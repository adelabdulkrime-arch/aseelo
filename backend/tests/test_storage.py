"""Storage key safety and the local backend contract."""

from __future__ import annotations

import io

import pytest

from app.storage.base import UnsafeKeyError, build_key, sanitize_key
from app.storage.local import LocalStorage


@pytest.mark.parametrize(
    "key",
    [
        "../../etc/passwd",
        "/etc/passwd",
        "users/../../../secret",
        "users\\windows\\path",
        "C:/Windows/System32/config",
        "users//double",
        "users/./here",
        "",
        "users/\x00null",
    ],
)
def test_sanitize_key_rejects_traversal(key):
    with pytest.raises(UnsafeKeyError):
        sanitize_key(key)


def test_sanitize_key_accepts_safe_keys():
    assert sanitize_key("users/abc-123/outputs/file.mp4") == "users/abc-123/outputs/file.mp4"


def test_build_key_never_reuses_original_filename():
    key = build_key("users", "abc", "inputs", extension=".MP4")
    assert key.startswith("users/abc/inputs/")
    assert key.endswith(".mp4")
    assert build_key("users", "abc", "inputs", extension="mp4") != key


def test_local_storage_round_trip(tmp_path):
    storage = LocalStorage(tmp_path)
    key = build_key("users", "abc", "inputs", extension="bin")

    stored = storage.save_stream(key, io.BytesIO(b"hello aseelo"))
    assert stored.size == 12
    assert storage.exists(key)
    assert storage.size(key) == 12

    destination = tmp_path / "out" / "copy.bin"
    storage.download_to(key, destination)
    assert destination.read_bytes() == b"hello aseelo"

    storage.delete(key)
    assert not storage.exists(key)
    # Deleting a missing object is not an error.
    storage.delete(key)


def test_local_storage_refuses_escaping_keys(tmp_path):
    storage = LocalStorage(tmp_path)
    with pytest.raises(UnsafeKeyError):
        storage.save_stream("../escape.bin", io.BytesIO(b"nope"))
    assert not storage.exists("../escape.bin")
