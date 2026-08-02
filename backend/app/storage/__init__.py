"""Storage provider factory."""

from __future__ import annotations

from functools import lru_cache

from app.config import settings
from app.storage.base import (
    Storage,
    StorageError,
    StoredObject,
    UnsafeKeyError,
    build_key,
    sanitize_key,
)
from app.storage.local import LocalStorage

__all__ = [
    "Storage",
    "StorageError",
    "StoredObject",
    "UnsafeKeyError",
    "build_key",
    "get_storage",
    "sanitize_key",
]


@lru_cache
def get_storage() -> Storage:
    if settings.storage_provider == "s3":
        from app.storage.s3 import S3Storage

        return S3Storage(
            bucket=settings.s3_bucket,
            endpoint_url=settings.s3_endpoint,
            access_key=settings.s3_access_key,
            secret_key=settings.s3_secret_key,
            region=settings.s3_region,
            public_base_url=settings.s3_public_base_url,
        )
    return LocalStorage(settings.storage_path)
