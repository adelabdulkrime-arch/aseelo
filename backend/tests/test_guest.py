"""Guest sessions: opening the app without a login."""

from __future__ import annotations

import pytest
from sqlalchemy import func, select

from app.config import settings
from app.errors import ValidationError
from app.models import BrandProfile, User


@pytest.fixture(autouse=True)
def _enabled(monkeypatch):
    """The endpoint is off by default; every test here needs it on."""
    monkeypatch.setattr(settings, "guest_sessions_enabled", True)


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


def test_guest_password_is_not_guessable(client, db):
    """No shared or derivable credential is left behind."""
    body = client.post("/api/auth/guest").json()
    email = body["user"]["email"]

    for attempt in ["", "guest", "password", email, body["user"]["id"]]:
        response = client.post("/api/auth/login", json={"email": email, "password": attempt})
        assert response.status_code in (401, 422), f"{attempt!r} was accepted"


def test_guests_are_flagged_apart_from_real_users(client, db):
    from .conftest import register

    register(client)
    client.post("/api/auth/guest")

    real = db.scalar(select(func.count()).select_from(User).where(User.is_guest.is_(False)))
    guests = db.scalar(select(func.count()).select_from(User).where(User.is_guest.is_(True)))
    assert real == 1
    assert guests == 1


def test_endpoint_is_refused_when_disabled(client, monkeypatch):
    """Default-off: the deployment must opt in, per environment."""
    monkeypatch.setattr(settings, "guest_sessions_enabled", False)

    response = client.post("/api/auth/guest")
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "forbidden"


def test_guests_get_a_tighter_duration_ceiling_than_registered_users(
    client, template, monkeypatch
):
    """Duration drives render cost, and a guest is an anonymous caller."""
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

    from .conftest import register

    account = register(client)
    client.post("/api/videos", headers=account["headers"], data=payload, files=files)

    # Guest capped at 20s; registered user passes None, meaning the global limit.
    assert seen == [20, None]


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


def test_registering_and_logging_in_still_work(client):
    """The ordinary flows must be untouched by this."""
    from .conftest import register

    account = register(client)
    login = client.post(
        "/api/auth/login", json={"email": account["email"], "password": account["password"]}
    )
    assert login.status_code == 200
    assert login.json()["user"]["is_guest"] is False


def test_convert_guest_keeps_the_same_account_and_its_data(client, db, template, tmp_path):
    """The whole point: videos and brand survive the upgrade because the
    user_id never changes - only the row's own fields do."""
    from scripts.smoke_test import make_clip

    guest = client.post("/api/auth/guest").json()
    headers = {"Authorization": f"Bearer {guest['access_token']}"}

    clip = make_clip(tmp_path / "clip.mp4")
    payload = {"text_content": "hi", "template_id": str(template.id)}
    with clip.open("rb") as fh:
        files = {"video_file": ("clip.mp4", fh, "video/mp4")}
        video = client.post("/api/videos", headers=headers, data=payload, files=files)
    assert video.status_code == 201, video.text

    response = client.post(
        "/api/auth/convert-guest",
        headers=headers,
        json={"email": "new-owner@example.com", "password": "SuperSecret123"},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["user"]["id"] == guest["user"]["id"]
    assert body["user"]["email"] == "new-owner@example.com"
    assert body["user"]["is_guest"] is False

    new_headers = {"Authorization": f"Bearer {body['access_token']}"}
    videos = client.get("/api/videos", headers=new_headers).json()["items"]
    assert [v["id"] for v in videos] == [video.json()["id"]]

    login = client.post(
        "/api/auth/login", json={"email": "new-owner@example.com", "password": "SuperSecret123"}
    )
    assert login.status_code == 200
    assert login.json()["user"]["id"] == guest["user"]["id"]


def test_convert_guest_requires_authentication(client):
    response = client.post(
        "/api/auth/convert-guest",
        json={"email": "someone@example.com", "password": "SuperSecret123"},
    )
    assert response.status_code == 401


def test_convert_guest_refuses_a_real_account(client):
    from .conftest import register

    account = register(client)
    response = client.post(
        "/api/auth/convert-guest",
        headers=account["headers"],
        json={"email": "someone-else@example.com", "password": "SuperSecret123"},
    )
    assert response.status_code == 409


def test_convert_guest_refuses_an_email_already_in_use(client):
    from .conftest import register

    account = register(client)
    guest = client.post("/api/auth/guest").json()
    guest_headers = {"Authorization": f"Bearer {guest['access_token']}"}

    response = client.post(
        "/api/auth/convert-guest",
        headers=guest_headers,
        json={"email": account["email"], "password": "SuperSecret123"},
    )
    assert response.status_code == 409

    # The guest row must be untouched by the failed attempt.
    me = client.get("/api/auth/me", headers=guest_headers)
    assert me.json()["is_guest"] is True


def test_convert_guest_lets_the_new_credentials_survive_a_lost_token(client):
    """The scenario this whole feature exists for: the browser token is gone,
    but the account (and its data) is reachable again through /login."""
    guest = client.post("/api/auth/guest").json()
    headers = {"Authorization": f"Bearer {guest['access_token']}"}

    client.post(
        "/api/auth/convert-guest",
        headers=headers,
        json={"email": "recoverable@example.com", "password": "SuperSecret123"},
    )

    # Simulate a cleared browser: no token carried over, only the credentials.
    login = client.post(
        "/api/auth/login",
        json={"email": "recoverable@example.com", "password": "SuperSecret123"},
    )
    assert login.status_code == 200
    assert login.json()["user"]["is_guest"] is False
