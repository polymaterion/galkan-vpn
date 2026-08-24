"""
Integration tests for the trial-period endpoints (api/routers/trial.py) and
the broadcast recipient-id endpoint (api/routers/admin.py).

Unlike tests/integration/test_api.py, this file creates the schema against
the app's actual engine itself (Base.metadata.create_all) rather than
assuming it already exists — see the note in test_api.py's
test_stars_payment_missing_plan, which fails independently of this change
because nothing in that file creates the schema either.
"""
import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from unittest.mock import AsyncMock, patch

from api.main import app
from billing.database import AsyncSessionLocal, engine as _engine
from models import Base
import models.models  # noqa: F401
from models.models import Plan, User, VpnServer, VpnServerStatus


@pytest_asyncio.fixture(autouse=True)
async def _schema():
    async with _engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with _engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


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
            client=CreatedClient(id="trial-client-id", config="vpn://trialtest", protocol="amneziawg"),
        )
        instance.enable_client.return_value = None
        instance.disable_client.return_value = None
        MockClient.return_value = instance
        yield instance


async def _seed_trial_plan():
    async with AsyncSessionLocal() as session:
        session.add(
            Plan(
                name="Trial",
                duration_days=3,
                price_stars=0,
                price_usdt=0,
                is_active=True,
                is_trial=True,
            )
        )
        session.add(
            VpnServer(
                name="Test Server",
                base_url="http://test-vpn:4001",
                api_key="key",
                region="EU",
                weight=100,
                status=VpnServerStatus.active,
                max_clients=500,
                current_clients=0,
            )
        )
        await session.commit()


@pytest.mark.asyncio
async def test_trial_eligible_true_when_no_trial_plan(client_headers):
    # No plan seeded at all -> not eligible.
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.get(
            "/api/v1/trial/eligible", params={"telegram_id": 111}, headers=client_headers
        )
    assert resp.status_code == 200
    assert resp.json() is False


@pytest.mark.asyncio
async def test_trial_eligible_true_for_new_user(mock_amnezia, client_headers):
    await _seed_trial_plan()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.get(
            "/api/v1/trial/eligible", params={"telegram_id": 222}, headers=client_headers
        )
    assert resp.status_code == 200
    assert resp.json() is True


@pytest.mark.asyncio
async def test_grant_trial_endpoint_success(mock_amnezia, client_headers):
    await _seed_trial_plan()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.post(
            "/api/v1/trial/grant",
            json={"telegram_id": 333, "username": "u", "first_name": "F", "last_name": None},
            headers=client_headers,
        )
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "active"
    assert data["subscription_id"] is not None


@pytest.mark.asyncio
async def test_grant_trial_endpoint_rejects_second_call(mock_amnezia, client_headers):
    await _seed_trial_plan()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        first = await ac.post(
            "/api/v1/trial/grant",
            json={"telegram_id": 444, "username": None, "first_name": None, "last_name": None},
            headers=client_headers,
        )
        assert first.status_code == 200

        second = await ac.post(
            "/api/v1/trial/grant",
            json={"telegram_id": 444, "username": None, "first_name": None, "last_name": None},
            headers=client_headers,
        )
    assert second.status_code == 400

    # eligible should now report False for this user too.
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.get(
            "/api/v1/trial/eligible", params={"telegram_id": 444}, headers=client_headers
        )
    assert resp.json() is False


@pytest.mark.asyncio
async def test_grant_trial_endpoint_no_plan_returns_400(client_headers):
    # No trial plan seeded at all.
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.post(
            "/api/v1/trial/grant",
            json={"telegram_id": 555, "username": None, "first_name": None, "last_name": None},
            headers=client_headers,
        )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_broadcast_ids_returns_every_seen_user(client_headers):
    async with AsyncSessionLocal() as session:
        session.add(User(telegram_id=1001, username="a"))
        session.add(User(telegram_id=1002, username="b"))
        session.add(User(telegram_id=1003, username="banned_user", is_banned=True))
        await session.commit()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.get("/api/v1/admin/users/broadcast_ids", headers=client_headers)

    assert resp.status_code == 200
    data = resp.json()
    assert set(data["telegram_ids"]) == {1001, 1002}
    assert data["total"] == 2


@pytest.mark.asyncio
async def test_broadcast_ids_requires_auth():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.get("/api/v1/admin/users/broadcast_ids")
    assert resp.status_code in (401, 403, 422)
