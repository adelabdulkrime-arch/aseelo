"""Background removal for logos uploaded without an alpha channel."""

from __future__ import annotations

from PIL import Image

from app.services.logo_cutout import remove_background, remove_white_background


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


# ---------------------------------------------------------------------------
# auto mode - any flat backdrop, not only white
# ---------------------------------------------------------------------------
def test_auto_clears_a_dark_grey_plate(tmp_path):
    """The real case: a customer logo on (48,48,48), which white mode can't see."""
    source = tmp_path / "logo.jpg"
    image = Image.new("RGB", (120, 120), (48, 48, 48))
    image.paste((250, 190, 20), (35, 35, 85, 85))
    image.save(source, quality=95)

    target = tmp_path / "out.png"
    assert remove_background(source, target, mode="auto") is True

    result = Image.open(target).convert("RGBA")
    assert result.getpixel((2, 2))[3] == 0, "grey backdrop should be cleared"
    assert result.getpixel((60, 60))[3] == 255, "the mark itself must stay"


def test_white_mode_ignores_a_grey_plate(tmp_path):
    """Proves the two modes really differ, and that 'white' is unchanged."""
    source = tmp_path / "logo.jpg"
    image = Image.new("RGB", (100, 100), (48, 48, 48))
    image.paste((250, 190, 20), (30, 30, 70, 70))
    image.save(source, quality=95)

    assert remove_background(source, tmp_path / "out.png", mode="white") is False


def test_auto_keeps_colour_enclosed_by_the_mark(tmp_path):
    source = tmp_path / "ring.jpg"
    image = Image.new("RGB", (120, 120), (30, 90, 200))
    image.paste((20, 20, 20), (25, 25, 95, 95))
    image.paste((30, 90, 200), (50, 50, 70, 70))  # same colour as the backdrop
    image.save(source, quality=95)

    target = tmp_path / "out.png"
    assert remove_background(source, target, mode="auto") is True

    result = Image.open(target).convert("RGBA")
    assert result.getpixel((60, 60))[3] == 255, "enclosed colour is not background"
    assert result.getpixel((1, 1))[3] == 0, "the border backdrop is"


def test_auto_refuses_to_erase_a_logo_that_is_all_one_colour(tmp_path):
    """A flat image has no mark to keep; blanking it would be worse than a no-op."""
    source = tmp_path / "flat.jpg"
    Image.new("RGB", (80, 80), (12, 140, 90)).save(source, quality=95)
    assert remove_background(source, tmp_path / "out.png", mode="auto") is False


def test_auto_survives_jpeg_noise_around_the_mark(tmp_path):
    """Heavy JPEG compression dithers the backdrop; it must still be cleared."""
    source = tmp_path / "noisy.jpg"
    image = Image.new("RGB", (140, 140), (48, 48, 48))
    image.paste((255, 255, 255), (45, 45, 95, 95))
    image.save(source, quality=30)

    target = tmp_path / "out.png"
    assert remove_background(source, target, mode="auto") is True
    result = Image.open(target).convert("RGBA")
    assert result.getpixel((3, 3))[3] == 0
    assert result.getpixel((70, 70))[3] == 255
