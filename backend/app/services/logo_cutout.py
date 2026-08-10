"""Optional white-background removal for uploaded brand logos.

JPEG has no alpha channel, so a logo saved that way renders as an opaque
rectangle over the video. This turns a near-white background into transparency
so the logo sits cleanly on the footage.

It is deliberately opt-in: a design that legitimately contains white would lose
those areas too, which is why the upload endpoint defaults it off and only warns.
"""

from __future__ import annotations

from pathlib import Path

from app.logging_config import get_logger

logger = get_logger(__name__)

# A pixel counts as background when every channel is at least this bright.
_WHITE_THRESHOLD = 240
# Below this the pixel is fully kept; between the two it fades, which softens
# the edge instead of leaving the hard staircase a single cutoff produces.
_SOFT_THRESHOLD = 200


def remove_white_background(source: Path, target: Path) -> bool:
    """Write ``source`` to ``target`` with near-white pixels made transparent.

    Only pixels connected to the border are cleared, so white *inside* the mark
    (an eye, a counter in a letter, a white glyph on a dark badge) survives.
    Returns True when a cutout was written, False when the image was left alone.
    """
    from PIL import Image

    try:
        with Image.open(source) as raw:
            img = raw.convert("RGBA")
    except Exception as exc:  # noqa: BLE001 - never fail an upload over this
        logger.warning("cutout_open_failed", extra={"error": str(exc)})
        return False

    width, height = img.size
    pixels = img.load()
    if pixels is None:  # pragma: no cover - defensive
        return False

    def is_background(x: int, y: int) -> bool:
        r, g, b, a = pixels[x, y]
        return a > 0 and r >= _WHITE_THRESHOLD and g >= _WHITE_THRESHOLD and b >= _WHITE_THRESHOLD

    # Flood-fill inward from the border; interior white is never reached.
    stack = [(x, y) for x in range(width) for y in (0, height - 1)]
    stack += [(x, y) for y in range(height) for x in (0, width - 1)]
    seen = set()
    cleared = 0

    while stack:
        x, y = stack.pop()
        if (x, y) in seen or not (0 <= x < width and 0 <= y < height):
            continue
        seen.add((x, y))
        if not is_background(x, y):
            continue
        r, g, b, _a = pixels[x, y]
        brightness = min(r, g, b)
        if brightness >= _WHITE_THRESHOLD:
            pixels[x, y] = (r, g, b, 0)
        else:
            span = max(1, _WHITE_THRESHOLD - _SOFT_THRESHOLD)
            fade = int(255 * (_WHITE_THRESHOLD - brightness) / span)
            pixels[x, y] = (r, g, b, max(0, min(255, fade)))
        cleared += 1
        stack.extend(((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)))

    if not cleared:
        logger.info("cutout_no_background_found")
        return False

    try:
        img.save(target, format="PNG")
    except Exception as exc:  # noqa: BLE001
        logger.warning("cutout_save_failed", extra={"error": str(exc)})
        return False

    logger.info(
        "cutout_applied",
        extra={"pixels_cleared": cleared, "total_pixels": width * height},
    )
    return True
