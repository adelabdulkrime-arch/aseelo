"""Timed captions: validation, band geometry, rasterising and the filter graph."""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError as PydanticValidationError

from app.schemas import Caption, validate_caption_track
from app.video.captions import BANDS, RenderedCaption, band_box, render_captions
from app.video.compose import BrandContext
from app.video.render import RenderRequest, build_command, build_filter_complex


def _caption(**overrides):
    payload = {
        "id": "txt_1",
        "content": "نص تجريبي",
        "start_time": 0.0,
        "end_time": 3.0,
        "position": "center",
        "animation": "fade",
    }
    payload.update(overrides)
    return Caption.model_validate(payload)


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------
def test_caption_must_end_after_it_starts():
    with pytest.raises(PydanticValidationError):
        _caption(start_time=5.0, end_time=5.0)


def test_caption_rejects_a_window_too_short_to_read():
    with pytest.raises(PydanticValidationError):
        _caption(start_time=1.0, end_time=1.1)


def test_overlapping_captions_in_the_same_band_are_rejected():
    track = [
        _caption(id="a", start_time=0.0, end_time=4.0, position="center"),
        _caption(id="b", start_time=3.0, end_time=6.0, position="center"),
    ]
    with pytest.raises(ValueError, match="overlap"):
        validate_caption_track(track)


def test_captions_may_overlap_across_different_bands():
    """A hook on top while a CTA shows at the bottom is a normal design."""
    track = [
        _caption(id="a", start_time=0.0, end_time=5.0, position="top"),
        _caption(id="b", start_time=0.0, end_time=5.0, position="bottom"),
    ]
    assert validate_caption_track(track) == track


def test_duplicate_ids_are_rejected():
    track = [
        _caption(id="same", start_time=0.0, end_time=2.0),
        _caption(id="same", start_time=3.0, end_time=5.0),
    ]
    with pytest.raises(ValueError, match="Duplicate"):
        validate_caption_track(track)


def test_track_length_is_capped():
    track = [
        _caption(id=f"c{i}", start_time=i * 2.0, end_time=i * 2.0 + 1.0) for i in range(13)
    ]
    with pytest.raises(ValueError, match="At most"):
        validate_caption_track(track)


# ---------------------------------------------------------------------------
# Geometry
# ---------------------------------------------------------------------------
def test_bands_do_not_overlap_and_stay_inside_the_frame():
    ordered = sorted(BANDS.values())
    for (_, earlier_bottom), (later_top, _) in zip(ordered, ordered[1:]):
        assert later_top >= earlier_bottom, "bands must not overlap"
    assert all(0.0 <= top < bottom <= 1.0 for top, bottom in BANDS.values())


def test_bottom_band_clears_the_platform_ui_strip():
    """Text at the very bottom of a Reel gets covered by the app's own chrome."""
    _top, bottom = BANDS["bottom"]
    assert bottom <= 0.90


def test_band_box_is_inset_from_the_edges():
    x, y, w, h = band_box("center", (1080, 1920))
    assert x > 0 and w < 1080
    assert y > 0 and y + h < 1920


# ---------------------------------------------------------------------------
# Rasterising
# ---------------------------------------------------------------------------
def test_each_caption_becomes_its_own_transparent_image(tmp_path):
    from PIL import Image

    rendered = render_captions(
        [
            {"id": "a", "content": "الهوك", "start_time": 0.0, "end_time": 3.0, "position": "top"},
            {"id": "b", "content": "CTA", "start_time": 4.0, "end_time": 8.0, "position": "bottom"},
        ],
        BrandContext(),
        (1080, 1920),
        tmp_path,
    )
    assert len(rendered) == 2
    for item in rendered:
        image = Image.open(item.path)
        assert image.size == (1080, 1920)
        assert image.mode == "RGBA"
        # Something was drawn, and the frame is not filled edge to edge.
        assert image.getchannel("A").getbbox() is not None


def test_a_blank_caption_costs_no_overlay(tmp_path):
    rendered = render_captions(
        [{"id": "a", "content": "   ", "start_time": 0.0, "end_time": 3.0}],
        BrandContext(),
        (1080, 1920),
        tmp_path,
    )
    assert rendered == []


# ---------------------------------------------------------------------------
# Filter graph
# ---------------------------------------------------------------------------
def _request(captions):
    return RenderRequest(
        input_path=Path("/tmp/in.mp4"),
        overlay_path=Path("/tmp/ov.png"),
        output_path=Path("/tmp/out.mp4"),
        duration=15.0,
        has_audio=False,
        captions=captions,
    )


def test_graph_is_unchanged_when_there_are_no_captions():
    graph = build_filter_complex(_request([]))
    assert "enable=" not in graph
    assert graph.endswith("[outv]")


def test_each_caption_gets_its_own_gated_overlay():
    captions = [
        RenderedCaption("a", Path("/tmp/c0.png"), 0.0, 3.0, "top", "fade", 0, 0),
        RenderedCaption("b", Path("/tmp/c1.png"), 4.0, 10.0, "center", "none", 0, 0),
    ]
    graph = build_filter_complex(_request(captions))
    assert graph.count("enable=") == 2
    assert "between(t\\,0\\,3)" in graph
    assert "between(t\\,4\\,10)" in graph
    # Caption inputs start after the source video (0) and static overlay (1).
    assert "[2:v]" in graph and "[3:v]" in graph
    assert graph.endswith("[outv]")


def test_animation_is_emitted_only_when_asked_for():
    animated = build_filter_complex(
        _request([RenderedCaption("a", Path("/tmp/c0.png"), 0.0, 3.0, "top", "fade", 0, 0)])
    )
    plain = build_filter_complex(
        _request([RenderedCaption("a", Path("/tmp/c0.png"), 0.0, 3.0, "top", "none", 0, 0)])
    )
    assert "fade=t=in" in animated and "fade=t=out" in animated
    assert "fade=" not in plain


def test_animation_never_outlasts_a_short_caption():
    """A 0.6s caption must not spend 0.4s fading in and 0.4s fading out."""
    graph = build_filter_complex(
        _request([RenderedCaption("a", Path("/tmp/c0.png"), 0.0, 0.6, "top", "fade", 0, 0)])
    )
    assert "d=0.2" in graph


def test_command_feeds_every_caption_as_a_looped_input():
    captions = [
        RenderedCaption("a", Path("/tmp/c0.png"), 0.0, 3.0, "top", "fade", 0, 0),
        RenderedCaption("b", Path("/tmp/c1.png"), 4.0, 9.0, "bottom", "fade", 0, 0),
    ]
    command = build_command(_request(captions))
    assert command.count("-loop") == 2
    assert str(Path("/tmp/c0.png")) in command
    assert str(Path("/tmp/c1.png")) in command
