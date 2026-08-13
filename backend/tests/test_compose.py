"""Layer composition: brand token resolution, layer ordering, flattening."""

from __future__ import annotations

from PIL import Image

from app.video.compose import (
    BrandContext,
    build_overlay,
    canvas_size,
    resolve_color,
    resolve_source,
)
from app.video.templates import CAPTION_TEMPLATE_SLUG, TEMPLATE_SEEDS

ARABIC = "عروضنا الجديدة متوفرة الآن"


def _brand(**overrides) -> BrandContext:
    defaults = {
        "brand_name": "ASEELO",
        "primary_color": "#0F172A",
        "secondary_color": "#1E88E5",
        "accent_color": "#F5B700",
        "phone": "+964 770 000 0000",
        "whatsapp": "+964 771 111 1111",
        "website": "https://aseelo.example",
        "tagline": "From Idea to Content",
    }
    return BrandContext(**{**defaults, **overrides})


def test_color_tokens_resolve_against_the_brand():
    brand = _brand()
    assert resolve_color("$primary", brand) == "#0F172A"
    assert resolve_color("$accent", brand) == "#F5B700"
    assert resolve_color("$white", brand) == "#FFFFFF"
    # A literal colour passes straight through.
    assert resolve_color("#ABCDEF", brand) == "#ABCDEF"


def test_contact_sources_compose_brand_fields():
    brand = _brand()
    inline = resolve_source("contact_inline", brand, ARABIC, None)
    assert "+964 770 000 0000" in inline
    assert "aseelo.example" in inline
    # Arabic content selects Arabic labels.
    assert "هاتف" in inline

    multiline = resolve_source("contact_multiline", brand, ARABIC, None)
    assert multiline.count("\n") >= 1


def test_duplicate_whatsapp_is_not_repeated():
    brand = _brand(whatsapp="+964 770 000 0000")
    inline = resolve_source("contact_inline", brand, ARABIC, None)
    assert inline.count("+964 770 000 0000") == 1


def test_english_content_uses_english_labels():
    brand = _brand(brand_name="ASEELO")
    inline = resolve_source("contact_inline", brand, "New offers available now", None)
    assert "Tel" in inline


def test_every_seeded_template_flattens_to_one_canvas(tmp_path):
    logo_path = tmp_path / "logo.png"
    Image.new("RGBA", (400, 400), (245, 183, 0, 255)).save(logo_path)
    brand = _brand()
    brand.logo_path = logo_path

    for seed in TEMPLATE_SEEDS:
        config = seed["configuration"]
        result = build_overlay(config, brand, ARABIC, "Test title")
        assert result.image.size == canvas_size(config) == (1080, 1920)
        assert result.image.mode == "RGBA"
        assert result.image.getchannel("A").getbbox() is not None
        assert "brand-logo" in result.layers_drawn
        assert not result.layers_skipped or "brand-logo" not in result.layers_skipped
        # The caption-driven template carries no headline on the static overlay:
        # its words are painted per caption, each on its own timed layer.
        if seed["slug"] != CAPTION_TEMPLATE_SLUG:
            assert "headline" in result.layers_drawn
        else:
            assert "headline" not in result.layers_drawn


def test_missing_logo_is_skipped_not_fatal():
    result = build_overlay(TEMPLATE_SEEDS[0]["configuration"], _brand(), ARABIC)
    assert "brand-logo" in result.layers_skipped
    # The headline still rendered.
    assert "headline" in result.layers_drawn


def test_empty_optional_fields_are_skipped():
    brand = _brand(tagline=None, phone=None, whatsapp=None, website=None)
    result = build_overlay(TEMPLATE_SEEDS[0]["configuration"], brand, ARABIC)
    assert "tagline" in result.layers_skipped
    assert "contact" in result.layers_skipped


def test_brand_snapshot_round_trips():
    brand = _brand()
    restored = BrandContext.from_snapshot(brand.to_snapshot())
    assert restored.brand_name == brand.brand_name
    assert restored.primary_color == brand.primary_color
    assert restored.phone == brand.phone
