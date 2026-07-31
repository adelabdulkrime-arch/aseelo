"""FFprobe wrapper: inspect media files without loading them into memory."""

from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass
from fractions import Fraction
from pathlib import Path

from app.config import settings
from app.logging_config import get_logger

logger = get_logger(__name__)

PROBE_TIMEOUT_SECONDS = 60


class ProbeError(Exception):
    """Raised when a file cannot be probed or contains no usable video stream."""


@dataclass(frozen=True)
class MediaInfo:
    path: str
    container: str
    duration: float
    size_bytes: int
    # video
    video_codec: str
    width: int
    height: int
    fps: float
    rotation: int
    pixel_format: str | None
    # audio
    has_audio: bool
    audio_codec: str | None
    audio_channels: int | None
    bitrate: int | None

    @property
    def display_width(self) -> int:
        return self.height if self.rotation in (90, 270) else self.width

    @property
    def display_height(self) -> int:
        return self.width if self.rotation in (90, 270) else self.height

    @property
    def aspect_ratio(self) -> float:
        return self.display_width / self.display_height if self.display_height else 0.0


def _parse_fps(value: str | None) -> float:
    if not value or value in {"0/0", "0"}:
        return 0.0
    try:
        return float(Fraction(value))
    except (ValueError, ZeroDivisionError):
        return 0.0


def _parse_rotation(stream: dict) -> int:
    """Rotation may live in tags (older FFmpeg) or in a displaymatrix side-data."""
    tags = stream.get("tags") or {}
    raw = tags.get("rotate")
    if raw is None:
        for side in stream.get("side_data_list") or []:
            if "rotation" in side:
                raw = side["rotation"]
                break
    try:
        rotation = int(round(float(raw)))
    except (TypeError, ValueError):
        return 0
    return rotation % 360


def run_ffprobe(path: str | Path) -> dict:
    path = str(path)
    command = [
        settings.ffprobe_path,
        "-v",
        "error",
        "-print_format",
        "json",
        "-show_format",
        "-show_streams",
        path,
    ]
    try:
        completed = subprocess.run(  # noqa: S603 - fixed argv, no shell
            command,
            capture_output=True,
            timeout=PROBE_TIMEOUT_SECONDS,
            check=False,
        )
    except FileNotFoundError as exc:
        raise ProbeError(f"ffprobe executable not found at {settings.ffprobe_path!r}") from exc
    except subprocess.TimeoutExpired as exc:
        raise ProbeError("Probing the file timed out") from exc

    if completed.returncode != 0:
        stderr = completed.stderr.decode("utf-8", "replace").strip()
        raise ProbeError(f"The file could not be read as media: {stderr[:300]}")

    try:
        return json.loads(completed.stdout.decode("utf-8", "replace"))
    except json.JSONDecodeError as exc:
        raise ProbeError("ffprobe returned malformed output") from exc


def probe(path: str | Path) -> MediaInfo:
    """Return structured information about a media file."""
    payload = run_ffprobe(path)
    streams = payload.get("streams") or []
    fmt = payload.get("format") or {}

    video_streams = [s for s in streams if s.get("codec_type") == "video"]
    audio_streams = [s for s in streams if s.get("codec_type") == "audio"]

    # Ignore attached cover art / thumbnails masquerading as video streams.
    real_video = [s for s in video_streams if not (s.get("disposition") or {}).get("attached_pic")]
    if not real_video:
        raise ProbeError("The file does not contain a video stream")
    vs = real_video[0]

    width = int(vs.get("width") or 0)
    height = int(vs.get("height") or 0)
    if width <= 0 or height <= 0:
        raise ProbeError("The video stream has invalid dimensions")

    duration = 0.0
    for candidate in (vs.get("duration"), fmt.get("duration")):
        try:
            duration = float(candidate)
            if duration > 0:
                break
        except (TypeError, ValueError):
            continue

    size_bytes = int(fmt.get("size") or Path(path).stat().st_size)
    audio = audio_streams[0] if audio_streams else None

    try:
        bitrate = int(fmt.get("bit_rate"))
    except (TypeError, ValueError):
        bitrate = None

    info = MediaInfo(
        path=str(path),
        container=fmt.get("format_name", "unknown"),
        duration=round(duration, 3),
        size_bytes=size_bytes,
        video_codec=vs.get("codec_name", "unknown"),
        width=width,
        height=height,
        fps=_parse_fps(vs.get("avg_frame_rate") or vs.get("r_frame_rate")),
        rotation=_parse_rotation(vs),
        pixel_format=vs.get("pix_fmt"),
        has_audio=audio is not None,
        audio_codec=audio.get("codec_name") if audio else None,
        audio_channels=int(audio.get("channels")) if audio and audio.get("channels") else None,
        bitrate=bitrate,
    )
    logger.info(
        "probe_complete",
        extra={
            "codec": info.video_codec,
            "resolution": f"{info.width}x{info.height}",
            "duration": info.duration,
            "has_audio": info.has_audio,
        },
    )
    return info
