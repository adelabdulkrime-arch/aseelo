"""Template listing (read-only; templates are seeded data, see app.services.seed)."""

from __future__ import annotations

from fastapi import APIRouter
from sqlalchemy import select

from app.deps import DbSession
from app.models import Template
from app.schemas import TemplateOut

router = APIRouter(prefix="/api/templates", tags=["templates"])


@router.get("", response_model=list[TemplateOut])
def list_templates(db: DbSession) -> list[Template]:
    return list(
        db.scalars(
            select(Template).where(Template.is_active.is_(True)).order_by(Template.sort_order)
        )
    )
