"""White-background removal for logos uploaded without an alpha channel."""

from __future__ import annotations

from PIL import Image

from app.services.logo_cutout import remove_white_background


def test_border_white_is_cleared(tmp_path):
    source = tmp_path / "logo.jpg"
    image = Image.new("RGB", (100, 100), (255, 255, 255))
    image.paste((200, 30, 30), (30, 30, 70, 70))
    image.save(source)

    target = tmp_path / "out.png"
    assert remove_white_background(source, target) is True

    result = Image.open(target).convert("RGBA")
    assert result.getpixel((2, 2))[3] == 0, "corner should be transparent"
    assert result.getpixel((50, 50))[3] == 255, "the mark itself must stay opaque"


def test_interior_white_is_preserved(tmp_path):
    """White enclosed by the design is not background and must survive.

    This is the case that makes a naive colour-key replacement unusable: the
    hole inside a letter like 'O' would otherwise be punched out.
    """
    source = tmp_path / "ring.jpg"
    image = Image.new("RGB", (100, 100), (255, 255, 255))
    image.paste((20, 20, 20), (20, 20, 80, 80))  # dark block
    image.paste((255, 255, 255), (40, 40, 60, 60))  # white hole inside it
    image.save(source)

    target = tmp_path / "out.png"
    assert remove_white_background(source, target) is True

    result = Image.open(target).convert("RGBA")
    assert result.getpixel((50, 50))[3] == 255, "interior white must be kept"
    assert result.getpixel((1, 1))[3] == 0, "border white must be cleared"


def test_image_without_white_background_is_left_alone(tmp_path):
    source = tmp_path / "solid.jpg"
    Image.new("RGB", (60, 60), (10, 60, 120)).save(source)

    target = tmp_path / "out.png"
    assert remove_white_background(source, target) is False
    assert not target.exists()


def test_unreadable_file_does_not_raise(tmp_path):
    source = tmp_path / "broken.jpg"
    source.write_bytes(b"not an image")
    assert remove_white_background(source, tmp_path / "out.png") is False
