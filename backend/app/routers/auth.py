"""Guest sessions and the current user - the only two auth endpoints.

There is no register, login or password reset: every visitor gets a guest
account minted by /guest, and that account's data lives only as long as the
row does (see scripts.prune_guests). This is a deliberate product decision,
not a placeholder for the flows that used to be here.

No `from __future__ import annotations` here: slowapi's @limiter.limit wrapper
makes FastAPI resolve string annotations against slowapi's module globals,
where this module's dependency aliases do not exist, so they degrade into
required body fields.
"""

import secrets
import uuid

from fastapi import APIRouter, Request

from app.config import settings
from app.deps import CurrentUser, DbSession
from app.errors import ForbiddenError
from app.logging_config import get_logger
from app.models import BrandProfile, User
from app.rate_limit import limiter
from app.schemas import TokenResponse, UserOut
from app.security import create_access_token, hash_password

logger = get_logger(__name__)
router = APIRouter(prefix="/api/auth", tags=["auth"])


def _token_response(user: User) -> TokenResponse:
    token = create_access_token(user.id, role=user.role.value)
    return TokenResponse(
        access_token=token,
        expires_in=settings.access_token_expire_minutes * 60,
        user=UserOut.model_validate(user),
    )


@router.post("/guest", response_model=TokenResponse, status_code=201)
@limiter.limit(settings.guest_rate_limit)
def guest(request: Request, db: DbSession) -> TokenResponse:
    """Mint a throwaway account so the app opens without a login.

    Each caller gets their own row, so one visitor never sees another's videos
    or brand. The account is real in every respect except that nobody knows its
    password: a random one is hashed and discarded, which keeps
    `users.password_hash` NOT NULL without leaving a credential that could be
    guessed.
    """
    if not settings.guest_sessions_enabled:
        raise ForbiddenError("Guest sessions are disabled")

    # Collision-proof without a uniqueness retry loop, under a subdomain nobody
    # receives mail on. `.example` is reserved by RFC 2606 for exactly this and
    # can never be registered.
    #
    # NOT `.invalid` (also RFC 2606) and NOT `.local` (mDNS), tempting as both
    # are: EmailStr rejects special-use names, so UserOut fails to serialise and
    # the endpoint 500s after having already committed the row.
    suffix = uuid.uuid4().hex
    user = User(
        name="Guest",
        email=f"guest-{suffix}@guest.aseelo.example",
        password_hash=hash_password(secrets.token_urlsafe(32)),
        is_guest=True,
    )
    db.add(user)
    db.flush()
    db.add(BrandProfile(user_id=user.id, brand_name="My Brand"))
    db.commit()
    db.refresh(user)

    logger.info("guest_session_created", extra={"user_id": str(user.id)})
    return _token_response(user)


@router.get("/me", response_model=UserOut)
def me(user: CurrentUser) -> UserOut:
    return UserOut.model_validate(user)
