"""Brand profile: read, update, validation, logo upload, isolation."""

from __future__ import annotations

import io

from PIL import Image


def _png_bytes(size: tuple[int, int] = (256, 256)) -> bytes:
    buffer = io.BytesIO()
    Image.new("RGBA", size, (30, 136, 229, 255)).save(buffer, format="PNG")
    return buffer.getvalue()


def _transparent_png_bytes(size: tuple[int, int] = (256, 256)) -> bytes:
    """A mark on a genuinely transparent background."""
    buffer = io.BytesIO()
    image = Image.new("RGBA", size, (0, 0, 0, 0))
    image.paste((30, 136, 229, 255), (64, 64, 192, 192))
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def _jpeg_bytes(size: tuple[int, int] = (256, 256)) -> bytes:
    """A mark on white — JPEG cannot carry alpha at all."""
    buffer = io.BytesIO()
    image = Image.new("RGB", size, (255, 255, 255))
    image.paste((30, 136, 229), (64, 64, 192, 192))
    image.save(buffer, format="JPEG")
    return buffer.getvalue()


def test_get_brand_creates_default(client, user):
    response = client.get("/api/brand", headers=user["headers"])
    assert response.status_code == 200
    body = response.json()
    assert body["primary_color"].startswith("#")
    assert body["logo_url"] is None


def test_update_brand_persists_fields(client, user):
    response = client.put(
        "/api/brand",
        headers=user["headers"],
        json={
            "brand_name": "خط الجزيرة",
            "primary_color": "#123456",
            "phone": "+964 770 000 0000",
            "website": "aseelo.example",
            "tagline": "From Idea to Content",
            "social_media": {"Instagram": "@aseelo"},
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["brand_name"] == "خط الجزيرة"
    assert body["primary_color"] == "#123456"
    # Bare domains are normalised to https and social keys are lowercased.
    assert body["website"] == "https://aseelo.example"
    assert body["social_media"] == {"instagram": "@aseelo"}

    again = client.get("/api/brand", headers=user["headers"]).json()
    assert again["brand_name"] == "خط الجزيرة"


def test_update_brand_rejects_bad_color(client, user):
    response = client.put(
        "/api/brand", headers=user["headers"], json={"primary_color": "not-a-color"}
    )
    assert response.status_code == 422


def test_brand_requires_auth(client):
    assert client.get("/api/brand").status_code == 401


def test_logo_upload_and_replace(client, user):
    response = client.post(
        "/api/brand/logo",
        headers=user["headers"],
        files={"file": ("logo.png", _png_bytes(), "image/png")},
    )
    assert response.status_code == 200
    first_url = response.json()["logo_url"]
    assert first_url and first_url.endswith(".png")

    replaced = client.post(
        "/api/brand/logo",
        headers=user["headers"],
        files={"file": ("logo2.png", _png_bytes((128, 128)), "image/png")},
    )
    assert replaced.status_code == 200
    assert replaced.json()["logo_url"] != first_url


def test_logo_upload_rejects_non_image(client, user):
    response = client.post(
        "/api/brand/logo",
        headers=user["headers"],
        files={"file": ("payload.png", b"this is definitely not a png", "image/png")},
    )
    assert response.status_code == 422


def test_logo_upload_rejects_bad_extension(client, user):
    response = client.post(
        "/api/brand/logo",
        headers=user["headers"],
        files={"file": ("evil.svg", _png_bytes(), "image/png")},
    )
    assert response.status_code == 422


def test_logo_upload_flags_missing_transparency(client, user):
    """A JPEG logo has no alpha, so the caller must be warned."""
    response = client.post(
        "/api/brand/logo",
        headers=user["headers"],
        files={"file": ("logo.jpg", _jpeg_bytes(), "image/jpeg")},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["logo_has_transparency"] is False
    assert body["logo_cutout_applied"] is False


def test_logo_upload_reports_real_transparency(client, user):
    response = client.post(
        "/api/brand/logo",
        headers=user["headers"],
        files={"file": ("logo.png", _transparent_png_bytes(), "image/png")},
    )
    assert response.status_code == 200
    assert response.json()["logo_has_transparency"] is True


def test_fully_opaque_png_is_not_reported_as_transparent(client, user):
    """RGBA alone is not enough — every pixel here is opaque."""
    response = client.post(
        "/api/brand/logo",
        headers=user["headers"],
        files={"file": ("logo.png", _png_bytes(), "image/png")},
    )
    assert response.status_code == 200
    assert response.json()["logo_has_transparency"] is False


def test_cutout_is_off_by_default(client, user):
    response = client.post(
        "/api/brand/logo",
        headers=user["headers"],
        files={"file": ("logo.jpg", _jpeg_bytes(), "image/jpeg")},
    )
    assert response.json()["logo_cutout_applied"] is False


def test_cutout_removes_white_background_when_requested(client, user):
    response = client.post(
        "/api/brand/logo?remove_white_background=true",
        headers=user["headers"],
        files={"file": ("logo.jpg", _jpeg_bytes(), "image/jpeg")},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["logo_cutout_applied"] is True
    assert body["logo_has_transparency"] is True
    # The cutout is always re-encoded as PNG, whatever arrived.
    assert body["logo_url"].endswith(".png")


def test_brands_are_isolated_per_user(client, user, other_user):
    client.put("/api/brand", headers=user["headers"], json={"brand_name": "Mine"})
    theirs = client.get("/api/brand", headers=other_user["headers"]).json()
    assert theirs["brand_name"] != "Mine"
