"""Guest sessions: the only way into the app."""

from __future__ import annotations

import pytest
from sqlalchemy import select

from app.config import settings
from app.errors import ValidationError
from app.models import BrandProfile, User


def test_guest_gets_a_working_session(client):
    response = client.post("/api/auth/guest")
    assert response.status_code == 201, response.text

    body = response.json()
    assert body["user"]["is_guest"] is True
    assert body["token_type"] == "bearer"

    # The token must actually authenticate - a session the API rejects is the
    # whole failure mode this endpoint exists to avoid.
    me = client.get("/api/auth/me", headers={"Authorization": f"Bearer {body['access_token']}"})
    assert me.status_code == 200
    assert me.json()["id"] == body["user"]["id"]


def test_guest_can_reach_the_authenticated_api(client):
    token = client.post("/api/auth/guest").json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    # These are exactly the calls the dashboard makes on first paint.
    assert client.get("/api/dashboard", headers=headers).status_code == 200
    assert client.get("/api/videos", headers=headers).status_code == 200
    assert client.get("/api/brand", headers=headers).status_code == 200


def test_each_guest_is_isolated(client, db):
    first = client.post("/api/auth/guest").json()
    second = client.post("/api/auth/guest").json()

    assert first["user"]["id"] != second["user"]["id"]
    assert first["user"]["email"] != second["user"]["email"]

    # Two rows, two brand profiles - not one shared account.
    guests = db.scalars(select(User).where(User.is_guest.is_(True))).all()
    assert len(guests) == 2
    for guest in guests:
        assert db.scalar(select(BrandProfile).where(BrandProfile.user_id == guest.id)) is not None


def test_a_guest_cannot_see_another_guests_videos(client, db, template):
    """The isolation that a single shared guest account would not give."""
    owner = client.post("/api/auth/guest").json()
    other = client.post("/api/auth/guest").json()

    owner_headers = {"Authorization": f"Bearer {owner['access_token']}"}
    other_headers = {"Authorization": f"Bearer {other['access_token']}"}

    assert client.get("/api/videos", headers=owner_headers).json()["items"] == []
    assert client.get("/api/videos", headers=other_headers).json()["items"] == []

    # Dashboards are per-user, so one guest's activity never shows in another's.
    assert client.get("/api/dashboard", headers=other_headers).json()["total_videos"] == 0


def test_endpoint_is_refused_when_disabled(client, monkeypatch):
    """The emergency brake: a host under load can shut off new sessions."""
    monkeypatch.setattr(settings, "guest_sessions_enabled", False)

    response = client.post("/api/auth/guest")
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "forbidden"


def test_guests_get_a_tighter_duration_ceiling_than_the_global_limit(
    client, template, monkeypatch
):
    """Duration drives render cost, and every caller is a guest."""
    from app.routers import videos as videos_router

    seen: list[int | None] = []

    def _capture(upload, *, max_duration_seconds=None):
        seen.append(max_duration_seconds)
        # A domain error so the request ends as a clean 422 instead of an
        # unhandled 500; only the captured argument matters here.
        raise ValidationError("captured")

    monkeypatch.setattr(videos_router, "validate_video_upload", _capture)
    monkeypatch.setattr(settings, "guest_max_video_duration_seconds", 20)

    payload = {"text_content": "hi", "template_id": str(template.id)}
    files = {"video_file": ("s.mp4", b"x", "video/mp4")}

    guest_token = client.post("/api/auth/guest").json()["access_token"]
    client.post(
        "/api/videos",
        headers={"Authorization": f"Bearer {guest_token}"},
        data=payload,
        files=files,
    )

    assert seen == [20]


def test_guest_ceiling_can_never_exceed_the_global_one(monkeypatch, tmp_path):
    """A misconfigured guest limit must not raise the ceiling for anyone.

    Uses a real 6-second clip and asks for a 600s guest allowance while the
    global ceiling is 5s. The upload must still be refused.
    """
    from app.errors import ValidationError
    from app.services.file_validation import validate_video_upload
    from scripts.smoke_test import make_clip

    monkeypatch.setattr(settings, "max_video_duration_seconds", 5)
    clip = make_clip(tmp_path / "long.mp4")

    class _Upload:
        filename = "long.mp4"
        content_type = "video/mp4"
        file = clip.open("rb")

    with pytest.raises(ValidationError, match="too long"):
        validate_video_upload(_Upload(), max_duration_seconds=600)
