"""Idempotent startup seeding: templates and an optional admin user.

Run via ``python -m app.services.seed`` (see entrypoint.sh). Safe to run on
every boot - templates are upserted by slug and the admin user is only
created if it does not already exist.
"""

from __future__ import annotations

import hashlib
import io
import json
from dataclasses import asdict
from typing import Any

from sqlalchemy import select

from app.config import settings
from app.database import session_scope
from app.logging_config import configure_logging, get_logger
from app.models import Template, User, UserRole
from app.security import hash_password
from app.storage import get_storage
from app.video.compose import BrandContext, render_preview
from app.video.templates import TEMPLATE_SEEDS

logger = get_logger(__name__)

# Thumbnails are shown three-across in the picker; 480px wide is already more
# than any card renders at, and keeps the three PNGs small.
PREVIEW_WIDTH = 480

# The picker is shown before the user has a brand, so previews use a neutral
# stand-in. Every contact field is populated on purpose: templates differ mainly
# in how they arrange the contact block, and empty fields make those layers skip
# rendering, which would make all three previews look alike.
PREVIEW_BRAND = BrandContext(
    brand_name="أصيلو",
    primary_color="#0F172A",
    secondary_color="#1E88E5",
    accent_color="#F5B700",
    phone="+964 770 000 0000",
    whatsapp="+964 771 111 1111",
    website="aseelo.example",
    tagline="From Idea to Content",
)
PREVIEW_TEXT = "عرض خاص لفترة محدودة"


def seed_templates() -> None:
    with session_scope() as db:
        for seed in TEMPLATE_SEEDS:
            template = db.scalar(select(Template).where(Template.slug == seed["slug"]))
            if template is None:
                db.add(Template(**seed))
                logger.info("template_seeded", extra={"slug": seed["slug"]})
            else:
                template.name = seed["name"]
                template.description = seed["description"]
                template.sort_order = seed["sort_order"]
                template.configuration = seed["configuration"]
                template.is_active = True


def _preview_fingerprint(configuration: dict[str, Any]) -> str:
    """Short digest of everything that changes what the preview looks like."""
    payload = json.dumps(
        {
            "configuration": configuration,
            "brand": asdict(PREVIEW_BRAND),
            "text": PREVIEW_TEXT,
            "width": PREVIEW_WIDTH,
        },
        sort_keys=True,
        default=str,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:12]


def seed_template_previews() -> None:
    """Render the picker thumbnails and point each template at its own.

    The storage key is stable per slug, so a re-render overwrites in place and
    never leaves orphans behind. The digest rides on the URL as ``?v=`` instead,
    which both busts browser/CDN caches and records - without a schema change -
    what the stored file was rendered from, so the next boot can tell whether
    the template configuration has changed.

    Rendering must never stop the app booting: on failure the template keeps
    whatever URL it had and the picker falls back to a plain gradient.
    """
    storage = get_storage()
    with session_scope() as db:
        for seed in TEMPLATE_SEEDS:
            slug = seed["slug"]
            template = db.scalar(select(Template).where(Template.slug == slug))
            if template is None:
                continue

            key = f"templates/previews/{slug}.png"
            url = f"{storage.public_url(key)}?v={_preview_fingerprint(seed['configuration'])}"
            try:
                if template.preview_url != url or not storage.exists(key):
                    image = render_preview(
                        seed["configuration"],
                        PREVIEW_BRAND,
                        PREVIEW_TEXT,
                        width=PREVIEW_WIDTH,
                    )
                    buffer = io.BytesIO()
                    image.save(buffer, format="PNG", optimize=True)
                    buffer.seek(0)
                    stored = storage.save_stream(key, buffer, content_type="image/png")
                    logger.info(
                        "template_preview_rendered",
                        extra={"slug": slug, "key": key, "bytes": stored.size},
                    )
                template.preview_url = url
            except Exception as exc:  # noqa: BLE001
                logger.exception("template_preview_failed", extra={"slug": slug, "error": str(exc)})


def seed_admin() -> None:
    if not settings.seed_admin_email or not settings.seed_admin_password:
        return
    with session_scope() as db:
        existing = db.scalar(select(User).where(User.email == settings.seed_admin_email))
        if existing is not None:
            return
        db.add(
            User(
                name="Administrator",
                email=settings.seed_admin_email,
                password_hash=hash_password(settings.seed_admin_password),
                role=UserRole.ADMIN,
            )
        )
        logger.info("admin_seeded", extra={"email": settings.seed_admin_email})


def main() -> None:
    configure_logging()
    seed_templates()
    # After seed_templates: the rows must exist before they can be given a URL.
    seed_template_previews()
    seed_admin()
    logger.info("seed_complete")


if __name__ == "__main__":
    main()
