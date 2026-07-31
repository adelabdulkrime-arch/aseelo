"""Brand identity endpoints: read, update, logo upload."""

from __future__ import annotations

from fastapi import APIRouter, File, UploadFile

from app.deps import CurrentUser, DbSession, get_or_create_brand
from app.logging_config import get_logger
from app.models import BrandProfile
from app.schemas import BrandOut, BrandUpdate
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
def upload_logo(user: CurrentUser, db: DbSession, file: UploadFile = File(...)) -> BrandOut:
    validated = validate_image_upload(file)
    try:
        storage = get_storage()
        key = build_key("users", str(user.id), "brand", extension=validated.extension)
        storage.save_file(key, validated.temp_path, content_type=validated.content_type)

        brand = get_or_create_brand(db, user)
        old_logo = brand.logo_url
        brand.logo_url = key
        db.commit()
        db.refresh(brand)

        if old_logo and old_logo != key:
            storage.delete(old_logo)
    finally:
        validated.cleanup()

    logger.info("brand_logo_updated", extra={"user_id": str(user.id)})
    return _brand_out(brand)
