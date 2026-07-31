"""Shared FastAPI dependencies: authentication, authorization, ownership checks."""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.database import get_db
from app.errors import AuthError, ForbiddenError, NotFoundError
from app.logging_config import user_id_var, video_id_var
from app.models import BrandProfile, User, UserRole, Video
from app.security import TokenError, decode_access_token

bearer_scheme = HTTPBearer(auto_error=False, description="JWT access token")


def get_current_user(
    request: Request,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
    db: Annotated[Session, Depends(get_db)],
) -> User:
    if credentials is None or not credentials.credentials:
        raise AuthError("Authentication required")

    try:
        payload = decode_access_token(credentials.credentials)
    except TokenError as exc:
        raise AuthError(str(exc)) from exc

    try:
        user_id = uuid.UUID(payload["sub"])
    except (KeyError, ValueError) as exc:
        raise AuthError("Invalid token subject") from exc

    user = db.get(User, user_id)
    if user is None:
        raise AuthError("User no longer exists")
    if not user.is_active:
        raise ForbiddenError("Account is disabled")

    request.state.user_id = str(user.id)
    user_id_var.set(str(user.id))
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]
DbSession = Annotated[Session, Depends(get_db)]


def require_admin(user: CurrentUser) -> User:
    if user.role is not UserRole.ADMIN:
        raise ForbiddenError("Administrator privileges required")
    return user


def get_or_create_brand(db: Session, user: User) -> BrandProfile:
    brand = db.scalar(select(BrandProfile).where(BrandProfile.user_id == user.id))
    if brand is None:
        brand = BrandProfile(user_id=user.id, brand_name=f"{user.name}'s Brand")
        db.add(brand)
        db.commit()
        db.refresh(brand)
    return brand


def get_owned_video(video_id: uuid.UUID, db: DbSession, user: CurrentUser) -> Video:
    """Load a video, enforcing that it belongs to the authenticated user.

    Returns 404 (not 403) for other users' videos so IDs are not enumerable.
    """
    video = db.scalar(
        select(Video)
        .where(Video.id == video_id)
        .options(selectinload(Video.jobs), selectinload(Video.template))
    )
    if video is None or video.user_id != user.id:
        raise NotFoundError("Video not found")
    video_id_var.set(str(video.id))
    return video


OwnedVideo = Annotated[Video, Depends(get_owned_video)]
