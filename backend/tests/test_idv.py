import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_kyc_submit_unauthenticated(client: AsyncClient):
    response = await client.post("/api/v1/kyc/submit")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_kyc_status_unauthenticated(client: AsyncClient):
    response = await client.get("/api/v1/kyc/status")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_upload_document_unauthenticated(client: AsyncClient):
    response = await client.post("/api/v1/kyc/upload-document")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_upload_selfie_unauthenticated(client: AsyncClient):
    response = await client.post("/api/v1/kyc/upload-selfie")
    assert response.status_code == 401
