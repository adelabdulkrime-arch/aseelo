"""Post-payment account activation: redeeming a charge, and the refusals."""

from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.models import BrandProfile, PaymentCharge, User

from .conftest import register

PASSWORD = "ChosenAtCheckout123"


@pytest.fixture
def charge(db) -> PaymentCharge:
    """An unredeemed charge, as a payment webhook or import would leave it."""
    record = PaymentCharge(
        charge_id=f"ch_{uuid.uuid4().hex[:20]}",
        email=f"buyer-{uuid.uuid4().hex[:10]}@example.com",
    )
    db.add(record)
    db.commit()
    db.refresh(record)
    return record


def _setup(client: TestClient, email: str, charge_id: str, password: str = PASSWORD):
    return client.post(
        "/api/auth/setup-account",
        json={"email": email, "charge_id": charge_id, "password": password},
    )


# ---------------------------------------------------------------------------
# The happy path
# ---------------------------------------------------------------------------
def test_redeeming_a_charge_creates_a_usable_account(client, db, charge):
    response = _setup(client, charge.email, charge.charge_id)
    assert response.status_code == 201, response.text

    body = response.json()
    assert body["user"]["email"] == charge.email
    assert body["token_type"] == "bearer"

    # The returned token must work immediately - the whole point is that the
    # customer lands on the dashboard without a second sign-in.
    me = client.get("/api/auth/me", headers={"Authorization": f"Bearer {body['access_token']}"})
    assert me.status_code == 200
    assert me.json()["email"] == charge.email

    # ...and the ordinary login path works too, with the password they chose.
    login = client.post("/api/auth/login", json={"email": charge.email, "password": PASSWORD})
    assert login.status_code == 200, login.text


def test_redemption_generates_a_default_brand_profile(client, db, charge):
    assert _setup(client, charge.email, charge.charge_id).status_code == 201

    user = db.scalar(select(User).where(User.email == charge.email))
    profile = db.scalar(select(BrandProfile).where(BrandProfile.user_id == user.id))
    assert profile is not None
    assert profile.brand_name == f"{user.name}'s Brand"
    # Defaults come from the column definitions; a blank profile would make the
    # first render fall back to nothing.
    assert profile.primary_color.startswith("#")


def test_redemption_marks_the_charge_used_and_links_the_account(client, db, charge):
    assert _setup(client, charge.email, charge.charge_id).status_code == 201

    db.expire_all()
    stored = db.scalar(select(PaymentCharge).where(PaymentCharge.charge_id == charge.charge_id))
    user = db.scalar(select(User).where(User.email == charge.email))
    assert stored.is_used is True
    assert stored.used_at is not None
    assert stored.user_id == user.id


def test_name_is_derived_from_the_email_local_part(client, db):
    record = PaymentCharge(charge_id=f"ch_{uuid.uuid4().hex[:20]}", email="adel.ali@example.com")
    db.add(record)
    db.commit()

    response = _setup(client, "adel.ali@example.com", record.charge_id)
    assert response.status_code == 201, response.text
    assert response.json()["user"]["name"] == "Adel Ali"


def test_single_character_local_part_falls_back_to_a_valid_name(client, db):
    record = PaymentCharge(charge_id=f"ch_{uuid.uuid4().hex[:20]}", email="a@example.com")
    db.add(record)
    db.commit()

    response = _setup(client, "a@example.com", record.charge_id)
    assert response.status_code == 201, response.text
    # users.name is NOT NULL and the UI greets the user by it.
    assert len(response.json()["user"]["name"]) >= 2


# ---------------------------------------------------------------------------
# The refusals
# ---------------------------------------------------------------------------
def test_a_charge_cannot_be_redeemed_twice(client, db, charge):
    assert _setup(client, charge.email, charge.charge_id).status_code == 201

    # The link sits in an inbox forever; a second click must not mint anything.
    again = _setup(client, charge.email, charge.charge_id, password="DifferentSecret123")
    assert again.status_code == 422, again.text
    assert again.json()["error"]["code"] == "validation_error"

    # ...and it certainly must not have changed the password of the account the
    # first click created.
    login = client.post("/api/auth/login", json={"email": charge.email, "password": PASSWORD})
    assert login.status_code == 200


def test_unknown_charge_is_refused(client):
    response = _setup(client, "nobody@example.com", "ch_does_not_exist_at_all")
    assert response.status_code == 422


def test_charge_bound_to_a_different_email_is_refused(client, db, charge):
    """Holding a charge reference must not let you claim it for your own address."""
    response = _setup(client, "attacker@example.com", charge.charge_id)
    assert response.status_code == 422

    assert db.scalar(select(User).where(User.email == "attacker@example.com")) is None
    db.expire_all()
    stored = db.scalar(select(PaymentCharge).where(PaymentCharge.charge_id == charge.charge_id))
    assert stored.is_used is False


def test_unknown_and_mismatched_charges_are_indistinguishable(client, charge):
    """Otherwise the endpoint confirms which charge references exist."""
    unknown = _setup(client, "attacker@example.com", "ch_does_not_exist_at_all")
    mismatched = _setup(client, "attacker@example.com", charge.charge_id)

    assert unknown.status_code == mismatched.status_code
    assert unknown.json()["error"] == mismatched.json()["error"]


def test_email_match_is_case_insensitive(client, db, charge):
    """Providers echo back whatever the customer typed; it is the same mailbox."""
    response = _setup(client, charge.email.upper(), charge.charge_id)
    assert response.status_code == 201, response.text


def test_account_created_from_an_uppercase_link_can_still_log_in(client, db, charge):
    """Regression: a 201 here used to produce an account nobody could sign in to.

    The address comes from a URL the customer never typed, so if the row is
    stored with the link's casing and login compares exactly, they are locked
    out of the account they just paid for. Nothing threw and every other test
    passed.
    """
    assert _setup(client, charge.email.upper(), charge.charge_id).status_code == 201

    login = client.post(
        "/api/auth/login", json={"email": charge.email.lower(), "password": PASSWORD}
    )
    assert login.status_code == 200, login.text

    stored = db.scalar(select(User).where(func.lower(User.email) == charge.email.lower()))
    assert stored.email == charge.email.lower()


def test_takeover_guard_is_not_bypassed_by_changing_case(client, db):
    """Otherwise the duplicate-account check is one shift key away from useless."""
    victim = register(client)
    record = PaymentCharge(
        charge_id=f"ch_{uuid.uuid4().hex[:20]}", email=victim["email"].upper()
    )
    db.add(record)
    db.commit()

    response = _setup(client, victim["email"].upper(), record.charge_id)
    assert response.status_code == 409, response.text

    # Exactly one account for that mailbox, and it is still the victim's.
    matches = db.scalars(
        select(User).where(func.lower(User.email) == victim["email"].lower())
    ).all()
    assert len(matches) == 1


def test_existing_account_is_not_taken_over(client, db):
    """Paying with someone else's address must not reset their password."""
    victim = register(client)
    record = PaymentCharge(charge_id=f"ch_{uuid.uuid4().hex[:20]}", email=victim["email"])
    db.add(record)
    db.commit()

    response = _setup(client, victim["email"], record.charge_id, password="AttackerChosen123")
    assert response.status_code == 409, response.text
    assert response.json()["error"]["code"] == "conflict"

    # The victim's original password still works and the attacker's does not.
    assert (
        client.post(
            "/api/auth/login", json={"email": victim["email"], "password": victim["password"]}
        ).status_code
        == 200
    )
    assert (
        client.post(
            "/api/auth/login", json={"email": victim["email"], "password": "AttackerChosen123"}
        ).status_code
        == 401
    )

    # The charge is left unspent so support can still refund or reassign it.
    db.expire_all()
    stored = db.scalar(select(PaymentCharge).where(PaymentCharge.charge_id == record.charge_id))
    assert stored.is_used is False


def test_short_password_is_rejected(client, charge):
    response = _setup(client, charge.email, charge.charge_id, password="short")
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"


def test_malformed_email_is_rejected(client, charge):
    assert _setup(client, "not-an-email", charge.charge_id).status_code == 422


# ---------------------------------------------------------------------------
# The pre-existing flows must be untouched
# ---------------------------------------------------------------------------
def test_register_and_login_still_work_without_any_charge(client):
    """No charge exists for these accounts; the ordinary path must not require one."""
    account = register(client)
    response = client.post(
        "/api/auth/login", json={"email": account["email"], "password": account["password"]}
    )
    assert response.status_code == 200, response.text


def test_activated_account_can_use_the_password_reset_flow(client, db, charge, monkeypatch):
    """An account created by redemption is an ordinary account in every respect."""
    sent: list[str] = []
    monkeypatch.setattr(
        "app.routers.auth.send_password_reset",
        lambda *, to, name, token: sent.append(token),
    )

    assert _setup(client, charge.email, charge.charge_id).status_code == 201
    assert client.post("/api/auth/forgot-password", json={"email": charge.email}).status_code == 200
    assert len(sent) == 1

    reset = client.post(
        "/api/auth/reset-password",
        json={"token": sent[0], "password": "AfterReset12345", "confirm_password": "AfterReset12345"},
    )
    assert reset.status_code == 200, reset.text
