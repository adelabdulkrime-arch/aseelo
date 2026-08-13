"""Layer composition: turn a template document + brand identity into one PNG.

The conceptual layer order from the product spec is preserved:

1. Video            (bottom - produced by FFmpeg, never touched here)
2. Background / FX  (tint + gradient scrims)
3. Text
4. Logo
5. Contact information
6. Brand elements
7. Final overlay

Everything above the video is flattened into a single full-canvas RGBA image so
FFmpeg needs exactly one ``overlay`` filter. The downloaded MP4 is therefore a
flat file with no editable layers.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw

from app.logging_config import get_logger
from app.video.text import TextStyle, contains_arabic, parse_color, render_text_layer

logger = get_logger(__name__)

DEFAULT_CANVAS = (1080, 1920)
SEPARATOR = "  |  "


@dataclass
class BrandContext:
    """Brand identity snapshot used for a single render."""

    brand_name: str = "My Brand"
    primary_color: str = "#0F172A"
    secondary_color: str = "#1E88E5"
    accent_color: str = "#F5B700"
    font: str | None = None
    phone: str | None = None
    whatsapp: str | None = None
    website: str | None = None
    address: str | None = None
    tagline: str | None = None
    social_media: dict[str, str] = field(default_factory=dict)
    logo_path: Path | None = None

    @classmethod
    def from_model(cls, brand: Any, logo_path: Path | None = None) -> "BrandContext":
        return cls(
            brand_name=brand.brand_name or "My Brand",
            primary_color=brand.primary_color,
            secondary_color=brand.secondary_color,
            accent_color=brand.accent_color,
            font=brand.font,
            phone=brand.phone,
            whatsapp=brand.whatsapp,
            website=brand.website,
            address=brand.address,
            tagline=brand.tagline,
            social_media=dict(brand.social_media or {}),
            logo_path=logo_path,
        )

    @classmethod
    def from_snapshot(cls, data: dict[str, Any], logo_path: Path | None = None) -> "BrandContext":
        known = {
            "brand_name",
            "primary_color",
            "secondary_color",
            "accent_color",
            "font",
            "phone",
            "whatsapp",
            "website",
            "address",
            "tagline",
            "social_media",
        }
        payload = {k: v for k, v in (data or {}).items() if k in known and v is not None}
        return cls(**payload, logo_path=logo_path)  # type: ignore[arg-type]

    def to_snapshot(self) -> dict[str, Any]:
        return {
            "brand_name": self.brand_name,
            "primary_color": self.primary_color,
            "secondary_color": self.secondary_color,
            "accent_color": self.accent_color,
            "font": self.font,
            "phone": self.phone,
            "whatsapp": self.whatsapp,
            "website": self.website,
            "address": self.address,
            "tagline": self.tagline,
            "social_media": self.social_media,
        }


# ---------------------------------------------------------------------------
# Token / colour resolution
# ---------------------------------------------------------------------------
def resolve_color(token: str | None, brand: BrandContext, fallback: str = "#FFFFFF") -> str:
    if not token:
        return fallback
    mapping = {
        "$primary": brand.primary_color,
        "$secondary": brand.secondary_color,
        "$accent": brand.accent_color,
        "$white": "#FFFFFF",
        "$black": "#000000",
    }
    return mapping.get(token, token)


def _with_alpha(color: str, alpha: float | None) -> str:
    if alpha is None:
        return color
    r, g, b, _a = parse_color(color)
    return f"#{r:02X}{g:02X}{b:02X}{int(max(0.0, min(1.0, alpha)) * 255):02X}"


# ---------------------------------------------------------------------------
# Text sources
# ---------------------------------------------------------------------------
def _labels(arabic: bool) -> dict[str, str]:
    if arabic:
        return {"phone": "هاتف", "whatsapp": "واتساب", "website": "الموقع", "address": "العنوان"}
    return {"phone": "Tel", "whatsapp": "WhatsApp", "website": "Web", "address": "Address"}


def _contact_parts(brand: BrandContext, arabic: bool) -> list[str]:
    labels = _labels(arabic)
    parts: list[str] = []
    if brand.phone:
        parts.append(f"{labels['phone']}: {brand.phone}")
    if brand.whatsapp and brand.whatsapp != brand.phone:
        parts.append(f"{labels['whatsapp']}: {brand.whatsapp}")
    if brand.website:
        parts.append(brand.website.replace("https://", "").replace("http://", ""))
    return parts


def resolve_source(source: str, brand: BrandContext, text_content: str, title: str | None) -> str:
    """Resolve a template layer ``source`` key into a concrete string."""
    arabic = contains_arabic(text_content) or contains_arabic(brand.brand_name or "")

    if source == "text_content":
        return text_content
    if source == "title":
        return title or ""
    if source == "brand_name":
        return brand.brand_name or ""
    if source == "tagline":
        return brand.tagline or ""
    if source == "phone":
        return brand.phone or ""
    if source == "whatsapp":
        return brand.whatsapp or ""
    if source == "website":
        return (brand.website or "").replace("https://", "").replace("http://", "")
    if source == "address":
        return brand.address or ""
    if source == "contact_inline":
        return SEPARATOR.join(_contact_parts(brand, arabic))
    if source == "contact_multiline":
        lines = _contact_parts(brand, arabic)
        if brand.address:
            lines.append(brand.address)
        return "\n".join(lines)
    if source == "social_inline":
        return SEPARATOR.join(f"{k}: {v}" for k, v in (brand.social_media or {}).items())
    if source.startswith("literal:"):
        return source[len("literal:") :]
    logger.warning("unknown_text_source", extra={"source": source})
    return ""


# ---------------------------------------------------------------------------
# Style mapping
# ---------------------------------------------------------------------------
_STYLE_KEYS = {
    "bold",
    "size",
    "min_size",
    "align",
    "line_spacing",
    "letter_case",
    "stroke_width",
    "shadow",
    "shadow_alpha",
    "max_lines",
    "highlight",
    "highlight_alpha",
    "highlight_radius",
    "features",
}


def style_from_config(raw: dict[str, Any], brand: BrandContext) -> TextStyle:
    payload: dict[str, Any] = {k: v for k, v in raw.items() if k in _STYLE_KEYS}
    payload["font_slug"] = raw.get("font_slug") or brand.font
    payload["color"] = _with_alpha(
        resolve_color(raw.get("color", "$white"), brand), raw.get("color_alpha")
    )
    payload["stroke_color"] = resolve_color(raw.get("stroke_color", "$black"), brand, "#000000")
    payload["shadow_color"] = resolve_color(raw.get("shadow_color", "$black"), brand, "#000000")
    payload["highlight_color"] = resolve_color(
        raw.get("highlight_color", "$primary"), brand, "#000000"
    )
    if offset := raw.get("shadow_offset"):
        payload["shadow_offset"] = (int(offset[0]), int(offset[1]))
    if padding := raw.get("highlight_padding"):
        payload["highlight_padding"] = (int(padding[0]), int(padding[1]))
    return TextStyle(**payload)


# ---------------------------------------------------------------------------
# Primitive layers
# ---------------------------------------------------------------------------
def _box(raw: dict[str, Any], canvas: tuple[int, int]) -> tuple[int, int, int, int]:
    x = int(raw.get("x", 0))
    y = int(raw.get("y", 0))
    w = int(raw.get("w", canvas[0]))
    h = int(raw.get("h", canvas[1]))
    return x, y, max(1, w), max(1, h)


def _composite(canvas: Image.Image, layer: Image.Image, x: int, y: int) -> None:
    """Alpha-composite ``layer`` at (x, y), clipping to the canvas bounds."""
    cw, ch = canvas.size
    lw, lh = layer.size

    src_x = max(0, -x)
    src_y = max(0, -y)
    dst_x = max(0, x)
    dst_y = max(0, y)
    width = min(lw - src_x, cw - dst_x)
    height = min(lh - src_y, ch - dst_y)
    if width <= 0 or height <= 0:
        return
    if (src_x, src_y, width, height) != (0, 0, lw, lh):
        layer = layer.crop((src_x, src_y, src_x + width, src_y + height))
    canvas.alpha_composite(layer, dest=(dst_x, dst_y))


def _draw_gradient(canvas: Image.Image, layer_cfg: dict[str, Any], brand: BrandContext) -> None:
    x, y, w, h = _box(layer_cfg.get("box", {}), canvas.size)
    color = parse_color(resolve_color(layer_cfg.get("color", "$black"), brand, "#000000"))
    a0 = float(layer_cfg.get("from_alpha", 0.0))
    a1 = float(layer_cfg.get("to_alpha", 1.0))

    band = Image.new("RGBA", (1, h))
    pixels = band.load()
    assert pixels is not None  # noqa: S101 - type narrowing, not a runtime check
    for row in range(h):
        t = row / max(1, h - 1)
        alpha = int(max(0.0, min(1.0, a0 + (a1 - a0) * t)) * 255)
        pixels[0, row] = (*color[:3], alpha)
    _composite(canvas, band.resize((w, h), Image.Resampling.BILINEAR), x, y)


def _draw_bar(canvas: Image.Image, layer_cfg: dict[str, Any], brand: BrandContext) -> None:
    x, y, w, h = _box(layer_cfg.get("box", {}), canvas.size)
    fill = parse_color(
        resolve_color(layer_cfg.get("color", "$primary"), brand, "#000000"),
        alpha=float(layer_cfg.get("alpha", 1.0)),
    )
    radius = int(layer_cfg.get("radius", 0))
    bar = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    draw = ImageDraw.Draw(bar)
    if radius > 0:
        draw.rounded_rectangle((0, 0, w - 1, h - 1), radius=min(radius, w // 2, h // 2), fill=fill)
    else:
        draw.rectangle((0, 0, w - 1, h - 1), fill=fill)
    _composite(canvas, bar, x, y)


def _draw_fill(canvas: Image.Image, layer_cfg: dict[str, Any], brand: BrandContext) -> None:
    fill = parse_color(
        resolve_color(layer_cfg.get("color", "$black"), brand, "#000000"),
        alpha=float(layer_cfg.get("alpha", 0.2)),
    )
    _composite(canvas, Image.new("RGBA", canvas.size, fill), 0, 0)


def _draw_logo(canvas: Image.Image, layer_cfg: dict[str, Any], brand: BrandContext) -> bool:
    if not brand.logo_path:
        return False
    path = Path(brand.logo_path)
    if not path.exists():
        logger.warning("logo_missing_on_disk", extra={"logo_path": str(path)})
        return False

    x, y, w, h = _box(layer_cfg.get("box", {}), canvas.size)
    try:
        with Image.open(path) as raw:
            logo = raw.convert("RGBA")
    except Exception as exc:  # noqa: BLE001 - a broken logo must not fail the render
        logger.warning("logo_unreadable", extra={"error": str(exc)})
        return False

    if layer_cfg.get("fit", "contain") == "cover":
        scale = max(w / logo.width, h / logo.height)
    else:
        scale = min(w / logo.width, h / logo.height)
    new_size = (max(1, int(logo.width * scale)), max(1, int(logo.height * scale)))
    logo = logo.resize(new_size, Image.Resampling.LANCZOS)

    opacity = float(layer_cfg.get("opacity", 1.0))
    if opacity < 1.0:
        alpha = logo.getchannel("A").point(lambda v: int(v * opacity))
        logo.putalpha(alpha)

    offset_x = x + (w - logo.width) // 2
    offset_y = y + (h - logo.height) // 2
    _composite(canvas, logo, offset_x, offset_y)
    return True


def _draw_text(
    canvas: Image.Image,
    layer_cfg: dict[str, Any],
    brand: BrandContext,
    text_content: str,
    title: str | None,
) -> bool:
    value = resolve_source(layer_cfg.get("source", "text_content"), brand, text_content, title)
    if not value.strip():
        return False
    x, y, w, h = _box(layer_cfg.get("box", {}), canvas.size)
    style = style_from_config(layer_cfg.get("style", {}), brand)
    rendered = render_text_layer(value, style, w, h)
    _composite(canvas, rendered.image, x, y)
    return True


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------
@dataclass
class CompositionResult:
    image: Image.Image
    layers_drawn: list[str]
    layers_skipped: list[str]


def canvas_size(config: dict[str, Any]) -> tuple[int, int]:
    canvas = config.get("canvas") or {}
    return (
        int(canvas.get("width", DEFAULT_CANVAS[0])),
        int(canvas.get("height", DEFAULT_CANVAS[1])),
    )


def build_overlay(
    config: dict[str, Any],
    brand: BrandContext,
    text_content: str,
    title: str | None = None,
) -> CompositionResult:
    """Flatten every non-video layer of ``config`` into one RGBA image."""
    size = canvas_size(config)
    canvas = Image.new("RGBA", size, (0, 0, 0, 0))

    drawn: list[str] = []
    skipped: list[str] = []

    background = config.get("background") or {}
    if background.get("overlay_alpha"):
        _draw_fill(
            canvas,
            {"color": background.get("overlay_color", "$black"), "alpha": background["overlay_alpha"]},
            brand,
        )
        drawn.append("background-tint")

    for index, layer_cfg in enumerate(config.get("layers") or []):
        kind = layer_cfg.get("type")
        name = layer_cfg.get("name") or f"{kind}-{index}"
        try:
            if kind == "gradient":
                _draw_gradient(canvas, layer_cfg, brand)
                ok = True
            elif kind == "bar":
                _draw_bar(canvas, layer_cfg, brand)
                ok = True
            elif kind == "fill":
                _draw_fill(canvas, layer_cfg, brand)
                ok = True
            elif kind == "logo":
                ok = _draw_logo(canvas, layer_cfg, brand)
            elif kind == "text":
                ok = _draw_text(canvas, layer_cfg, brand, text_content, title)
            else:
                logger.warning("unknown_layer_type", extra={"layer_type": kind})
                ok = False
        except Exception as exc:  # noqa: BLE001
            logger.exception("layer_render_failed", extra={"layer": name, "error": str(exc)})
            raise
        (drawn if ok else skipped).append(name)

    logger.info(
        "overlay_composed",
        extra={"layers_drawn": len(drawn), "layers_skipped": len(skipped), "canvas": f"{size[0]}x{size[1]}"},
    )
    return CompositionResult(image=canvas, layers_drawn=drawn, layers_skipped=skipped)


def render_preview(
    config: dict[str, Any],
    brand: BrandContext,
    text_content: str,
    *,
    width: int = 540,
) -> Image.Image:
    """Flat preview of a template (used for the template picker thumbnails)."""
    size = canvas_size(config)
    base = Image.new("RGBA", size, (0, 0, 0, 255))
    draw = ImageDraw.Draw(base)
    top = parse_color(brand.secondary_color)
    bottom = parse_color(brand.primary_color)
    for row in range(size[1]):
        t = row / max(1, size[1] - 1)
        draw.line(
            [(0, row), (size[0], row)],
            fill=tuple(int(top[i] + (bottom[i] - top[i]) * t) for i in range(3)) + (255,),
        )
    overlay = build_overlay(config, brand, text_content).image
    base.alpha_composite(overlay)

    # A caption-driven template has no headline layer - its words arrive as
    # timed captions - so a plain overlay preview would be a thumbnail with no
    # text at all. Paint one sample caption so the picker shows what it does.
    if not any(layer.get("source") == "text_content" for layer in config.get("layers", [])):
        from app.video.captions import band_box

        x, y, w, h = band_box("center", size)
        style = style_from_config(
            {
                "bold": True,
                "size": 86,
                "min_size": 36,
                "color": "$white",
                "align": "center",
                "shadow": True,
                "max_lines": 3,
            },
            brand,
        )
        base.alpha_composite(render_text_layer(text_content, style, w, h).image, dest=(x, y))

    height = int(size[1] * width / size[0])
    return base.convert("RGB").resize((width, height), Image.Resampling.LANCZOS)
