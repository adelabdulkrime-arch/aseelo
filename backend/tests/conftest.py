"""Shared test fixtures.

Tests run against the real PostgreSQL instance from docker compose (the schema
uses JSONB and native enums, so SQLite would not be a faithful substitute).
Each test module gets a clean set of tables.
"""

from __future__ import annotations

import os
import uuid
from collections.abc import Iterator

import pytest

os.environ.setdefault("APP_ENV", "test")
os.environ.setdefault("RATE_LIMIT_ENABLED", "false")

from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import text  # noqa: E402

from app.database import Base, SessionLocal, engine  # noqa: E402
from app.main import app  # noqa: E402
from app.models import Template  # noqa: E402
from app.video.templates import TEMPLATE_SEEDS  # noqa: E402


@pytest.fixture(scope="session", autouse=True)
def _schema() -> Iterator[None]:
    Base.metadata.create_all(bind=engine)
    yield


@pytest.fixture(autouse=True)
def _clean_tables() -> Iterator[None]:
    """Truncate user data between tests; seeded templates are re-created."""
    with SessionLocal() as db:
        db.execute(
            text(
                "TRUNCATE users, videos, rendering_jobs, brand_profiles, "
                "password_reset_tokens CASCADE"
            )
        )
        db.commit()
    yield


@pytest.fixture
def db() -> Iterator:
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def client() -> Iterator[TestClient]:
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def template(db) -> Template:
    seed = TEMPLATE_SEEDS[0]
    existing = db.query(Template).filter(Template.slug == seed["slug"]).one_or_none()
    if existing is None:
        existing = Template(**seed)
        db.add(existing)
        db.commit()
        db.refresh(existing)
    return existing


def register(client: TestClient, email: str | None = None, password: str = "SuperSecret123") -> dict:
    """Register a fresh user and return {'token', 'user', 'headers'}."""
    email = email or f"user-{uuid.uuid4().hex[:10]}@example.com"
    response = client.post(
        "/api/auth/register",
        json={
            "name": "Test User",
            "email": email,
            "password": password,
            "confirm_password": password,
        },
    )
    assert response.status_code == 201, response.text
    body = response.json()
    return {
        "token": body["access_token"],
        "user": body["user"],
        "email": email,
        "password": password,
        "headers": {"Authorization": f"Bearer {body['access_token']}"},
    }


@pytest.fixture
def user(client: TestClient) -> dict:
    return register(client)


@pytest.fixture
def other_user(client: TestClient) -> dict:
    return register(client)
