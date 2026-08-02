"""S3-compatible storage backend (AWS S3, Cloudflare R2, MinIO, Wasabi, ...)."""

from __future__ import annotations

from pathlib import Path
from typing import BinaryIO

from app.storage.base import Storage, StorageError, StoredObject, sanitize_key


class S3Storage(Storage):
    def __init__(
        self,
        bucket: str,
        *,
        endpoint_url: str | None = None,
        access_key: str | None = None,
        secret_key: str | None = None,
        region: str = "auto",
        public_base_url: str | None = None,
    ):
        import boto3
        from botocore.config import Config

        self.bucket = bucket
        self.public_base_url = public_base_url
        self._client = boto3.client(
            "s3",
            endpoint_url=endpoint_url or None,
            aws_access_key_id=access_key or None,
            aws_secret_access_key=secret_key or None,
            region_name=region,
            config=Config(signature_version="s3v4", retries={"max_attempts": 3, "mode": "standard"}),
        )

    # ---------------- API ----------------
    def save_stream(self, key: str, stream: BinaryIO, content_type: str | None = None) -> StoredObject:
        key = sanitize_key(key)
        extra = {"ContentType": content_type} if content_type else {}
        self._client.upload_fileobj(stream, self.bucket, key, ExtraArgs=extra or None)
        return StoredObject(key=key, size=self.size(key), content_type=content_type)

    def save_file(self, key: str, path: Path, content_type: str | None = None) -> StoredObject:
        key = sanitize_key(key)
        extra = {"ContentType": content_type} if content_type else {}
        self._client.upload_file(str(path), self.bucket, key, ExtraArgs=extra or None)
        return StoredObject(key=key, size=Path(path).stat().st_size, content_type=content_type)

    def download_to(self, key: str, destination: Path) -> Path:
        key = sanitize_key(key)
        destination = Path(destination)
        destination.parent.mkdir(parents=True, exist_ok=True)
        try:
            self._client.download_file(self.bucket, key, str(destination))
        except Exception as exc:  # noqa: BLE001
            raise StorageError(f"Failed to download {key}: {exc}") from exc
        return destination

    def open_stream(self, key: str) -> BinaryIO:
        key = sanitize_key(key)
        try:
            response = self._client.get_object(Bucket=self.bucket, Key=key)
        except Exception as exc:  # noqa: BLE001
            raise StorageError(f"Object not found: {key}") from exc
        return response["Body"]

    def delete(self, key: str) -> None:
        self._client.delete_object(Bucket=self.bucket, Key=sanitize_key(key))

    def exists(self, key: str) -> bool:
        try:
            self._client.head_object(Bucket=self.bucket, Key=sanitize_key(key))
            return True
        except Exception:  # noqa: BLE001
            return False

    def size(self, key: str) -> int:
        try:
            head = self._client.head_object(Bucket=self.bucket, Key=sanitize_key(key))
        except Exception as exc:  # noqa: BLE001
            raise StorageError(f"Object not found: {key}") from exc
        return int(head["ContentLength"])

    def public_url(self, key: str) -> str:
        key = sanitize_key(key)
        if self.public_base_url:
            return f"{self.public_base_url.rstrip('/')}/{key}"
        # Presigned URL keeps private buckets usable without a CDN in front.
        return self._client.generate_presigned_url(
            "get_object", Params={"Bucket": self.bucket, "Key": key}, ExpiresIn=3600
        )
