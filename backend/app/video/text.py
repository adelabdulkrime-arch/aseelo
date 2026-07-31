"""Arabic-first text rendering.

FFmpeg's ``drawtext`` filter passes strings straight to FreeType with no
HarfBuzz shaping and no bidirectional reordering, so Arabic comes out as
disconnected, reversed letters. ASEELO therefore renders every text layer to a
transparent PNG with Pillow and composites it with FFmpeg's ``overlay`` filter:

* When Pillow is built with **libraqm** (HarfBuzz + FriBidi) shaping and the
  bidi algorithm are handled natively - the correct approach.
* Otherwise we fall back to ``arabic-reshaper`` + ``python-bidi``, which
  substitutes Arabic presentation forms and reorders runs manually.

Both paths support Arabic, English and mixed strings, RTL and LTR.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Literal

from PIL import Image, ImageDraw, ImageFont, features

from app.logging_config import get_logger
from app.video.fonts import resolve_font

logger = get_logger(__name__)

Align = Literal["start", "center", "end", "left", "right"]
Direction = Literal["rtl", "ltr"]

# Arabic, Arabic Supplement/Extended, Presentation Forms A/B, plus Hebrew/Thaana.
_RTL_RANGES = (
    (0x0590, 0x05FF),
    (0x0600, 0x06FF),
    (0x0700, 0x074F),
    (0x0750, 0x077F),
    (0x0780, 0x07BF),
    (0x08A0, 0x08FF),
    (0xFB1D, 0xFDFF),
    (0xFE70, 0xFEFF),
)

_ARABIC_RANGES = (
    (0x0600, 0x06FF),
    (0x0750, 0x077F),
    (0x08A0, 0x08FF),
    (0xFB50, 0xFDFF),
    (0xFE70, 0xFEFF),
)

_WS = re.compile(r"[ \t ]+")


@lru_cache
def raqm_available() -> bool:
    try:
        return bool(features.check("raqm"))
    except Exception:  # noqa: BLE001
        return False


def _in_ranges(codepoint: int, ranges: tuple[tuple[int, int], ...]) -> bool:
    return any(low <= codepoint <= high for low, high in ranges)


def contains_arabic(text: str) -> bool:
    return any(_in_ranges(ord(ch), _ARABIC_RANGES) for ch in text)


def contains_rtl(text: str) -> bool:
    return any(_in_ranges(ord(ch), _RTL_RANGES) for ch in text)


def base_direction(text: str) -> Direction:
    """Resolve the paragraph direction from the first strong character (UAX#9 P2/P3)."""
    for ch in text:
        bidi = unicodedata.bidirectional(ch)
        if bidi in {"R", "AL"}:
            return "rtl"
        if bidi == "L":
            return "ltr"
    return "ltr"


# ---------------------------------------------------------------------------
# Shaping
# ---------------------------------------------------------------------------
@lru_cache
def _reshaper():
    import arabic_reshaper

    return arabic_reshaper.ArabicReshaper(
        configuration={"delete_harakat": False, "support_ligatures": True}
    )


def _get_display(text: str) -> str:
    # python-bidi moved get_display to the package root in 0.5+.
    try:
        from bidi import get_display  # type: ignore[attr-defined]
    except ImportError:  # pragma: no cover - older python-bidi
        from bidi.algorithm import get_display  # type: ignore[no-redef]
    return get_display(text)


def prepare_display_text(text: str) -> str:
    """Return a string ready to be handed to the glyph rasteriser.

    With libraqm this is the identity function (raqm shapes and reorders).
    Without it, Arabic is reshaped into presentation forms and reordered.
    """
    if raqm_available() or not contains_rtl(text):
        return text
    shaped = _reshaper().reshape(text) if contains_arabic(text) else text
    return _get_display(shaped)


# ---------------------------------------------------------------------------
# Styling
# ---------------------------------------------------------------------------
def parse_color(value: str | tuple, alpha: float | None = None) -> tuple[int, int, int, int]:
    """Parse ``#RGB``/``#RRGGBB``/``#RRGGBBAA`` (or a tuple) into RGBA."""
    if isinstance(value, tuple | list):
        parts = list(value) + [255] * (4 - len(value))
        rgba = tuple(int(max(0, min(255, p))) for p in parts[:4])
    else:
        text = str(value).strip().lstrip("#")
        if len(text) == 3:
            text = "".join(ch * 2 for ch in text)
        if len(text) == 6:
            text += "ff"
        if len(text) != 8:
            raise ValueError(f"Invalid color: {value!r}")
        rgba = tuple(int(text[i : i + 2], 16) for i in (0, 2, 4, 6))
    if alpha is not None:
        rgba = (*rgba[:3], int(max(0.0, min(1.0, alpha)) * 255))
    return rgba  # type: ignore[return-value]


@dataclass
class TextStyle:
    font_slug: str | None = None
    bold: bool = True
    size: int = 72
    min_size: int = 24
    color: str = "#FFFFFF"
    align: Align = "center"
    line_spacing: float = 1.25
    letter_case: Literal["none", "upper"] = "none"
    stroke_width: int = 0
    stroke_color: str = "#000000"
    shadow: bool = True
    shadow_offset: tuple[int, int] = (0, 3)
    shadow_color: str = "#000000"
    shadow_alpha: float = 0.55
    max_lines: int = 6
    highlight: bool = False
    highlight_color: str = "#000000"
    highlight_alpha: float = 0.45
    highlight_padding: tuple[int, int] = (28, 16)
    highlight_radius: int = 18
    features: list[str] = field(default_factory=list)


@dataclass
class RenderedText:
    image: Image.Image
    width: int
    height: int
    line_count: int
    font_size: int


@lru_cache(maxsize=256)
def _load_font(path: str, size: int) -> ImageFont.FreeTypeFont:
    layout = ImageFont.Layout.RAQM if raqm_available() else ImageFont.Layout.BASIC
    return ImageFont.truetype(path, size=size, layout_engine=layout)


def load_font(
    font_slug: str | None, size: int, *, bold: bool = False, text: str | None = None
) -> ImageFont.FreeTypeFont:
    path: Path = resolve_font(font_slug, bold=bold, text=text)
    return _load_font(str(path), max(6, int(size)))


def measure(font: ImageFont.FreeTypeFont, text: str, direction: Direction) -> float:
    if not text:
        return 0.0
    kwargs = {"direction": direction} if raqm_available() else {}
    try:
        return font.getlength(prepare_display_text(text), **kwargs)  # type: ignore[arg-type]
    except (ValueError, KeyError):
        return font.getlength(prepare_display_text(text))


def line_height(font: ImageFont.FreeTypeFont, spacing: float) -> int:
    ascent, descent = font.getmetrics()
    return max(1, int(round((ascent + descent) * spacing)))


def wrap_text(
    text: str,
    font: ImageFont.FreeTypeFont,
    max_width: int,
    direction: Direction,
) -> list[str]:
    """Greedy word wrap on the *logical* string, honouring explicit newlines."""
    lines: list[str] = []
    for paragraph in text.split("\n"):
        paragraph = _WS.sub(" ", paragraph).strip()
        if not paragraph:
            lines.append("")
            continue

        words = paragraph.split(" ")
        current = ""
        for word in words:
            candidate = f"{current} {word}".strip()
            if measure(font, candidate, direction) <= max_width or not current:
                current = candidate
                # A single word wider than the box must be broken by characters.
                while measure(font, current, direction) > max_width and len(current) > 1:
                    cut = len(current)
                    while cut > 1 and measure(font, current[:cut], direction) > max_width:
                        cut -= 1
                    lines.append(current[:cut])
                    current = current[cut:]
            else:
                lines.append(current)
                current = word
        if current:
            lines.append(current)
    return lines or [""]


def fit_text(
    text: str,
    style: TextStyle,
    max_width: int,
    max_height: int,
) -> tuple[ImageFont.FreeTypeFont, list[str], int]:
    """Shrink the font until the wrapped paragraph fits the safe box."""
    direction = base_direction(text)
    size = max(style.min_size, style.size)
    while size >= style.min_size:
        font = load_font(style.font_slug, size, bold=style.bold, text=text)
        lines = wrap_text(text, font, max_width, direction)
        lh = line_height(font, style.line_spacing)
        if len(lines) <= style.max_lines and lh * len(lines) <= max_height:
            return font, lines, size
        size -= 2
    font = load_font(style.font_slug, style.min_size, bold=style.bold, text=text)
    lines = wrap_text(text, font, max_width, direction)[: style.max_lines]
    return font, lines, style.min_size


def _rounded_rect(
    draw: ImageDraw.ImageDraw,
    box: tuple[float, float, float, float],
    radius: int,
    fill: tuple[int, int, int, int],
) -> None:
    x0, y0, x1, y1 = box
    radius = int(max(0, min(radius, (x1 - x0) / 2, (y1 - y0) / 2)))
    if radius <= 0:
        draw.rectangle(box, fill=fill)
    else:
        draw.rounded_rectangle(box, radius=radius, fill=fill)


def render_text_layer(
    text: str,
    style: TextStyle,
    box_width: int,
    box_height: int,
) -> RenderedText:
    """Render ``text`` into a transparent RGBA image of ``box_width x box_height``.

    The returned image is sized to the layout box so FFmpeg can overlay it at a
    fixed offset without further measurement.
    """
    text = (text or "").strip()
    if style.letter_case == "upper":
        # Arabic has no case; upper() is a no-op there and safe for mixed text.
        text = text.upper()

    canvas = Image.new("RGBA", (max(1, box_width), max(1, box_height)), (0, 0, 0, 0))
    if not text:
        return RenderedText(canvas, box_width, box_height, 0, style.size)

    direction = base_direction(text)
    pad_x, pad_y = style.highlight_padding if style.highlight else (0, 0)
    inner_width = max(16, box_width - 2 * pad_x)
    inner_height = max(16, box_height - 2 * pad_y)

    font, lines, size = fit_text(text, style, inner_width, inner_height)
    lh = line_height(font, style.line_spacing)
    ascent, _descent = font.getmetrics()
    block_height = lh * len(lines)

    draw = ImageDraw.Draw(canvas)
    fill = parse_color(style.color)
    stroke_fill = parse_color(style.stroke_color)
    shadow_fill = parse_color(style.shadow_color, alpha=style.shadow_alpha)

    # Resolve logical alignment against the paragraph direction.
    align = style.align
    if align == "start":
        align = "right" if direction == "rtl" else "left"
    elif align == "end":
        align = "left" if direction == "rtl" else "right"

    widths = [measure(font, line, direction) for line in lines]
    top = (box_height - block_height) / 2

    if style.highlight:
        widest = max(widths) if widths else 0
        if align == "center":
            left = (box_width - widest) / 2
        elif align == "right":
            left = box_width - widest - pad_x
        else:
            left = pad_x
        _rounded_rect(
            draw,
            (left - pad_x, top - pad_y, left + widest + pad_x, top + block_height + pad_y),
            style.highlight_radius,
            parse_color(style.highlight_color, alpha=style.highlight_alpha),
        )

    text_kwargs: dict[str, object] = {"font": font, "anchor": "la"}
    if raqm_available():
        text_kwargs["direction"] = direction
        if style.features:
            text_kwargs["features"] = style.features

    for index, line in enumerate(lines):
        if not line:
            continue
        display = prepare_display_text(line)
        width = widths[index]
        if align == "center":
            x = (box_width - width) / 2
        elif align == "right":
            x = box_width - width - pad_x
        else:
            x = pad_x
        # Baseline-consistent vertical placement using the ascender anchor.
        y = top + index * lh + (lh - (ascent + font.getmetrics()[1])) / 2

        if style.shadow:
            draw.text(
                (x + style.shadow_offset[0], y + style.shadow_offset[1]),
                display,
                fill=shadow_fill,
                **text_kwargs,  # type: ignore[arg-type]
            )
        draw.text(
            (x, y),
            display,
            fill=fill,
            stroke_width=style.stroke_width or 0,
            stroke_fill=stroke_fill if style.stroke_width else None,
            **text_kwargs,  # type: ignore[arg-type]
        )

    return RenderedText(canvas, box_width, box_height, len(lines), size)


def text_engine_info() -> dict[str, object]:
    return {
        "raqm": raqm_available(),
        "freetype": features.version("freetype2"),
        "pillow": features.version("pil"),
        "shaping": "harfbuzz/fribidi (libraqm)" if raqm_available() else "arabic-reshaper + python-bidi",
    }
