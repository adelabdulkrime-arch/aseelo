"""Post-render quality validation (FFprobe based)."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from app.config import settings
from app.logging_config import get_logger
from app.video.probe import MediaInfo, ProbeError, probe

logger = get_logger(__name__)

MIN_OUTPUT_BYTES = 20 * 1024  # anything smaller cannot be a real 1080x1920 clip
DURATION_TOLERANCE_SECONDS = 1.0
DURATION_TOLERANCE_RATIO = 0.08


@dataclass
class QualityReport:
    ok: bool
    issues: list[str] = field(default_factory=list)
    checks: dict[str, bool] = field(default_factory=dict)
    info: MediaInfo | None = None

    @property
    def summary(self) -> str:
        return "; ".join(self.issues) if self.issues else "All quality checks passed"


def validate_output(
    path: Path,
    *,
    expected_width: int | None = None,
    expected_height: int | None = None,
    expected_duration: float | None = None,
    source_had_audio: bool = False,
) -> QualityReport:
    """Verify the rendered MP4 is what we promised the user."""
    expected_width = expected_width or settings.output_width
    expected_height = expected_height or settings.output_height

    report = QualityReport(ok=True)

    def check(name: str, passed: bool, message: str) -> None:
        report.checks[name] = passed
        if not passed:
            report.ok = False
            report.issues.append(message)

    if not path.exists():
        check("exists", False, "Rendered file is missing")
        return report
    check("exists", True, "")

    size = path.stat().st_size
    check("file_size", size >= MIN_OUTPUT_BYTES, f"Rendered file is suspiciously small ({size} bytes)")

    try:
        info = probe(path)
    except ProbeError as exc:
        check("readable", False, f"Rendered file is not readable as MP4: {exc}")
        return report
    report.info = info
    check("readable", True, "")

    check(
        "container",
        "mp4" in info.container or "mov" in info.container,
        f"Unexpected container: {info.container}",
    )
    check("video_codec_h264", info.video_codec == "h264", f"Video codec is {info.video_codec}, expected h264")
    check(
        "resolution",
        info.width == expected_width and info.height == expected_height,
        f"Resolution is {info.width}x{info.height}, expected {expected_width}x{expected_height}",
    )
    check(
        "pixel_format",
        info.pixel_format in {"yuv420p", "yuvj420p"},
        f"Pixel format is {info.pixel_format}, expected yuv420p",
    )
    check("duration_valid", info.duration > 0.05, "Rendered video has no measurable duration")

    if expected_duration and expected_duration > 0 and info.duration > 0:
        tolerance = max(DURATION_TOLERANCE_SECONDS, expected_duration * DURATION_TOLERANCE_RATIO)
        check(
            "duration_matches_source",
            abs(info.duration - expected_duration) <= tolerance,
            f"Duration {info.duration}s differs from source {expected_duration}s by more than {tolerance:.1f}s",
        )

    if source_had_audio:
        check("audio_present", info.has_audio, "Source had audio but the render has none")
        if info.has_audio:
            check("audio_codec_aac", info.audio_codec == "aac", f"Audio codec is {info.audio_codec}, expected aac")

    # Sanity check on bitrate: a 1080x1920 clip below ~150 kbps is almost
    # certainly a broken/black render.
    if info.duration > 0:
        effective_bitrate = size * 8 / info.duration
        check(
            "bitrate_reasonable",
            effective_bitrate > 150_000,
            f"Effective bitrate {effective_bitrate / 1000:.0f} kbps is too low for 1080x1920",
        )

    report.issues = [issue for issue in report.issues if issue]
    logger.info(
        "quality_check_complete",
        extra={"quality_ok": report.ok, "quality_issues": report.issues},
    )
    return report
