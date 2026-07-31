"""Authentication and authorization."""

from __future__ import annotations

from tests.conftest import register


def test_register_creates_user_and_default_brand(client):
    account = register(client)
    assert account["user"]["role"] == "USER"

    brand = client.get("/api/brand", headers=account["headers"])
    assert brand.status_code == 200
    assert brand.json()["brand_name"] == "Test User's Brand"


def test_register_rejects_duplicate_email(client):
    account = register(client)
    response = client.post(
        "/api/auth/register",
        json={
            "name": "Other",
            "email": account["email"],
            "password": "SuperSecret123",
            "confirm_password": "SuperSecret123",
        },
    )
    assert response.status_code == 409


def test_register_rejects_mismatched_passwords(client):
    response = client.post(
        "/api/auth/register",
        json={
            "name": "Test",
            "email": "mismatch@example.com",
            "password": "SuperSecret123",
            "confirm_password": "DifferentPass123",
        },
    )
    assert response.status_code == 422


def test_register_rejects_short_password(client):
    response = client.post(
        "/api/auth/register",
        json={
            "name": "Test",
            "email": "short@example.com",
            "password": "short",
            "confirm_password": "short",
        },
    )
    assert response.status_code == 422


def test_login_returns_token(client, user):
    response = client.post(
        "/api/auth/login", json={"email": user["email"], "password": user["password"]}
    )
    assert response.status_code == 200
    assert response.json()["access_token"]


def test_login_rejects_wrong_password(client, user):
    response = client.post(
        "/api/auth/login", json={"email": user["email"], "password": "WrongPassword1"}
    )
    assert response.status_code == 401


def test_me_requires_token(client):
    assert client.get("/api/auth/me").status_code == 401


def test_me_rejects_garbage_token(client):
    response = client.get("/api/auth/me", headers={"Authorization": "Bearer not-a-real-token"})
    assert response.status_code == 401


def test_me_returns_current_user(client, user):
    response = client.get("/api/auth/me", headers=user["headers"])
    assert response.status_code == 200
    assert response.json()["email"] == user["email"]


def test_arabic_password_round_trips(client):
    """bcrypt truncates at 72 bytes; multi-byte passwords must still verify."""
    password = "كلمة-المرور-الطويلة-جدا-جدا-جدا-جدا-جدا-للاختبار"
    account = register(client, password=password)
    response = client.post(
        "/api/auth/login", json={"email": account["email"], "password": password}
    )
    assert response.status_code == 200
