"""Authentication endpoints: register, login, current user."""

# No `from __future__ import annotations` here: slowapi's @limiter.limit wrapper makes
# FastAPI resolve string annotations against slowapi's module globals, where this
# module's dependency aliases do not exist, so they degrade into required body fields.

from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, BackgroundTasks, Request
from sqlalchemy import delete, select

from app.config import settings
from app.deps import CurrentUser, DbSession
from app.errors import AuthError, ConflictError, ValidationError
from app.logging_config import get_logger
from app.models import BrandProfile, PasswordResetToken, User
from app.rate_limit import limiter
from app.schemas import (
    ForgotPasswordRequest,
    LoginRequest,
    MessageResponse,
    RegisterRequest,
    ResetPasswordRequest,
    TokenResponse,
    UserOut,
)
from app.security import (
    create_access_token,
    generate_reset_token,
    hash_password,
    hash_reset_token,
    verify_password,
)
from app.services.mail import MailError, send_password_reset

logger = get_logger(__name__)
router = APIRouter(prefix="/api/auth", tags=["auth"])

# Identical for every outcome: whether the address is registered must not be
# observable, so this is returned for unknown addresses too.
_RESET_SENT_MESSAGE = (
    "If an account exists for that address, a reset link has been sent."
)


def _token_response(user: User) -> TokenResponse:
    token = create_access_token(user.id, role=user.role.value)
    return TokenResponse(
        access_token=token,
        expires_in=settings.access_token_expire_minutes * 60,
        user=UserOut.model_validate(user),
    )


@router.post("/register", response_model=TokenResponse, status_code=201)
@limiter.limit(settings.auth_rate_limit)
def register(request: Request, payload: RegisterRequest, db: DbSession) -> TokenResponse:
    existing = db.scalar(select(User).where(User.email == payload.email))
    if existing is not None:
        raise ConflictError("An account with this email already exists")

    user = User(
        name=payload.name,
        email=payload.email,
        password_hash=hash_password(payload.password),
    )
    db.add(user)
    db.flush()
    db.add(BrandProfile(user_id=user.id, brand_name=f"{user.name}'s Brand"))
    db.commit()
    db.refresh(user)

    logger.info("user_registered", extra={"user_id": str(user.id)})
    return _token_response(user)


@router.post("/login", response_model=TokenResponse)
@limiter.limit(settings.auth_rate_limit)
def login(request: Request, payload: LoginRequest, db: DbSession) -> TokenResponse:
    user = db.scalar(select(User).where(User.email == payload.email))
    if user is None or not verify_password(payload.password, user.password_hash):
        raise AuthError("Invalid email or password")
    if not user.is_active:
        raise AuthError("Account is disabled")

    logger.info("user_login", extra={"user_id": str(user.id)})
    return _token_response(user)


@router.get("/me", response_model=UserOut)
def me(user: CurrentUser) -> UserOut:
    return UserOut.model_validate(user)


def _deliver_reset(email: str, name: str, token: str) -> None:
    """Send the reset mail, swallowing transport failures.

    Runs after the response has been returned. A raised MailError here would be
    an enumeration oracle: delivery is only attempted for addresses that exist,
    so a 500 on failure would answer exactly the question the generic message
    is designed to hide. Log it instead - the operator needs to know, the
    caller must not.
    """
    try:
        send_password_reset(to=email, name=name, token=token)
    except MailError as exc:
        logger.error("password_reset_mail_failed", extra={"email": email, "error": str(exc)})


@router.post("/forgot-password", response_model=MessageResponse)
@limiter.limit(settings.password_reset_rate_limit)
def forgot_password(
    request: Request,
    payload: ForgotPasswordRequest,
    db: DbSession,
    background: BackgroundTasks,
) -> MessageResponse:
    user = db.scalar(select(User).where(User.email == payload.email))

    if user is not None and user.is_active:
        # One live token per user: issuing a new link retires any earlier one.
        db.execute(delete(PasswordResetToken).where(PasswordResetToken.user_id == user.id))
        plaintext, token_hash = generate_reset_token()
        db.add(
            PasswordResetToken(
                user_id=user.id,
                token_hash=token_hash,
                expires_at=datetime.now(UTC)
                + timedelta(minutes=settings.password_reset_token_ttl_minutes),
            )
        )
        db.commit()
        # Deliberately after the response: sending inline would make the
        # endpoint measurably slower for registered addresses than for unknown
        # ones, reintroducing enumeration through timing.
        background.add_task(_deliver_reset, user.email, user.name, plaintext)
        logger.info("password_reset_requested", extra={"user_id": str(user.id)})
    else:
        logger.info("password_reset_requested_unknown_email")

    return MessageResponse(message=_RESET_SENT_MESSAGE)


@router.post("/reset-password", response_model=MessageResponse)
@limiter.limit(settings.password_reset_rate_limit)
def reset_password(
    request: Request, payload: ResetPasswordRequest, db: DbSession
) -> MessageResponse:
    record = db.scalar(
        select(PasswordResetToken).where(
            PasswordResetToken.token_hash == hash_reset_token(payload.token)
        )
    )
    # One message for every failure mode: an unknown token, a spent one and an
    # expired one are indistinguishable to the caller.
    if (
        record is None
        or record.used_at is not None
        or record.expires_at <= datetime.now(UTC)
    ):
        raise ValidationError("This reset link is invalid or has expired")

    user = db.scalar(select(User).where(User.id == record.user_id))
    if user is None or not user.is_active:
        raise ValidationError("This reset link is invalid or has expired")

    user.password_hash = hash_password(payload.password)
    record.used_at = datetime.now(UTC)
    # Any other outstanding link for this user dies with the reset.
    db.execute(
        delete(PasswordResetToken).where(
            PasswordResetToken.user_id == user.id, PasswordResetToken.id != record.id
        )
    )
    db.commit()

    # NOTE: access tokens are stateless JWTs, so sessions issued before the
    # reset stay valid until they expire. Revoking them needs a token version
    # on the user row - worth doing if this ever guards anything sensitive.
    logger.info("password_reset_completed", extra={"user_id": str(user.id)})
    return MessageResponse(message="Your password has been reset. You can now sign in.")
