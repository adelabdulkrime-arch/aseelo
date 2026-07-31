"""Idempotent startup seeding: templates and an optional admin user.

Run via ``python -m app.services.seed`` (see entrypoint.sh). Safe to run on
every boot - templates are upserted by slug and the admin user is only
created if it does not already exist.
"""

from __future__ import annotations

from sqlalchemy import select

from app.config import settings
from app.database import session_scope
from app.logging_config import configure_logging, get_logger
from app.models import Template, User, UserRole
from app.security import hash_password
from app.video.templates import TEMPLATE_SEEDS

logger = get_logger(__name__)


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
    seed_admin()
    logger.info("seed_complete")


if __name__ == "__main__":
    main()
