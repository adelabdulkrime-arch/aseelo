"""Data-driven template definitions.

Templates are *data*, not code: each one is a JSON document stored in the
``templates`` table and interpreted by :mod:`app.video.compose`. Adding a
template means inserting a row - the renderer never changes.

Colour tokens (``$primary``, ``$secondary``, ``$accent``, ``$white``,
``$black``) are resolved against the user's brand profile at render time, so a
single template automatically reflects every brand.

Layer types
-----------
``fill``      full-canvas flat colour wash
``gradient``  vertical linear gradient band (legibility scrim)
``bar``       solid / rounded rectangle (brand bar)
``text``      Arabic-aware text block, auto-fitted to its box
``logo``      brand logo, aspect-preserving contain inside its box
"""

from __future__ import annotations

from typing import Any

CANVAS = {"width": 1080, "height": 1920}
SAFE_AREA = {"top": 180, "bottom": 320, "left": 72, "right": 72}


def _base(background: dict[str, Any], layers: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "version": 1,
        "canvas": dict(CANVAS),
        "safe_area": dict(SAFE_AREA),
        "background": background,
        "layers": layers,
    }


# ---------------------------------------------------------------------------
# Template 01 - Clean / minimal
# ---------------------------------------------------------------------------
TEMPLATE_01 = _base(
    background={"mode": "cover", "overlay_color": "$black", "overlay_alpha": 0.28},
    layers=[
        {
            "type": "gradient",
            "box": {"x": 0, "y": 1180, "w": 1080, "h": 740},
            "color": "$black",
            "from_alpha": 0.0,
            "to_alpha": 0.80,
        },
        {
            "type": "logo",
            "name": "brand-logo",
            "box": {"x": 430, "y": 150, "w": 220, "h": 220},
            "fit": "contain",
            "opacity": 1.0,
        },
        {
            "type": "text",
            "name": "headline",
            "source": "text_content",
            "box": {"x": 90, "y": 700, "w": 900, "h": 600},
            "style": {
                "bold": True,
                "size": 86,
                "min_size": 40,
                "color": "$white",
                "align": "center",
                "line_spacing": 1.28,
                "shadow": True,
                "shadow_offset": [0, 4],
                "shadow_alpha": 0.6,
                "stroke_width": 0,
                "max_lines": 5,
            },
        },
        {
            "type": "bar",
            "name": "accent-underline",
            "box": {"x": 465, "y": 1348, "w": 150, "h": 8},
            "color": "$accent",
            "alpha": 1.0,
            "radius": 4,
        },
        {
            "type": "text",
            "name": "brand-name",
            "source": "brand_name",
            "box": {"x": 90, "y": 1396, "w": 900, "h": 76},
            "style": {
                "bold": True,
                "size": 48,
                "min_size": 26,
                "color": "$accent",
                "align": "center",
                "max_lines": 1,
                "shadow": True,
            },
        },
        {
            "type": "text",
            "name": "contact",
            "source": "contact_inline",
            "box": {"x": 80, "y": 1482, "w": 920, "h": 64},
            "style": {
                "bold": False,
                "size": 38,
                "min_size": 22,
                "color": "$white",
                "align": "center",
                "max_lines": 1,
                "shadow": True,
            },
        },
        {
            "type": "text",
            "name": "tagline",
            "source": "tagline",
            "box": {"x": 90, "y": 1556, "w": 900, "h": 56},
            "style": {
                "bold": False,
                "size": 32,
                "min_size": 20,
                "color": "$white",
                "color_alpha": 0.85,
                "align": "center",
                "max_lines": 1,
                "shadow": True,
            },
        },
    ],
)

# ---------------------------------------------------------------------------
# Template 02 - Strong headline + bottom brand bar
# ---------------------------------------------------------------------------
TEMPLATE_02 = _base(
    background={
        "mode": "blur_pad",
        "blur_sigma": 28,
        "overlay_color": "$black",
        "overlay_alpha": 0.20,
    },
    layers=[
        {
            "type": "gradient",
            "box": {"x": 0, "y": 0, "w": 1080, "h": 620},
            "color": "$black",
            "from_alpha": 0.72,
            "to_alpha": 0.0,
        },
        {
            "type": "text",
            "name": "headline",
            "source": "text_content",
            "box": {"x": 90, "y": 300, "w": 900, "h": 760},
            "style": {
                "bold": True,
                "size": 104,
                "min_size": 44,
                "color": "$white",
                "align": "start",
                "line_spacing": 1.2,
                "stroke_width": 0,
                "shadow": True,
                "shadow_offset": [0, 5],
                "shadow_alpha": 0.65,
                "max_lines": 6,
            },
        },
        {
            "type": "bar",
            "name": "brand-bar",
            "box": {"x": 0, "y": 1520, "w": 1080, "h": 300},
            "color": "$primary",
            "alpha": 0.94,
            "radius": 0,
        },
        {
            "type": "bar",
            "name": "accent-strip",
            "box": {"x": 0, "y": 1512, "w": 1080, "h": 10},
            "color": "$accent",
            "alpha": 1.0,
            "radius": 0,
        },
        {
            "type": "logo",
            "name": "brand-logo",
            "box": {"x": 80, "y": 1572, "w": 180, "h": 180},
            "fit": "contain",
            "opacity": 1.0,
        },
        {
            "type": "text",
            "name": "brand-name",
            "source": "brand_name",
            "box": {"x": 292, "y": 1576, "w": 708, "h": 80},
            "style": {
                "bold": True,
                "size": 52,
                "min_size": 26,
                "color": "$white",
                "align": "start",
                "max_lines": 1,
                "shadow": False,
            },
        },
        {
            "type": "text",
            "name": "contact",
            "source": "contact_inline",
            "box": {"x": 292, "y": 1664, "w": 708, "h": 60},
            "style": {
                "bold": False,
                "size": 36,
                "min_size": 20,
                "color": "$white",
                "color_alpha": 0.92,
                "align": "start",
                "max_lines": 1,
                "shadow": False,
            },
        },
        # No separate `website` layer here: `contact_inline` above already ends
        # with the website (see _contact_parts), so adding one printed the same
        # URL twice, stacked, inside the brand bar. Caught by looking at a
        # rendered preview — every assertion still passed.
    ],
)

# ---------------------------------------------------------------------------
# Template 03 - Modern promotional
# ---------------------------------------------------------------------------
TEMPLATE_03 = _base(
    background={"mode": "cover", "overlay_color": "$primary", "overlay_alpha": 0.30},
    layers=[
        {
            "type": "gradient",
            "box": {"x": 0, "y": 1280, "w": 1080, "h": 640},
            "color": "$primary",
            "from_alpha": 0.0,
            "to_alpha": 0.88,
        },
        {
            "type": "text",
            "name": "brand-name",
            "source": "brand_name",
            "box": {"x": 80, "y": 170, "w": 640, "h": 84},
            "style": {
                "bold": True,
                "size": 46,
                "min_size": 24,
                "color": "$accent",
                "align": "start",
                "max_lines": 1,
                "shadow": True,
            },
        },
        {
            "type": "logo",
            "name": "brand-logo",
            "box": {"x": 800, "y": 150, "w": 200, "h": 200},
            "fit": "contain",
            "opacity": 1.0,
        },
        {
            "type": "text",
            "name": "headline",
            "source": "text_content",
            "box": {"x": 70, "y": 620, "w": 940, "h": 620},
            "style": {
                "bold": True,
                "size": 96,
                "min_size": 42,
                "color": "$white",
                "align": "center",
                "line_spacing": 1.3,
                "highlight": True,
                "highlight_color": "$secondary",
                "highlight_alpha": 0.82,
                "highlight_padding": [34, 20],
                "highlight_radius": 24,
                "shadow": True,
                "shadow_alpha": 0.5,
                "max_lines": 5,
            },
        },
        {
            "type": "bar",
            "name": "accent-underline",
            "box": {"x": 80, "y": 1400, "w": 200, "h": 10},
            "color": "$accent",
            "alpha": 1.0,
            "radius": 5,
        },
        {
            "type": "text",
            "name": "contact-block",
            "source": "contact_multiline",
            "box": {"x": 80, "y": 1446, "w": 920, "h": 250},
            "style": {
                "bold": False,
                "size": 40,
                "min_size": 22,
                "color": "$white",
                "align": "start",
                "line_spacing": 1.32,
                "max_lines": 4,
                "shadow": True,
            },
        },
        {
            "type": "text",
            "name": "tagline",
            "source": "tagline",
            "box": {"x": 80, "y": 1712, "w": 920, "h": 60},
            "style": {
                "bold": True,
                "size": 34,
                "min_size": 18,
                "color": "$accent",
                "align": "start",
                "max_lines": 1,
                "shadow": True,
            },
        },
    ],
)


TEMPLATE_SEEDS: list[dict[str, Any]] = [
    {
        "slug": "clean-minimal",
        "name": "Template 01 - Clean Minimal",
        "description": (
            "Minimal centred layout: large headline in the middle of the frame, logo at the "
            "top and brand contact details above the bottom safe area."
        ),
        "sort_order": 10,
        "configuration": TEMPLATE_01,
    },
    {
        "slug": "bold-headline",
        "name": "Template 02 - Bold Headline",
        "description": (
            "Strong upper headline over a blurred fill background with a solid bottom brand "
            "bar carrying the logo, brand name, phone/WhatsApp and website."
        ),
        "sort_order": 20,
        "configuration": TEMPLATE_02,
    },
    {
        "slug": "modern-promo",
        "name": "Template 03 - Modern Promo",
        "description": (
            "Promotional layout with a highlighted headline plate in brand colours, logo and "
            "brand name in the header, and a multi-line contact block at the bottom."
        ),
        "sort_order": 30,
        "configuration": TEMPLATE_03,
    },
]
