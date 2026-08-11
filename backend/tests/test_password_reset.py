"""Password reset: issuing, redeeming, and the ways it must refuse."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.models import PasswordResetToken, User
from app.routers import auth as auth_router
from app.security import hash_reset_token
from app.services.mail import MailError

from .conftest import register


@pytest.fixture
def captured(monkeypatch) -> list[dict]:
    """Intercept delivery and record what would have been mailed."""
    sent: list[dict] = []

    def _capture(*, to: str, name: str, token: str) -> None:
        sent.append({"to": to, "name": name, "token": token})

    monkeypatch.setattr(auth_router, "send_password_reset", _capture)
    return sent


def _request_reset(client: TestClient, email: str):
    return client.post("/api/auth/forgot-password", json={"email": email})


def _reset(client: TestClient, token: str, password: str = "BrandNewSecret123"):
    return client.post(
        "/api/auth/reset-password",
        json={"token": token, "password": password, "confirm_password": password},
    )


def test_full_reset_flow_changes_the_password(client, captured):
    account = register(client)

    assert _request_reset(client, account["email"]).status_code == 200
    assert len(captured) == 1
    token = captured[0]["token"]

    response = _reset(client, token)
    assert response.status_code == 200, response.text

    # The old password no longer works, the new one does.
    old = client.post(
        "/api/auth/login", json={"email": account["email"], "password": account["password"]}
    )
    assert old.status_code == 401
    new = client.post(
        "/api/auth/login", json={"email": account["email"], "password": "BrandNewSecret123"}
    )
    assert new.status_code == 200


def test_unknown_email_is_indistinguishable(client, captured):
    account = register(client)

    known = _request_reset(client, account["email"])
    unknown = _request_reset(client, f"nobody-{uuid.uuid4().hex[:8]}@example.com")

    # Same status and same body: nothing here reveals who has an account.
    assert known.status_code == unknown.status_code == 200
    assert known.json() == unknown.json()
    assert [item["to"] for item in captured] == [account["email"]]


def test_token_is_single_use(client, captured):
    register(client)
    account = register(client)
    _request_reset(client, account["email"])
    token = captured[-1]["token"]

    assert _reset(client, token).status_code == 200
    second = _reset(client, token, password="YetAnotherSecret123")
    assert second.status_code == 422
    assert second.json()["error"]["code"] == "validation_error"


def test_expired_token_is_refused(client, captured, db):
    account = register(client)
    _request_reset(client, account["email"])
    token = captured[-1]["token"]

    record = db.scalar(
        select(PasswordResetToken).where(PasswordResetToken.token_hash == hash_reset_token(token))
    )
    record.expires_at = datetime.now(UTC) - timedelta(minutes=1)
    db.commit()

    assert _reset(client, token).status_code == 422


def test_unknown_token_is_refused(client):
    assert _reset(client, "a" * 43).status_code == 422


def test_plaintext_token_is_never_stored(client, captured, db):
    account = register(client)
    _request_reset(client, account["email"])
    token = captured[-1]["token"]

    stored = db.scalars(select(PasswordResetToken.token_hash)).all()
    assert token not in stored
    assert hash_reset_token(token) in stored


def test_requesting_a_second_link_retires_the_first(client, captured):
    account = register(client)
    _request_reset(client, account["email"])
    first = captured[-1]["token"]
    _request_reset(client, account["email"])
    second = captured[-1]["token"]

    assert first != second
    assert _reset(client, first).status_code == 422
    assert _reset(client, second, password="SecondSecret123").status_code == 200


def test_mail_failure_does_not_leak_or_500(client, monkeypatch):
    """A broken mail transport must not become an enumeration oracle."""
    account = register(client)

    def _explode(**kwargs) -> None:
        raise MailError("smtp is down")

    monkeypatch.setattr(auth_router, "send_password_reset", _explode)

    response = _request_reset(client, account["email"])
    assert response.status_code == 200
    assert response.json()["message"]


def test_reset_refused_for_a_disabled_account(client, captured, db):
    account = register(client)
    _request_reset(client, account["email"])
    token = captured[-1]["token"]

    user = db.scalar(select(User).where(User.email == account["email"]))
    user.is_active = False
    db.commit()

    assert _reset(client, token).status_code == 422


def test_mismatched_confirmation_is_rejected(client, captured):
    account = register(client)
    _request_reset(client, account["email"])
    token = captured[-1]["token"]

    response = client.post(
        "/api/auth/reset-password",
        json={"token": token, "password": "OneSecret123", "confirm_password": "OtherSecret123"},
    )
    assert response.status_code == 422
