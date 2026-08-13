"""Optional background removal for uploaded brand logos.

JPEG has no alpha channel, so a logo saved that way renders as an opaque
rectangle over the video. This turns a flat background into transparency so the
logo sits cleanly on the footage.

Two modes, because the original white-only rule turned out to be too narrow -
a real customer logo arrived on a dark grey (48,48,48) plate that the white
test could never match:

``white``
    The original behaviour, unchanged. Clears near-white only.
``auto`` (default)
    Samples the actual corner colour and clears whatever is there, white or not.

Both are still opt-in and both flood-fill inward from the border, so colour that
belongs *inside* the mark survives either way.
"""

from __future__ import annotations

from collections import Counter
from pathlib import Path
from typing import Literal

from app.logging_config import get_logger

logger = get_logger(__name__)

CutoutMode = Literal["auto", "white"]

# A pixel counts as white background when every channel is at least this bright.
_WHITE_THRESHOLD = 240
# Below this the pixel is fully kept; between the two it fades, which softens
# the edge instead of leaving the hard staircase a single cutoff produces.
_SOFT_THRESHOLD = 200

# How far a pixel may sit from the sampled background colour and still count as
# background. Euclidean distance in RGB. Wide enough to absorb JPEG ringing
# around the mark, narrow enough not to eat a mid-tone in the design itself.
_AUTO_TOLERANCE = 42
# Beyond this the pixel is kept outright; between the two it fades.
_AUTO_SOFT_TOLERANCE = 78


def _sample_background(pixels, width: int, height: int) -> tuple[int, int, int]:
    """Most common colour along the border - the backdrop the mark sits on.

    Sampling the whole border rather than one corner means a logo that happens
    to touch a corner cannot hijack the reading.
    """
    votes: Counter[tuple[int, int, int]] = Counter()
    step = max(1, min(width, height) // 64)
    for x in range(0, width, step):
        for y in (0, height - 1):
            votes[pixels[x, y][:3]] += 1
    for y in range(0, height, step):
        for x in (0, width - 1):
            votes[pixels[x, y][:3]] += 1
    return votes.most_common(1)[0][0]


def _distance(a: tuple[int, int, int], b: tuple[int, int, int]) -> float:
    return sum((a[i] - b[i]) ** 2 for i in range(3)) ** 0.5


def remove_background(
    source: Path, target: Path, *, mode: CutoutMode = "auto"
) -> bool:
    """Write ``source`` to ``target`` with its flat background made transparent.

    Only pixels connected to the border are cleared, so colour *inside* the mark
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

    backdrop = _sample_background(pixels, width, height) if mode == "auto" else None

    def alpha_for(x: int, y: int) -> int | None:
        """New alpha for a border-connected pixel, or None to keep it opaque."""
        r, g, b, a = pixels[x, y]
        if a == 0:
            return None
        if mode == "white":
            if min(r, g, b) >= _WHITE_THRESHOLD:
                return 0
            if min(r, g, b) >= _SOFT_THRESHOLD:
                span = _WHITE_THRESHOLD - _SOFT_THRESHOLD
                return max(0, min(255, int(255 * (_WHITE_THRESHOLD - min(r, g, b)) / span)))
            return None

        assert backdrop is not None
        distance = _distance((r, g, b), backdrop)
        if distance <= _AUTO_TOLERANCE:
            return 0
        if distance <= _AUTO_SOFT_TOLERANCE:
            span = _AUTO_SOFT_TOLERANCE - _AUTO_TOLERANCE
            return max(0, min(255, int(255 * (distance - _AUTO_TOLERANCE) / span)))
        return None

    # Flood-fill inward from the border; interior colour is never reached.
    stack = [(x, y) for x in range(width) for y in (0, height - 1)]
    stack += [(x, y) for y in range(height) for x in (0, width - 1)]
    seen: set[tuple[int, int]] = set()
    cleared = 0

    while stack:
        x, y = stack.pop()
        if (x, y) in seen or not (0 <= x < width and 0 <= y < height):
            continue
        seen.add((x, y))
        new_alpha = alpha_for(x, y)
        if new_alpha is None:
            continue
        r, g, b, _a = pixels[x, y]
        pixels[x, y] = (r, g, b, new_alpha)
        cleared += 1
        stack.extend(((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)))

    if not cleared:
        logger.info("cutout_no_background_found", extra={"mode": mode})
        return False

    # A logo that is almost entirely "background" means the sampled colour was
    # the mark itself. Writing that would hand the user a blank image, so keep
    # the original instead.
    if cleared > 0.97 * width * height:
        logger.warning(
            "cutout_would_erase_everything",
            extra={"mode": mode, "cleared": cleared, "total": width * height},
        )
        return False

    try:
        img.save(target, format="PNG")
    except Exception as exc:  # noqa: BLE001
        logger.warning("cutout_save_failed", extra={"error": str(exc)})
        return False

    logger.info(
        "cutout_applied",
        extra={
            "mode": mode,
            "backdrop": backdrop,
            "pixels_cleared": cleared,
            "total_pixels": width * height,
        },
    )
    return True


def remove_white_background(source: Path, target: Path) -> bool:
    """Backwards-compatible alias for the original white-only behaviour."""
    return remove_background(source, target, mode="white")
