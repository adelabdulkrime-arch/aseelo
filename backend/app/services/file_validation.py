"""Upload validation: size, extension, declared MIME type, file signature, media probe.

Uploads are streamed to a temporary file in bounded chunks - a 500 MB video is
never held in memory.
"""

from __future__ import annotations

import os
import tempfile
from dataclasses import dataclass
from pathlib import Path

from fastapi import UploadFile

from app.config import settings
from app.errors import PayloadTooLargeError, ValidationError
from app.logging_config import get_logger
from app.video.probe import MediaInfo, ProbeError, probe

logger = get_logger(__name__)

CHUNK_SIZE = 1024 * 1024

# (offset, magic bytes) pairs; a file matches if ANY pair matches.
VIDEO_SIGNATURES: tuple[tuple[int, bytes], ...] = (
    (4, b"ftyp"),  # MP4 / MOV / M4V
    (0, b"\x1a\x45\xdf\xa3"),  # Matroska / WebM
    (0, b"RIFF"),  # AVI (further checked for "AVI " at offset 8)
    (0, b"\x00\x00\x01\xba"),  # MPEG program stream
    (0, b"\x00\x00\x01\xb3"),  # MPEG video stream
    (0, b"FLV\x01"),  # FLV
    (0, b"OggS"),  # Ogg (Theora)
)

IMAGE_SIGNATURES: tuple[tuple[int, bytes], ...] = (
    (0, b"\x89PNG\r\n\x1a\n"),
    (0, b"\xff\xd8\xff"),
    (0, b"RIFF"),  # WEBP (further checked for "WEBP" at offset 8)
    (0, b"GIF8"),
)


@dataclass
class ValidatedUpload:
    temp_path: Path
    size: int
    extension: str
    content_type: str
    media: MediaInfo | None = None
    # Images only: False when the logo has no usable alpha channel, so it will
    # render as an opaque rectangle over the video. None for non-images.
    has_transparency: bool | None = None

    def cleanup(self) -> None:
        try:
            self.temp_path.unlink(missing_ok=True)
        except OSError as exc:  # pragma: no cover
            logger.warning("temp_cleanup_failed", extra={"error": str(exc)})


def _extension_of(filename: str | None) -> str:
    if not filename:
        return ""
    # Only the final suffix is considered; the original name is never used as a path.
    return Path(filename).suffix.lower()


def _detect_transparency(path: Path) -> bool:
    """True when the image carries an alpha channel that is actually used.

    A mode check alone is not enough: a PNG saved from a JPEG source is RGBA
    with every pixel fully opaque, which still renders as a solid rectangle.
    """
    from PIL import Image

    try:
        with Image.open(path) as img:
            if "transparency" in img.info and img.mode in ("P", "L"):
                return True
            if img.mode not in ("RGBA", "LA", "PA"):
                return False
            alpha = img.convert("RGBA").getchannel("A")
            low, _high = alpha.getextrema()
            # Anything below fully opaque means real transparency is present.
            return low < 255
    except Exception as exc:  # noqa: BLE001 - detection must never fail the upload
        logger.warning("transparency_detection_failed", extra={"error": str(exc)})
        return False


def _matches(header: bytes, signatures: tuple[tuple[int, bytes], ...]) -> bool:
    for offset, magic in signatures:
        if header[offset : offset + len(magic)] == magic:
            if magic == b"RIFF":
                # Distinguish AVI / WEBP from other RIFF payloads.
                if header[8:12] in {b"AVI ", b"WEBP"}:
                    return True
                continue
            return True
    return False


def _stream_to_temp(upload: UploadFile, max_size: int, suffix: str) -> tuple[Path, int, bytes]:
    Path(settings.render_tmp_dir).mkdir(parents=True, exist_ok=True)
    fd, raw_path = tempfile.mkstemp(suffix=suffix or ".bin", dir=settings.render_tmp_dir)
    path = Path(raw_path)
    size = 0
    header = b""
    try:
        with os.fdopen(fd, "wb") as fh:
            while chunk := upload.file.read(CHUNK_SIZE):
                if not header:
                    header = chunk[:32]
                size += len(chunk)
                if size > max_size:
                    raise PayloadTooLargeError(
                        f"File exceeds the maximum allowed size of {max_size // (1024 * 1024)} MB"
                    )
                fh.write(chunk)
    except Exception:
        path.unlink(missing_ok=True)
        raise
    return path, size, header


def validate_video_upload(
    upload: UploadFile, *, max_duration_seconds: int | None = None
) -> ValidatedUpload:
    """Validate and persist an uploaded video to a temporary file.

    `max_duration_seconds` overrides the global ceiling for this one upload.
    Guests get a tighter limit than registered users: duration is what drives
    render cost, and on a one-core host a single long render saturates the
    machine for everyone. Defaults to the global setting when not given.
    """
    max_duration = (
        settings.max_video_duration_seconds
        if max_duration_seconds is None
        else min(max_duration_seconds, settings.max_video_duration_seconds)
    )
    extension = _extension_of(upload.filename)
    if extension not in settings.video_extensions:
        raise ValidationError(
            f"Unsupported video type '{extension or 'unknown'}'. "
            f"Allowed: {', '.join(sorted(settings.video_extensions))}"
        )

    content_type = (upload.content_type or "").split(";")[0].strip().lower()
    if content_type and content_type not in settings.video_mime_types:
        raise ValidationError(f"Unsupported content type '{content_type}'")

    path, size, header = _stream_to_temp(upload, settings.max_upload_size, extension)
    result = ValidatedUpload(
        temp_path=path, size=size, extension=extension, content_type=content_type or "video/mp4"
    )

    try:
        if size == 0:
            raise ValidationError("The uploaded file is empty")
        if not _matches(header, VIDEO_SIGNATURES):
            raise ValidationError("The file content is not a recognised video format")

        try:
            media = probe(path)
        except ProbeError as exc:
            raise ValidationError(str(exc)) from exc

        if media.duration <= 0:
            raise ValidationError("The video has no readable duration")
        if media.duration < settings.min_video_duration_seconds:
            raise ValidationError(
                f"The video is too short (minimum {settings.min_video_duration_seconds}s)"
            )
        if media.duration > max_duration:
            raise ValidationError(
                f"The video is too long ({media.duration:.0f}s). "
                f"Maximum is {max_duration}s"
            )
        if min(media.width, media.height) < 144:
            raise ValidationError(
                f"The video resolution is too low ({media.width}x{media.height}); "
                "at least 144px on the short edge is required"
            )
        result.media = media
    except Exception:
        result.cleanup()
        raise

    logger.info(
        "video_upload_validated",
        extra={
            "size_bytes": size,
            "duration": result.media.duration if result.media else None,
            "resolution": f"{result.media.width}x{result.media.height}" if result.media else None,
        },
    )
    return result


def validate_image_upload(upload: UploadFile, *, max_pixels: int = 8000) -> ValidatedUpload:
    """Validate and persist an uploaded image (brand logo)."""
    extension = _extension_of(upload.filename)
    if extension not in settings.image_extensions:
        raise ValidationError(
            f"Unsupported image type '{extension or 'unknown'}'. "
            f"Allowed: {', '.join(sorted(settings.image_extensions))}"
        )

    content_type = (upload.content_type or "").split(";")[0].strip().lower()
    if content_type and content_type not in settings.image_mime_types:
        raise ValidationError(f"Unsupported content type '{content_type}'")

    path, size, header = _stream_to_temp(upload, settings.max_logo_size, extension)
    result = ValidatedUpload(
        temp_path=path, size=size, extension=extension, content_type=content_type or "image/png"
    )

    try:
        if size == 0:
            raise ValidationError("The uploaded file is empty")
        if not _matches(header, IMAGE_SIGNATURES):
            raise ValidationError("The file content is not a recognised image format")

        from PIL import Image, UnidentifiedImageError

        try:
            with Image.open(path) as img:
                img.verify()
            with Image.open(path) as img:
                width, height = img.size
        except (UnidentifiedImageError, OSError) as exc:
            raise ValidationError("The image file is corrupt or unreadable") from exc

        if width <= 0 or height <= 0:
            raise ValidationError("The image has invalid dimensions")
        if width > max_pixels or height > max_pixels:
            raise ValidationError(f"The image is too large ({width}x{height}); max {max_pixels}px per side")

        result.has_transparency = _detect_transparency(path)
    except Exception:
        result.cleanup()
        raise

    logger.info(
        "image_upload_validated",
        extra={"size_bytes": size, "has_transparency": result.has_transparency},
    )
    return result
