"""FFmpeg rendering: filter graph, real encode, FFprobe validation.

These tests shell out to the real ffmpeg/ffprobe binaries and encode an actual
clip - there is no mocked renderer here.
"""

from __future__ import annotations

import subprocess

import pytest
from PIL import Image

from app.config import settings
from app.video.compose import BrandContext, build_overlay
from app.video.probe import ProbeError, probe
from app.video.quality import validate_output
from app.video.render import (
    RenderError,
    RenderRequest,
    build_command,
    build_filter_complex,
    render,
)
from app.video.templates import TEMPLATE_SEEDS

ARABIC = "عروضنا الجديدة متوفرة الآن"
MIXED = "عرض خاص - 50% OFF"


def _make_source(path, *, width=1920, height=1080, duration=2, audio=True):
    """Synthesise a landscape test clip with ffmpeg's built-in sources."""
    command = [
        settings.ffmpeg_path,
        "-hide_banner",
        "-loglevel",
        "error",
        "-y",
        "-f",
        "lavfi",
        "-i",
        f"testsrc=size={width}x{height}:rate=30:duration={duration}",
    ]
    if audio:
        command += ["-f", "lavfi", "-i", f"sine=frequency=440:duration={duration}", "-c:a", "aac"]
    command += ["-c:v", "libx264", "-pix_fmt", "yuv420p", "-t", str(duration), str(path)]
    subprocess.run(command, check=True, capture_output=True, timeout=180)
    return path


@pytest.fixture(scope="module")
def source_video(tmp_path_factory):
    return _make_source(tmp_path_factory.mktemp("media") / "source.mp4")


# ---------------------------------------------------------------------------
# Filter graph
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("mode", ["cover", "pad", "blur_pad"])
def test_filter_graph_always_targets_the_output_canvas(mode, tmp_path):
    request = RenderRequest(
        input_path=tmp_path / "in.mp4",
        overlay_path=tmp_path / "ovl.png",
        output_path=tmp_path / "out.mp4",
        duration=5.0,
        has_audio=True,
        background_mode=mode,
    )
    graph = build_filter_complex(request)
    assert "1080:1920" in graph
    assert "[outv]" in graph
    assert "yuv420p" in graph


def test_command_encodes_h264_and_aac_when_audio_present(tmp_path):
    request = RenderRequest(
        input_path=tmp_path / "in.mp4",
        overlay_path=tmp_path / "ovl.png",
        output_path=tmp_path / "out.mp4",
        duration=5.0,
        has_audio=True,
    )
    command = build_command(request)
    assert "libx264" in command
    assert "aac" in command
    assert "+faststart" in command


def test_command_drops_audio_when_source_is_silent(tmp_path):
    request = RenderRequest(
        input_path=tmp_path / "in.mp4",
        overlay_path=tmp_path / "ovl.png",
        output_path=tmp_path / "out.mp4",
        duration=5.0,
        has_audio=False,
    )
    command = build_command(request)
    assert "-an" in command
    assert "aac" not in command


# ---------------------------------------------------------------------------
# Probe
# ---------------------------------------------------------------------------
def test_probe_reads_real_media(source_video):
    info = probe(source_video)
    assert info.video_codec == "h264"
    assert (info.width, info.height) == (1920, 1080)
    assert info.duration == pytest.approx(2.0, abs=0.3)
    assert info.has_audio


def test_probe_rejects_non_media(tmp_path):
    junk = tmp_path / "junk.mp4"
    junk.write_bytes(b"definitely not a video")
    with pytest.raises(ProbeError):
        probe(junk)


# ---------------------------------------------------------------------------
# End-to-end render
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("seed", TEMPLATE_SEEDS, ids=lambda s: s["slug"])
def test_full_render_produces_a_valid_9_16_mp4(seed, source_video, tmp_path):
    logo_path = tmp_path / "logo.png"
    Image.new("RGBA", (400, 400), (245, 183, 0, 255)).save(logo_path)

    brand = BrandContext(
        brand_name="ASEELO",
        phone="+964 770 000 0000",
        website="https://aseelo.example",
        tagline="From Idea to Content",
        logo_path=logo_path,
    )
    overlay_path = tmp_path / f"overlay-{seed['slug']}.png"
    build_overlay(seed["configuration"], brand, ARABIC, "Test").image.save(overlay_path)

    source_info = probe(source_video)
    output_path = tmp_path / f"out-{seed['slug']}.mp4"
    seen: list[float] = []
    result = render(
        RenderRequest(
            input_path=source_video,
            overlay_path=overlay_path,
            output_path=output_path,
            duration=source_info.duration,
            has_audio=source_info.has_audio,
            background_mode=(seed["configuration"]["background"] or {}).get("mode", "cover"),
            preset="ultrafast",
        ),
        progress=seen.append,
    )

    assert result.size_bytes > 0
    # Progress came from ffmpeg's own -progress stream, not a timer.
    assert seen and seen[-1] == 1.0
    assert all(0.0 <= f <= 1.0 for f in seen)

    report = validate_output(
        output_path,
        expected_duration=source_info.duration,
        source_had_audio=source_info.has_audio,
    )
    assert report.ok, report.summary
    assert report.info is not None
    assert (report.info.width, report.info.height) == (1080, 1920)
    assert report.info.video_codec == "h264"
    assert report.info.audio_codec == "aac"


def test_render_of_a_silent_portrait_source(tmp_path):
    source = _make_source(tmp_path / "portrait.mp4", width=720, height=1280, audio=False)
    overlay_path = tmp_path / "overlay.png"
    build_overlay(
        TEMPLATE_SEEDS[1]["configuration"], BrandContext(brand_name="ASEELO"), MIXED
    ).image.save(overlay_path)

    output_path = tmp_path / "out.mp4"
    render(
        RenderRequest(
            input_path=source,
            overlay_path=overlay_path,
            output_path=output_path,
            duration=probe(source).duration,
            has_audio=False,
            preset="ultrafast",
        )
    )
    report = validate_output(output_path, source_had_audio=False)
    assert report.ok, report.summary
    assert not report.info.has_audio


def test_render_fails_loudly_on_a_corrupt_source(tmp_path):
    corrupt = tmp_path / "corrupt.mp4"
    corrupt.write_bytes(b"\x00" * 4096)
    overlay_path = tmp_path / "overlay.png"
    Image.new("RGBA", (1080, 1920), (0, 0, 0, 0)).save(overlay_path)

    with pytest.raises(RenderError):
        render(
            RenderRequest(
                input_path=corrupt,
                overlay_path=overlay_path,
                output_path=tmp_path / "out.mp4",
                duration=2.0,
                has_audio=False,
                preset="ultrafast",
            )
        )


def test_quality_check_rejects_a_missing_output(tmp_path):
    report = validate_output(tmp_path / "nope.mp4")
    assert not report.ok
    assert "missing" in report.summary.lower()


def test_quality_check_rejects_wrong_resolution(source_video):
    """The unmodified 1920x1080 source must fail the 1080x1920 contract."""
    report = validate_output(source_video)
    assert not report.ok
    assert not report.checks["resolution"]
