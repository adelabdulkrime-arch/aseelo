"""Storage abstraction shared by the API and the worker.

Business logic only ever deals with opaque *keys* such as
``users/<uuid>/outputs/<uuid>.mp4``. Whether those live on a local disk or in an
S3-compatible bucket is decided by ``STORAGE_PROVIDER``.
"""

from __future__ import annotations

import posixpath
import re
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO

_SAFE_SEGMENT = re.compile(r"^[A-Za-z0-9._-]+$")


class StorageError(Exception):
    """Raised for unrecoverable storage failures."""


class UnsafeKeyError(StorageError):
    """Raised when a key would escape the storage root."""


@dataclass(frozen=True)
class StoredObject:
    key: str
    size: int
    content_type: str | None = None


def sanitize_key(key: str) -> str:
    """Validate a storage key and return it normalised.

    Rejects absolute paths, traversal (``..``), backslashes, empty segments and
    any character outside ``[A-Za-z0-9._-]`` - which makes path traversal and
    Windows/UNC tricks impossible regardless of the backend.
    """
    if not key or len(key) > 512:
        raise UnsafeKeyError("Storage key has an invalid length")
    if "\\" in key or "\x00" in key:
        raise UnsafeKeyError("Storage key contains illegal characters")
    if key.startswith("/") or ":" in key:
        raise UnsafeKeyError("Storage key must be relative")

    segments = key.split("/")
    for segment in segments:
        if not segment or segment in {".", ".."} or not _SAFE_SEGMENT.match(segment):
            raise UnsafeKeyError(f"Illegal path segment: {segment!r}")

    normalised = posixpath.normpath("/".join(segments))
    if normalised.startswith(("/", "..")):
        raise UnsafeKeyError("Storage key escapes the storage root")
    return normalised


def build_key(*parts: str, extension: str = "") -> str:
    """Build a safe, unique storage key. Original filenames are never used."""
    unique = uuid.uuid4().hex
    ext = extension.lower().lstrip(".")
    name = f"{unique}.{ext}" if ext else unique
    return sanitize_key("/".join([*parts, name]))


class Storage(ABC):
    """Minimal storage contract used across the app."""

    @abstractmethod
    def save_stream(self, key: str, stream: BinaryIO, content_type: str | None = None) -> StoredObject:
        """Persist a readable binary stream under ``key``."""

    @abstractmethod
    def save_file(self, key: str, path: Path, content_type: str | None = None) -> StoredObject:
        """Persist a local file under ``key``."""

    @abstractmethod
    def download_to(self, key: str, destination: Path) -> Path:
        """Copy the object at ``key`` to a local path (used by the renderer)."""

    @abstractmethod
    def open_stream(self, key: str) -> BinaryIO:
        """Open the object for reading."""

    @abstractmethod
    def delete(self, key: str) -> None:
        """Delete the object; missing objects are not an error."""

    @abstractmethod
    def exists(self, key: str) -> bool: ...

    @abstractmethod
    def size(self, key: str) -> int: ...

    @abstractmethod
    def public_url(self, key: str) -> str:
        """Browser-reachable URL for the object."""
