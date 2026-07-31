"""FFmpeg rendering: 9:16 normalisation + single flattened overlay + H.264/AAC."""

from __future__ import annotations

import shlex
import subprocess
import tempfile
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from app.config import settings
from app.logging_config import get_logger

logger = get_logger(__name__)

ProgressCallback = Callable[[float], None]


class RenderError(Exception):
    """Raised when FFmpeg fails or produces nothing usable."""


@dataclass
class RenderRequest:
    input_path: Path
    overlay_path: Path
    output_path: Path
    duration: float
    has_audio: bool
    background_mode: str = "cover"
    blur_sigma: float = 25.0
    pad_color: str = "black"
    width: int = 0
    height: int = 0
    fps: int = 0
    crf: int = 0
    preset: str = ""
    audio_bitrate: str = ""

    def __post_init__(self) -> None:
        self.width = self.width or settings.output_width
        self.height = self.height or settings.output_height
        self.fps = self.fps or settings.output_fps
        self.crf = self.crf or settings.output_crf
        self.preset = self.preset or settings.output_preset
        self.audio_bitrate = self.audio_bitrate or settings.output_audio_bitrate


@dataclass
class RenderResult:
    output_path: Path
    size_bytes: int
    elapsed_seconds: float
    command: str


def build_filter_complex(request: RenderRequest) -> str:
    """Build the filter graph that normalises the source to 9:16 and overlays the brand layer."""
    w, h = request.width, request.height
    mode = (request.background_mode or "cover").lower()

    if mode == "blur_pad":
        # Blurred, cropped copy of the source fills the frame; the untouched
        # source is fitted on top so nothing is cut off.
        base = (
            f"[0:v]split=2[bgsrc][fgsrc];"
            f"[bgsrc]scale={w}:{h}:force_original_aspect_ratio=increase,"
            f"crop={w}:{h},gblur=sigma={request.blur_sigma:g}[bg];"
            f"[fgsrc]scale={w}:{h}:force_original_aspect_ratio=decrease[fg];"
            f"[bg][fg]overlay=(W-w)/2:(H-h)/2:format=auto[base]"
        )
    elif mode == "pad":
        base = (
            f"[0:v]scale={w}:{h}:force_original_aspect_ratio=decrease,"
            f"pad={w}:{h}:(ow-iw)/2:(oh-ih)/2:color={request.pad_color}[base]"
        )
    else:  # cover - centre-crop, the default for Reels/Shorts
        base = (
            f"[0:v]scale={w}:{h}:force_original_aspect_ratio=increase,crop={w}:{h}[base]"
        )

    return (
        f"{base};"
        f"[1:v]scale={w}:{h}[ovl];"
        f"[base][ovl]overlay=0:0:format=auto:eof_action=repeat[composed];"
        f"[composed]fps={request.fps},setsar=1,format=yuv420p[outv]"
    )


def build_command(request: RenderRequest) -> list[str]:
    command = [
        settings.ffmpeg_path,
        "-hide_banner",
        "-nostdin",
        "-y",
        "-loglevel",
        "error",
        "-progress",
        "pipe:1",
        "-i",
        str(request.input_path),
        "-i",
        str(request.overlay_path),
        "-filter_complex",
        build_filter_complex(request),
        "-map",
        "[outv]",
    ]

    if request.has_audio:
        command += [
            "-map",
            "0:a:0",
            "-c:a",
            "aac",
            "-b:a",
            request.audio_bitrate,
            "-ar",
            "44100",
            "-ac",
            "2",
        ]
    else:
        command += ["-an"]

    command += [
        "-c:v",
        "libx264",
        "-preset",
        request.preset,
        "-crf",
        str(request.crf),
        "-profile:v",
        "high",
        "-level",
        "4.1",
        "-pix_fmt",
        "yuv420p",
        "-g",
        str(request.fps * 2),
        "-movflags",
        "+faststart",
        "-max_muxing_queue_size",
        "1024",
        str(request.output_path),
    ]
    return command


def _parse_progress_line(line: str) -> float | None:
    """Return the encoded position in seconds for an FFmpeg progress line."""
    if "=" not in line:
        return None
    key, _, value = line.partition("=")
    key = key.strip()
    value = value.strip()
    try:
        if key == "out_time_us" or key == "out_time_ms":
            # FFmpeg reports microseconds under both keys (a long-standing quirk).
            return int(value) / 1_000_000
        if key == "out_time":
            hours, minutes, seconds = value.split(":")
            return int(hours) * 3600 + int(minutes) * 60 + float(seconds)
    except (ValueError, TypeError):
        return None
    return None


def render(request: RenderRequest, progress: ProgressCallback | None = None) -> RenderResult:
    """Run FFmpeg, streaming real encode progress back through ``progress``.

    ``progress`` receives a 0.0-1.0 fraction of the encode.
    """
    request.output_path.parent.mkdir(parents=True, exist_ok=True)
    command = build_command(request)
    printable = shlex.join(command)
    logger.info("ffmpeg_render_start", extra={"ffmpeg_command": printable})

    total = max(0.1, float(request.duration or 0.1))
    timeout = max(300.0, total * 30)
    started = time.monotonic()

    with tempfile.TemporaryFile(mode="w+", encoding="utf-8", errors="replace") as stderr_file:
        try:
            process = subprocess.Popen(  # noqa: S603 - fixed argv, no shell
                command,
                stdout=subprocess.PIPE,
                stderr=stderr_file,
                stdin=subprocess.DEVNULL,
                text=True,
                bufsize=1,
            )
        except FileNotFoundError as exc:
            raise RenderError(f"ffmpeg executable not found at {settings.ffmpeg_path!r}") from exc

        assert process.stdout is not None  # noqa: S101 - type narrowing, not a runtime check
        last_reported = -1.0
        try:
            for raw_line in process.stdout:
                position = _parse_progress_line(raw_line)
                if position is None:
                    continue
                fraction = max(0.0, min(1.0, position / total))
                # Throttle: only report meaningful movement.
                if progress and fraction - last_reported >= 0.01:
                    last_reported = fraction
                    progress(fraction)
            process.wait(timeout=timeout)
        except subprocess.TimeoutExpired as exc:
            process.kill()
            process.wait()
            raise RenderError(f"Rendering timed out after {timeout:.0f}s") from exc
        finally:
            if process.stdout:
                process.stdout.close()

        stderr_file.seek(0)
        stderr = stderr_file.read().strip()

    elapsed = time.monotonic() - started

    if process.returncode != 0:
        logger.error(
            "ffmpeg_render_failed",
            extra={"returncode": process.returncode, "ffmpeg_stderr": stderr[-2000:]},
        )
        raise RenderError(_friendly_ffmpeg_error(stderr, process.returncode))

    if not request.output_path.exists() or request.output_path.stat().st_size == 0:
        raise RenderError("FFmpeg reported success but produced no output file")

    if progress:
        progress(1.0)

    size = request.output_path.stat().st_size
    logger.info(
        "ffmpeg_render_complete",
        extra={"elapsed_seconds": round(elapsed, 2), "output_bytes": size},
    )
    return RenderResult(
        output_path=request.output_path, size_bytes=size, elapsed_seconds=elapsed, command=printable
    )


def _friendly_ffmpeg_error(stderr: str, returncode: int) -> str:
    """Map common FFmpeg failures to something a non-technical user can act on."""
    lowered = stderr.lower()
    if "no such file or directory" in lowered:
        return "The source video could not be opened."
    if "invalid data found" in lowered or "moov atom not found" in lowered:
        return "The uploaded file is corrupt or not a valid video."
    if "no space left" in lowered:
        return "The server ran out of disk space while rendering."
    if "killed" in lowered or returncode in (-9, 137):
        return "Rendering was stopped because it exceeded the available memory."
    tail = stderr.strip().splitlines()[-1] if stderr.strip() else f"exit code {returncode}"
    return f"Video rendering failed: {tail[:200]}"


def generate_thumbnail(
    video_path: Path,
    output_path: Path,
    *,
    at_seconds: float = 1.0,
    width: int = 540,
) -> Path:
    """Extract a poster frame as JPEG. Non-fatal: raises RenderError on failure."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    seek = max(0.0, at_seconds)
    command = [
        settings.ffmpeg_path,
        "-hide_banner",
        "-nostdin",
        "-y",
        "-loglevel",
        "error",
        "-ss",
        f"{seek:.3f}",
        "-i",
        str(video_path),
        "-frames:v",
        "1",
        "-vf",
        f"scale={width}:-2",
        "-q:v",
        "3",
        str(output_path),
    ]
    completed = subprocess.run(  # noqa: S603
        command, capture_output=True, timeout=120, check=False
    )
    if completed.returncode != 0 or not output_path.exists():
        # Retry from the very first frame (very short clips can fail the seek).
        command[command.index("-ss") + 1] = "0"
        completed = subprocess.run(  # noqa: S603
            command, capture_output=True, timeout=120, check=False
        )
    if completed.returncode != 0 or not output_path.exists():
        raise RenderError(
            "Thumbnail extraction failed: "
            + completed.stderr.decode("utf-8", "replace").strip()[:200]
        )
    return output_path


def ffmpeg_version() -> str:
    try:
        completed = subprocess.run(  # noqa: S603
            [settings.ffmpeg_path, "-version"], capture_output=True, timeout=15, check=False
        )
        return completed.stdout.decode("utf-8", "replace").splitlines()[0]
    except Exception as exc:  # noqa: BLE001
        return f"unavailable ({exc.__class__.__name__})"
