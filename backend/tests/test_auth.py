from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
@pytest.mark.parametrize("available", [True, False])
async def test_health_check(client: AsyncClient, monkeypatch, available):
    import redis.asyncio

    import app.database

    connection = AsyncMock()
    manager = MagicMock()
    manager.__aenter__ = AsyncMock(return_value=connection)
    manager.__aexit__ = AsyncMock(return_value=False)
    monkeypatch.setattr(app.database, "engine", SimpleNamespace(connect=lambda: manager))
    cache = AsyncMock()
    if not available:
        cache.ping.side_effect = ConnectionError("Synthetic dependency failure")
    monkeypatch.setattr(redis.asyncio, "from_url", lambda _: cache)
    response = await client.get("/api/v1/health")
    assert response.status_code == (200 if available else 503)
    data = response.json()
    assert data["status"] == ("healthy" if available else "degraded")
    assert data["version"] == "2.0.0"
    assert "checks" in data


@pytest.mark.asyncio
async def test_register_weak_password(client: AsyncClient):
    response = await client.post(
        "/api/v1/auth/register",
        json={
            "email": "test@example.com",
            "password": "weak",
            "full_name": "Test User",
        },
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_register_invalid_email(client: AsyncClient):
    response = await client.post(
        "/api/v1/auth/register",
        json={
            "email": "not-an-email",
            "password": "StrongPass1",
            "full_name": "Test User",
        },
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_register_short_name(client: AsyncClient):
    response = await client.post(
        "/api/v1/auth/register",
        json={
            "email": "test@example.com",
            "password": "StrongPass1",
            "full_name": "A",
        },
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_register_missing_fields(client: AsyncClient):
    response = await client.post(
        "/api/v1/auth/register",
        json={
            "email": "test@example.com",
        },
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_login_missing_fields(client: AsyncClient):
    response = await client.post("/api/v1/auth/login", json={})
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_me_unauthenticated(client: AsyncClient):
    response = await client.get("/api/v1/auth/me")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_me_invalid_token(client: AsyncClient):
    response = await client.get(
        "/api/v1/auth/me",
        headers={"Authorization": "Bearer invalid-token"},
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_logout_unauthenticated(client: AsyncClient):
    response = await client.post("/api/v1/auth/logout")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_refresh_invalid_token(client: AsyncClient):
    response = await client.post(
        "/api/v1/auth/refresh",
        json={
            "refresh_token": "invalid-token",
        },
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_password_no_uppercase(client: AsyncClient):
    response = await client.post(
        "/api/v1/auth/register",
        json={
            "email": "test@example.com",
            "password": "alllowercase1",
            "full_name": "Test User",
        },
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_password_no_digit(client: AsyncClient):
    response = await client.post(
        "/api/v1/auth/register",
        json={
            "email": "test@example.com",
            "password": "NoDigitHere",
            "full_name": "Test User",
        },
    )
    assert response.status_code == 422
