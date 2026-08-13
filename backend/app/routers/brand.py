"""Brand identity endpoints: read, update, logo upload."""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, File, Query, UploadFile

from app.deps import CurrentUser, DbSession, get_or_create_brand
from app.logging_config import get_logger
from app.models import BrandProfile
from app.schemas import BrandOut, BrandUpdate
from app.services import logo_cutout
from app.services.file_validation import validate_image_upload
from app.storage import build_key, get_storage

logger = get_logger(__name__)
router = APIRouter(prefix="/api/brand", tags=["brand"])


def _brand_out(brand: BrandProfile) -> BrandOut:
    out = BrandOut.model_validate(brand)
    if brand.logo_url:
        out.logo_url = get_storage().public_url(brand.logo_url)
    return out


@router.get("", response_model=BrandOut)
def get_brand(user: CurrentUser, db: DbSession) -> BrandOut:
    return _brand_out(get_or_create_brand(db, user))


@router.put("", response_model=BrandOut)
def update_brand(payload: BrandUpdate, user: CurrentUser, db: DbSession) -> BrandOut:
    brand = get_or_create_brand(db, user)
    updates = payload.model_dump(exclude_unset=True)
    for field, value in updates.items():
        setattr(brand, field, value)
    db.commit()
    db.refresh(brand)
    logger.info("brand_updated", extra={"user_id": str(user.id)})
    return _brand_out(brand)


@router.post("/logo", response_model=BrandOut)
def upload_logo(
    user: CurrentUser,
    db: DbSession,
    file: UploadFile = File(...),
    remove_white_background: bool = Query(
        default=False,
        description=(
            "Opt-in: make a flat background transparent. Off by default because "
            "it also clears colour that belongs to the design."
        ),
    ),
    cutout_mode: Literal["auto", "white"] = Query(
        default="auto",
        description=(
            "'auto' samples the logo's own border colour, so it works on any flat "
            "backdrop. 'white' is the original white-only rule, kept so an upload "
            "that worked before keeps behaving identically."
        ),
    ),
) -> BrandOut:
    validated = validate_image_upload(file)
    cutout_applied = False
    try:
        storage = get_storage()
        upload_path = validated.temp_path
        extension = validated.extension
        content_type = validated.content_type

        if remove_white_background and not validated.has_transparency:
            cutout_path = validated.temp_path.with_suffix(".cutout.png")
            if logo_cutout.remove_background(
                validated.temp_path, cutout_path, mode=cutout_mode
            ):
                cutout_applied = True
                upload_path = cutout_path
                extension = ".png"
                content_type = "image/png"

        key = build_key("users", str(user.id), "brand", extension=extension)
        storage.save_file(key, upload_path, content_type=content_type)

        brand = get_or_create_brand(db, user)
        old_logo = brand.logo_url
        brand.logo_url = key
        db.commit()
        db.refresh(brand)

        if old_logo and old_logo != key:
            storage.delete(old_logo)
    finally:
        if cutout_applied:
            validated.temp_path.with_suffix(".cutout.png").unlink(missing_ok=True)
        validated.cleanup()

    logger.info(
        "brand_logo_updated",
        extra={
            "user_id": str(user.id),
            "has_transparency": validated.has_transparency,
            "cutout_applied": cutout_applied,
        },
    )
    out = _brand_out(brand)
    # After a cutout the stored logo is transparent regardless of what arrived.
    out.logo_has_transparency = True if cutout_applied else validated.has_transparency
    out.logo_cutout_applied = cutout_applied
    return out
