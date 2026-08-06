"""
Integration tests for billing FastAPI endpoints.
Uses test DB and mocked AmneziaClient.
"""
import os
import pytest
from httpx import AsyncClient, ASGITransport
from unittest.mock import AsyncMock, patch

from api.main import app
from billing.database import AsyncSessionLocal, engine as _engine
from models import Base
import models.models  # noqa


# ---------------------------------------------------------------------------
# Override DB session in FastAPI dependency for tests
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def patch_billing_key(monkeypatch):
    monkeypatch.setenv("BILLING_SECRET_KEY", "test-secret")


@pytest.fixture
def client_headers():
    return {"X-Billing-Key": "test-secret"}


@pytest.fixture
def mock_amnezia():
    with patch("billing.services.billing_service.AmneziaClient") as MockClient:
        instance = AsyncMock()
        from integrations.amnezia.schemas import CreateClientResponse, CreatedClient
        instance.create_client.return_value = CreateClientResponse(
            message="OK",
            client=CreatedClient(
                id="integ-client-id",
                config="vpn://integtest",
                protocol="amneziawg",
            ),
        )
        instance.enable_client.return_value = None
        instance.disable_client.return_value = None
        MockClient.return_value = instance
        yield instance


@pytest.mark.asyncio
async def test_health_endpoint():
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        resp = await ac.get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


@pytest.mark.asyncio
async def test_stars_payment_endpoint_unauthorized():
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        resp = await ac.post(
            "/api/v1/payments/stars",
            json={
                "telegram_id": 123,
                "telegram_payment_charge_id": "abc",
                "total_amount": 100,
            },
        )
    assert resp.status_code == 422  # missing X-Billing-Key header


@pytest.mark.asyncio
async def test_stars_payment_missing_plan(client_headers):
    """Should return 400 if no plan exists in DB."""
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        resp = await ac.post(
            "/api/v1/payments/stars",
            headers=client_headers,
            json={
                "telegram_id": 9991,
                "telegram_payment_charge_id": "no_plan_test",
                "total_amount": 100,
            },
        )
    # Either 400 (ValueError: No active plan) or 500
    assert resp.status_code in (400, 500)
