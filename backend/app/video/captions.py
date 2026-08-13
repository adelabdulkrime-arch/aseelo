"""Timed captions: one transparent PNG per caption, shown over a time window.

The classic templates flatten every layer into a single overlay that sits on the
video for its whole duration. A caption cannot work that way - it has to appear
and disappear - so each one is rendered to its own RGBA image and handed to
FFmpeg as a separate input, gated by `enable='between(t,start,end)'`.

Band geometry (fractions of frame height), chosen to sit inside the 9:16 safe
areas rather than to add up to 100%:

    top     0.10 - 0.35    hook; clear of the status bar and any platform chrome
    center  0.36 - 0.68    the message; the natural reading line
    bottom  0.69 - 0.86    call to action; above the caption/UI strip that
                           Reels, Shorts and TikTok all overlay at the bottom

The gap under `bottom` is deliberate. A CTA painted at the very bottom of the
frame is the single most common way a vertical video gets its text covered by
the platform's own interface.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from PIL import Image

from app.logging_config import get_logger
from app.video.compose import BrandContext, style_from_config
from app.video.text import render_text_layer

logger = get_logger(__name__)

# (top, bottom) as a fraction of frame height.
BANDS: dict[str, tuple[float, float]] = {
    "top": (0.10, 0.35),
    "center": (0.36, 0.68),
    "bottom": (0.69, 0.86),
}

# Horizontal inset, as a fraction of width, on each side.
SIDE_INSET = 0.08

# How long an entry/exit animation runs. Long enough to read as motion, short
# enough that a 1.5s caption is still legible for most of its life.
ANIMATION_SECONDS = 0.4

_DEFAULT_STYLE: dict[str, Any] = {
    "bold": True,
    "size": 82,
    "min_size": 34,
    "color": "$white",
    "align": "center",
    "line_spacing": 1.25,
    "shadow": True,
    "shadow_alpha": 0.65,
    "shadow_offset": [0, 4],
    "max_lines": 4,
}


@dataclass
class RenderedCaption:
    """One caption, rasterised and ready to be overlaid."""

    caption_id: str
    path: Path
    start_time: float
    end_time: float
    position: str
    animation: str
    x: int
    y: int


def band_box(position: str, size: tuple[int, int]) -> tuple[int, int, int, int]:
    """Pixel box (x, y, w, h) for a named band on a canvas of ``size``."""
    width, height = size
    top_fraction, bottom_fraction = BANDS.get(position, BANDS["center"])
    inset = int(width * SIDE_INSET)
    x = inset
    y = int(height * top_fraction)
    w = max(1, width - 2 * inset)
    h = max(1, int(height * bottom_fraction) - y)
    return x, y, w, h


def render_captions(
    captions: list[dict[str, Any]],
    brand: BrandContext,
    size: tuple[int, int],
    workdir: Path,
    style_overrides: dict[str, Any] | None = None,
) -> list[RenderedCaption]:
    """Rasterise each caption to its own transparent PNG in ``workdir``.

    A caption whose text renders to nothing is skipped rather than emitted as an
    empty overlay, so it costs no FFmpeg filter at render time.
    """
    style_config = {**_DEFAULT_STYLE, **(style_overrides or {})}
    rendered: list[RenderedCaption] = []

    for index, caption in enumerate(captions):
        content = str(caption.get("content", "")).strip()
        if not content:
            continue

        position = str(caption.get("position", "center"))
        x, y, w, h = band_box(position, size)

        style = style_from_config(style_config, brand)
        layer = render_text_layer(content, style, w, h)

        canvas = Image.new("RGBA", size, (0, 0, 0, 0))
        canvas.alpha_composite(layer.image, dest=(x, y))

        path = workdir / f"caption-{index:02d}.png"
        canvas.save(path)

        rendered.append(
            RenderedCaption(
                caption_id=str(caption.get("id", f"txt_{index}")),
                path=path,
                start_time=float(caption.get("start_time", 0.0)),
                end_time=float(caption.get("end_time", 0.0)),
                position=position,
                animation=str(caption.get("animation", "fade")),
                x=x,
                y=y,
            )
        )

    logger.info(
        "captions_rendered",
        extra={"requested": len(captions), "rendered": len(rendered)},
    )
    return rendered
