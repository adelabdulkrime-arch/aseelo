"""Named output qualities, resolved to encoder settings at render time.

The video row stores a name ("balanced"), not a resolution and a CRF. The
hardware this runs on is the thing that decides what a sensible "high" is, and
that changes when the host does - so the meaning lives here rather than being
frozen into every row ever created.

Deliberately no 4K option. This host renders on a single core; offering a
quality it cannot deliver in reasonable time is a worse experience than not
offering it, because one such job blocks the queue for everyone.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.config import settings


@dataclass(frozen=True)
class QualityPreset:
    slug: str
    width: int
    height: int
    crf: int
    preset: str


# CRF is logarithmic: +3 is roughly half the bitrate. 26/23/20 spans "clearly
# compressed" to "indistinguishable from source" for 9:16 phone footage.
PRESETS: dict[str, QualityPreset] = {
    "fast": QualityPreset("fast", 720, 1280, 26, "veryfast"),
    "balanced": QualityPreset("balanced", 1080, 1920, 23, "veryfast"),
    "high": QualityPreset("high", 1080, 1920, 20, "medium"),
}

DEFAULT_QUALITY = "balanced"


def resolve(slug: str | None) -> QualityPreset:
    """Look up a preset, falling back to the default for anything unknown.

    Never raises: an unrecognised value on an old row must not fail a render.
    """
    preset = PRESETS.get((slug or "").lower()) or PRESETS[DEFAULT_QUALITY]

    # The canvas is fixed by the template, so a preset must never enlarge it -
    # upscaling past the composed overlay would only soften the text.
    if preset.width > settings.output_width or preset.height > settings.output_height:
        return QualityPreset(
            preset.slug,
            settings.output_width,
            settings.output_height,
            preset.crf,
            preset.preset,
        )
    return preset
