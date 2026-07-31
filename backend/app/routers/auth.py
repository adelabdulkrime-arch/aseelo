"""Authentication endpoints: register, login, current user."""

# No `from __future__ import annotations` here: slowapi's @limiter.limit wrapper makes
# FastAPI resolve string annotations against slowapi's module globals, where this
# module's dependency aliases do not exist, so they degrade into required body fields.

from fastapi import APIRouter, Request
from sqlalchemy import select

from app.config import settings
from app.deps import CurrentUser, DbSession
from app.errors import AuthError, ConflictError
from app.logging_config import get_logger
from app.models import BrandProfile, User
from app.rate_limit import limiter
from app.schemas import LoginRequest, RegisterRequest, TokenResponse, UserOut
from app.security import create_access_token, hash_password, verify_password

logger = get_logger(__name__)
router = APIRouter(prefix="/api/auth", tags=["auth"])


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
