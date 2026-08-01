"""Template picker thumbnails generated at seed time."""

from __future__ import annotations

import hashlib
from collections.abc import Iterator

import pytest
from PIL import Image

from app.models import Template
from app.services import seed as seed_module
from app.services.seed import (
    PREVIEW_WIDTH,
    _preview_fingerprint,
    seed_template_previews,
    seed_templates,
)
from app.storage import get_storage
from app.video.templates import TEMPLATE_SEEDS


@pytest.fixture(scope="module", autouse=True)
def _restore_previews() -> Iterator[None]:
    """Put the previews back after this module has finished mangling them.

    These tests delete stored previews on purpose. Storage is shared with the
    running dev stack, so without this a plain ``pytest`` run would leave the
    template picker showing gradients until the next backend restart re-seeded.
    """
    yield
    seed_templates()
    seed_template_previews()


def _key(slug: str) -> str:
    return f"templates/previews/{slug}.png"


def _cold_start(db) -> None:
    """Drop stored previews and unlink them, so the render branch really runs."""
    storage = get_storage()
    for seed in TEMPLATE_SEEDS:
        if storage.exists(_key(seed["slug"])):
            storage.delete(_key(seed["slug"]))
    db.query(Template).update({"preview_url": None})
    db.commit()


def test_seed_renders_a_preview_for_every_template(db):
    seed_templates()
    _cold_start(db)

    seed_template_previews()
    db.expire_all()

    storage = get_storage()
    for seed in TEMPLATE_SEEDS:
        slug = seed["slug"]
        assert storage.exists(_key(slug)), f"no preview stored for {slug}"

        template = db.query(Template).filter(Template.slug == slug).one()
        assert template.preview_url
        # The digest on the URL is what lets the next boot detect a config change.
        assert template.preview_url.endswith(f"?v={_preview_fingerprint(seed['configuration'])}")

        with storage.open_stream(_key(slug)) as handle:
            image = Image.open(handle)
            assert image.format == "PNG"
            assert image.width == PREVIEW_WIDTH
            # 9:16 portrait, matching the rendered video.
            assert image.height == int(PREVIEW_WIDTH * 16 / 9)


def test_previews_are_visually_distinct(db):
    """Guards the failure that would still look like success.

    If the template configuration were ignored, every preview would render the
    same image and every other assertion here would still pass.
    """
    seed_templates()
    _cold_start(db)
    seed_template_previews()

    storage = get_storage()
    digests = {}
    for seed in TEMPLATE_SEEDS:
        with storage.open_stream(_key(seed["slug"])) as handle:
            digests[seed["slug"]] = hashlib.sha256(handle.read()).hexdigest()

    assert len(set(digests.values())) == len(digests), f"identical previews: {digests}"


def test_seed_previews_skips_rendering_when_unchanged(db, monkeypatch):
    seed_templates()
    _cold_start(db)
    seed_template_previews()

    calls: list[str] = []
    real = seed_module.render_preview

    def _counting(*args, **kwargs):
        calls.append("render")
        return real(*args, **kwargs)

    monkeypatch.setattr(seed_module, "render_preview", _counting)
    seed_template_previews()

    assert calls == [], "previews were re-rendered despite nothing changing"


def test_seed_previews_rerenders_when_configuration_changes(db, monkeypatch):
    seed_templates()
    _cold_start(db)
    seed_template_previews()
    db.expire_all()
    before = db.query(Template).filter(Template.slug == TEMPLATE_SEEDS[0]["slug"]).one().preview_url

    monkeypatch.setattr(seed_module, "PREVIEW_TEXT", "نص مختلف تماما")
    seed_template_previews()
    db.expire_all()
    after = db.query(Template).filter(Template.slug == TEMPLATE_SEEDS[0]["slug"]).one().preview_url

    assert before != after, "changing what is rendered did not change the ?v= digest"


def test_seed_previews_survives_a_render_failure(db, monkeypatch):
    """A broken preview must not stop the app booting."""
    seed_templates()
    _cold_start(db)

    def _boom(*args, **kwargs):
        raise RuntimeError("font blew up")

    monkeypatch.setattr(seed_module, "render_preview", _boom)
    seed_template_previews()
    db.expire_all()

    # No exception escaped, and nothing was linked to a file that does not exist.
    for seed in TEMPLATE_SEEDS:
        template = db.query(Template).filter(Template.slug == seed["slug"]).one()
        assert template.preview_url is None
