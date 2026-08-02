"""Local filesystem storage backend (development / single-node deployments)."""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import BinaryIO

from app.storage.base import Storage, StorageError, StoredObject, UnsafeKeyError, sanitize_key

_CHUNK = 1024 * 1024


class LocalStorage(Storage):
    def __init__(self, root: str | Path):
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    # ---------------- internals ----------------
    def _path(self, key: str) -> Path:
        safe = sanitize_key(key)
        path = (self.root / safe).resolve()
        # Defence in depth: even with a sanitised key, verify containment.
        if not path.is_relative_to(self.root):
            raise UnsafeKeyError("Resolved path escapes the storage root")
        return path

    # ---------------- API ----------------
    def save_stream(self, key: str, stream: BinaryIO, content_type: str | None = None) -> StoredObject:
        path = self._path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        size = 0
        with path.open("wb") as fh:
            while chunk := stream.read(_CHUNK):
                size += len(chunk)
                fh.write(chunk)
        return StoredObject(key=key, size=size, content_type=content_type)

    def save_file(self, key: str, path: Path, content_type: str | None = None) -> StoredObject:
        target = self._path(key)
        target.parent.mkdir(parents=True, exist_ok=True)
        if Path(path).resolve() != target:
            shutil.copyfile(path, target)
        return StoredObject(key=key, size=target.stat().st_size, content_type=content_type)

    def download_to(self, key: str, destination: Path) -> Path:
        source = self._path(key)
        if not source.exists():
            raise StorageError(f"Object not found: {key}")
        destination = Path(destination)
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, destination)
        return destination

    def open_stream(self, key: str) -> BinaryIO:
        path = self._path(key)
        if not path.exists():
            raise StorageError(f"Object not found: {key}")
        return path.open("rb")

    def delete(self, key: str) -> None:
        path = self._path(key)
        path.unlink(missing_ok=True)

    def exists(self, key: str) -> bool:
        try:
            return self._path(key).is_file()
        except UnsafeKeyError:
            return False

    def size(self, key: str) -> int:
        path = self._path(key)
        if not path.exists():
            raise StorageError(f"Object not found: {key}")
        return path.stat().st_size

    def public_url(self, key: str) -> str:
        from app.config import settings

        return f"{settings.public_media_base_url.rstrip('/')}/{sanitize_key(key)}"

    # ---------------- local-only helper ----------------
    def local_path(self, key: str) -> Path:
        """Direct filesystem path - only valid for this backend."""
        return self._path(key)
