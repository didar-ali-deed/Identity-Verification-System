import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_admin_list_unauthenticated(client: AsyncClient):
    response = await client.get("/api/v1/admin/applications")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_admin_stats_unauthenticated(client: AsyncClient):
    response = await client.get("/api/v1/admin/stats")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_admin_detail_unauthenticated(client: AsyncClient):
    response = await client.get(
        "/api/v1/admin/applications/00000000-0000-0000-0000-000000000000"
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_admin_review_unauthenticated(client: AsyncClient):
    response = await client.patch(
        "/api/v1/admin/applications/00000000-0000-0000-0000-000000000000",
        json={"action": "approve"},
    )
    assert response.status_code == 401
