"""Arabic-first text rendering: direction, shaping, wrapping, auto-fit."""

from __future__ import annotations

import pytest

from app.video.fonts import covers, resolve_font
from app.video.text import (
    TextStyle,
    base_direction,
    contains_arabic,
    contains_rtl,
    fit_text,
    load_font,
    parse_color,
    prepare_display_text,
    render_text_layer,
    text_engine_info,
    wrap_text,
)

ARABIC = "عروضنا الجديدة متوفرة الآن"
MIXED = "عرض خاص - 50% OFF"
ENGLISH = "Our new offers are available now"


def test_detects_arabic_and_rtl():
    assert contains_arabic(ARABIC)
    assert contains_rtl(ARABIC)
    assert contains_arabic(MIXED)
    assert not contains_arabic(ENGLISH)
    assert not contains_rtl(ENGLISH)


def test_base_direction_follows_first_strong_character():
    assert base_direction(ARABIC) == "rtl"
    assert base_direction(MIXED) == "rtl"
    assert base_direction(ENGLISH) == "ltr"
    assert base_direction("50% OFF عرض") == "ltr"


def test_prepare_display_text_is_lossless_for_latin():
    assert prepare_display_text(ENGLISH) == ENGLISH


def test_prepare_display_text_produces_renderable_arabic():
    """Either raqm shapes natively (identity) or reshaper emits presentation forms."""
    display = prepare_display_text(ARABIC)
    assert display
    engine = text_engine_info()
    if engine["raqm"]:
        assert display == ARABIC
    else:
        # Reshaped Arabic lands in the presentation-forms blocks.
        assert any(0xFE70 <= ord(ch) <= 0xFEFF or 0xFB50 <= ord(ch) <= 0xFDFF for ch in display)


@pytest.mark.parametrize("text", [ARABIC, MIXED, ENGLISH])
def test_render_text_layer_produces_visible_pixels(text):
    style = TextStyle(size=72, min_size=24, color="#FFFFFF")
    rendered = render_text_layer(text, style, 900, 400)
    assert rendered.image.size == (900, 400)
    assert rendered.line_count >= 1
    # Something was actually drawn: the alpha channel is not entirely empty.
    assert rendered.image.getchannel("A").getbbox() is not None


def test_empty_text_renders_transparent_layer():
    rendered = render_text_layer("   ", TextStyle(), 400, 200)
    assert rendered.image.getchannel("A").getbbox() is None


def test_long_text_shrinks_to_fit_the_box():
    long_text = " ".join([ARABIC] * 12)
    style = TextStyle(size=96, min_size=20, max_lines=5)
    _font, lines, size = fit_text(long_text, style, 800, 400)
    assert size <= style.size
    assert len(lines) <= style.max_lines


def test_wrap_breaks_an_unbreakably_long_word():
    font = load_font(None, 48)
    lines = wrap_text("A" * 200, font, 300, "ltr")
    assert len(lines) > 1


def test_explicit_newlines_are_preserved():
    font = load_font(None, 40)
    lines = wrap_text("first\nsecond", font, 2000, "ltr")
    assert lines == ["first", "second"]


@pytest.mark.parametrize(
    "text",
    [MIXED, ENGLISH, ARABIC, "50% OFF", "Tel: +964 770 000 0000", "aseelo.example"],
)
def test_resolved_font_covers_every_character(text):
    """Pillow does no font fallback, so one file must cover the whole string.

    The Arabic-only Noto families have no Latin or '%' glyphs; picking one for a
    mixed headline used to render "OFF" as tofu boxes.
    """
    for bold in (False, True):
        path = resolve_font("noto-sans-arabic", bold=bold, text=text)
        missing = [ch for ch in text if not ch.isspace() and not covers(path, ch)]
        assert not missing, f"{path.name} cannot render {missing!r} from {text!r}"


def test_arabic_only_text_still_prefers_the_requested_family():
    path = resolve_font("noto-sans-arabic", text=ARABIC)
    assert "NotoSansArabic" in path.stem


def test_parse_color_forms():
    assert parse_color("#FFF") == (255, 255, 255, 255)
    assert parse_color("#1E88E5") == (30, 136, 229, 255)
    assert parse_color("#1E88E580")[3] == 0x80
    assert parse_color("#000000", alpha=0.5)[3] == 127
    with pytest.raises(ValueError):
        parse_color("#12345")
