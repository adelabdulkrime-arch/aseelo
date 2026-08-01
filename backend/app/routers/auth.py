"""Authentication endpoints: register, login, current user."""

# No `from __future__ import annotations` here: slowapi's @limiter.limit wrapper makes
# FastAPI resolve string annotations against slowapi's module globals, where this
# module's dependency aliases do not exist, so they degrade into required body fields.

import re
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, BackgroundTasks, Request
from sqlalchemy import delete, func, select

from app.config import settings
from app.deps import CurrentUser, DbSession
from app.errors import AuthError, ConflictError, ValidationError
from app.logging_config import get_logger
from app.models import BrandProfile, PasswordResetToken, PaymentCharge, User
from app.rate_limit import limiter
from app.schemas import (
    ForgotPasswordRequest,
    LoginRequest,
    MessageResponse,
    RegisterRequest,
    ResetPasswordRequest,
    SetupAccountRequest,
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


# One message for unknown, spent and mismatched charges alike. The pair
# (email, charge_id) is what authorises account creation, so telling the caller
# which half was wrong would turn this into a confirmation oracle for charge
# references.
_INVALID_CHARGE_MESSAGE = "This activation link is invalid or has already been used."

_NAME_SEPARATORS = re.compile(r"[._+\-]+")


def _name_from_email(email: str) -> str:
    """Best-effort display name: the setup page collects only email and password.

    The customer arrives from a payment receipt, and asking for a name there
    would add a field to the one screen that should be as short as possible.
    They can correct it in Settings; the brand name is theirs to edit anyway.
    """
    local = _NAME_SEPARATORS.sub(" ", email.split("@", 1)[0])
    name = " ".join(part.capitalize() for part in local.split() if part)
    # `users.name` is NOT NULL and the rest of the app assumes it reads like a
    # name, but `a@example.com` is a legal address - so fall back rather than
    # write a one-character string.
    return name[:120] if len(name) >= 2 else "ASEELO Customer"


@router.post("/setup-account", response_model=TokenResponse, status_code=201)
@limiter.limit(settings.setup_account_rate_limit)
def setup_account(
    request: Request, payload: SetupAccountRequest, db: DbSession
) -> TokenResponse:
    """Turn a paid charge into an account, and sign the customer straight in."""
    charge = db.scalar(
        select(PaymentCharge)
        .where(PaymentCharge.charge_id == payload.charge_id)
        # Locked for the duration: without it two clicks on the same link can
        # both read used_at as NULL and both proceed. The users.email unique
        # index would still catch the duplicate, but as a 500 rather than a
        # clean refusal.
        .with_for_update()
    )

    if (
        charge is None
        or charge.used_at is not None
        # Case-insensitive: providers echo back whatever the customer typed,
        # and an address that differs only in case is the same mailbox.
        or charge.email.lower() != payload.email.lower()
    ):
        raise ValidationError(_INVALID_CHARGE_MESSAGE)

    # The ledger is the record of who paid, so the account belongs to the
    # address on the charge - not to whatever casing arrived in the URL.
    # Lowercased because login compares emails exactly: storing
    # `SARA.HASSAN@example.com` because that is how the link was written
    # produces an account nobody can sign in to, and the customer never typed
    # that address in the first place. Returned 201 and passed every test.
    email = charge.email.lower()

    # An address that already has an account must not have its password set by
    # whoever holds the link - paying with someone else's email would otherwise
    # be an account takeover. Compared case-insensitively, or the same casing
    # trick walks straight past the guard and makes a duplicate account. The
    # charge stays unused, so support can still redeem or refund it.
    if db.scalar(select(User).where(func.lower(User.email) == email)) is not None:
        raise ConflictError(
            "An account already exists for this email. Sign in instead, "
            "or reset your password."
        )

    user = User(
        name=_name_from_email(email),
        email=email,
        password_hash=hash_password(payload.password),
    )
    db.add(user)
    db.flush()
    db.add(BrandProfile(user_id=user.id, brand_name=f"{user.name}'s Brand"))

    charge.used_at = datetime.now(UTC)
    charge.user_id = user.id
    db.commit()
    db.refresh(user)

    logger.info(
        "account_setup_from_charge",
        extra={"user_id": str(user.id), "charge_id": charge.charge_id},
    )
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
