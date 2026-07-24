"""
Unit tests for BillingService core logic.
All external calls (Amnezia API) are mocked.
"""
import pytest
import pytest_asyncio
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

from sqlalchemy import select
from billing.services.billing_service import BillingService
from billing.repositories.other_repos import PlanRepository, VpnClientRepository
from billing.repositories.server_repo import VpnServerRepository
from billing.repositories.subscription_repo import SubscriptionRepository
from billing.repositories.user_repo import UserRepository
from models.models import (
    Plan,
    SubscriptionStatus,
    VpnClient,
    VpnServer,
    VpnServerStatus,
    VpnClientStatus,
    PaymentProvider,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _seed_plan(session) -> Plan:
    plan = Plan(
        name="Test Plan",
        duration_days=30,
        price_stars=100,
        price_usdt=3.0,
        is_active=True,
    )
    session.add(plan)
    await session.flush()
    return plan


async def _seed_server(session) -> VpnServer:
    server = VpnServer(
        name="Test Server",
        base_url="http://test-vpn:4001",
        api_key="test-api-key",
        region="EU",
        weight=100,
        status=VpnServerStatus.active,
        max_clients=500,
        current_clients=0,
    )
    session.add(server)
    await session.flush()
    return server


# ---------------------------------------------------------------------------
# Test: Stars payment - new user, new subscription
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_stars_payment_creates_subscription(session, mock_amnezia_client):
    await _seed_plan(session)
    await _seed_server(session)
    await session.commit()

    svc = BillingService()
    sub = await svc.handle_payment(
        session,
        telegram_id=111,
        username="testuser",
        first_name="Test",
        last_name=None,
        provider=PaymentProvider.stars,
        external_id="charge_abc123",
        amount=100,
        currency="XTR",
    )
    await session.commit()

    # Re-fetch with relationships eagerly loaded
    from sqlalchemy.orm import joinedload
    result = await session.execute(
        select(type(sub)).options(joinedload(type(sub).vpn_client))
        .where(type(sub).id == sub.id)
    )
    sub = result.unique().scalar_one()

    assert sub is not None
    assert sub.status == SubscriptionStatus.active
    assert sub.vpn_client is not None
    assert sub.vpn_client.amnezia_client_id == "test-uuid-1234"
    assert sub.vpn_client.config_url == "vpn://eyJ0ZXN0IjoiY29uZmlnIn0="
    assert sub.expires_at is not None
    assert sub.expires_at.replace(tzinfo=timezone.utc) > datetime.now(timezone.utc)

    mock_amnezia_client.create_client.assert_called_once()


# ---------------------------------------------------------------------------
# Test: USDT payment
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_usdt_payment_creates_subscription(session, mock_amnezia_client):
    await _seed_plan(session)
    await _seed_server(session)
    await session.commit()

    svc = BillingService()
    sub = await svc.handle_payment(
        session,
        telegram_id=222,
        username=None,
        first_name="Alice",
        last_name=None,
        provider=PaymentProvider.usdt,
        external_id="invoice_xyz999",
        amount=3.0,
        currency="USDT",
    )
    await session.commit()

    from sqlalchemy.orm import joinedload
    result = await session.execute(
        select(type(sub)).options(joinedload(type(sub).vpn_client))
        .where(type(sub).id == sub.id)
    )
    sub = result.unique().scalar_one()

    assert sub.status == SubscriptionStatus.active
    assert sub.vpn_client is not None


# ---------------------------------------------------------------------------
# Test: Duplicate payment is idempotent
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_duplicate_payment_is_idempotent(session, mock_amnezia_client):
    await _seed_plan(session)
    await _seed_server(session)
    await session.commit()

    svc = BillingService()
    kwargs = dict(
        telegram_id=333,
        username="dup",
        first_name="Dup",
        last_name=None,
        provider=PaymentProvider.stars,
        external_id="charge_dup_001",
        amount=100,
        currency="XTR",
    )
    sub1 = await svc.handle_payment(session, **kwargs)
    await session.commit()

    try:
        sub2 = await svc.handle_payment(session, **kwargs)
        assert sub2.id == sub1.id
    except ValueError as e:
        assert "Duplicate" in str(e)

    assert mock_amnezia_client.create_client.call_count == 1


# ---------------------------------------------------------------------------
# Test: default mode="new" always creates a brand-new device, even for the
# same telegram_id paying twice — this is the hard "1 payment = 1 device" rule.
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_repeat_payment_creates_new_device_by_default(session, mock_amnezia_client):
    await _seed_plan(session)
    await _seed_server(session)
    await session.commit()

    svc = BillingService()

    sub = await svc.handle_payment(
        session,
        telegram_id=444,
        username=None,
        first_name="Bob",
        last_name=None,
        provider=PaymentProvider.stars,
        external_id="charge_device_1",
        amount=100,
        currency="XTR",
    )
    await session.commit()

    sub2 = await svc.handle_payment(
        session,
        telegram_id=444,  # same user
        username=None,
        first_name="Bob",
        last_name=None,
        provider=PaymentProvider.stars,
        external_id="charge_device_2",  # different payment
        amount=100,
        currency="XTR",
        # mode defaults to "new"
    )
    await session.commit()

    assert sub2.id != sub.id, "A second payment must provision a second device, not extend the first"
    assert mock_amnezia_client.create_client.call_count == 2

    user_repo = UserRepository(session)
    user = await user_repo.get_by_telegram_id(444)
    sub_repo = SubscriptionRepository(session)
    all_devices = await sub_repo.get_all_for_user(user.id)
    assert len(all_devices) == 2


# ---------------------------------------------------------------------------
# Test: mode="renew" extends the ONE specific device given by
# target_subscription_id, and does not create a new one.
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_explicit_renew_extends_specific_device(session, mock_amnezia_client):
    await _seed_plan(session)
    await _seed_server(session)
    await session.commit()

    svc = BillingService()

    sub = await svc.handle_payment(
        session,
        telegram_id=445,
        username=None,
        first_name="Carol",
        last_name=None,
        provider=PaymentProvider.stars,
        external_id="charge_renew_base",
        amount=100,
        currency="XTR",
    )
    await session.commit()
    first_expiry = sub.expires_at

    sub2 = await svc.handle_payment(
        session,
        telegram_id=445,
        username=None,
        first_name="Carol",
        last_name=None,
        provider=PaymentProvider.stars,
        external_id="charge_renew_actual",
        amount=100,
        currency="XTR",
        mode="renew",
        target_subscription_id=sub.id,
    )
    await session.commit()

    assert sub2.id == sub.id, "Explicit renew must extend the SAME device, not create a new one"
    assert sub2.expires_at > first_expiry

    user_repo = UserRepository(session)
    user = await user_repo.get_by_telegram_id(445)
    sub_repo = SubscriptionRepository(session)
    all_devices = await sub_repo.get_all_for_user(user.id)
    assert len(all_devices) == 1, "Renewing must not create a second device"


@pytest.mark.asyncio
async def test_renew_rejects_another_users_subscription(session, mock_amnezia_client):
    await _seed_plan(session)
    await _seed_server(session)
    await session.commit()

    svc = BillingService()

    victim_sub = await svc.handle_payment(
        session,
        telegram_id=446,
        username=None,
        first_name="Victim",
        last_name=None,
        provider=PaymentProvider.stars,
        external_id="charge_victim",
        amount=100,
        currency="XTR",
    )
    await session.commit()

    with pytest.raises(ValueError):
        await svc.handle_payment(
            session,
            telegram_id=447,  # different user
            username=None,
            first_name="Attacker",
            last_name=None,
            provider=PaymentProvider.stars,
            external_id="charge_attacker",
            amount=100,
            currency="XTR",
            mode="renew",
            target_subscription_id=victim_sub.id,
        )


@pytest.mark.asyncio
async def test_renew_without_target_id_raises(session, mock_amnezia_client):
    await _seed_plan(session)
    await _seed_server(session)
    await session.commit()

    svc = BillingService()

    with pytest.raises(ValueError):
        await svc.handle_payment(
            session,
            telegram_id=448,
            username=None,
            first_name="NoTarget",
            last_name=None,
            provider=PaymentProvider.stars,
            external_id="charge_no_target",
            amount=100,
            currency="XTR",
            mode="renew",
            target_subscription_id=None,
        )


# ---------------------------------------------------------------------------
# Test: Subscription expiry disables client
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_expiry_disables_subscription(session, mock_amnezia_client):
    await _seed_plan(session)
    await _seed_server(session)
    await session.commit()

    svc = BillingService()

    sub = await svc.handle_payment(
        session,
        telegram_id=555,
        username=None,
        first_name="Expired",
        last_name=None,
        provider=PaymentProvider.stars,
        external_id="charge_expire_test",
        amount=100,
        currency="XTR",
    )
    await session.commit()

    # Force-expire: use naive datetime to match SQLite
    from sqlalchemy import update
    from models.models import Subscription
    await session.execute(
        update(Subscription)
        .where(Subscription.id == sub.id)
        .values(expires_at=datetime(2020, 1, 1))
    )
    await session.commit()

    with patch(
        "billing.services.billing_service.AsyncSessionLocal"
    ) as mock_session_factory:
        mock_session_factory.return_value.__aenter__ = AsyncMock(return_value=session)
        mock_session_factory.return_value.__aexit__ = AsyncMock(return_value=False)

        count = await svc.disable_expired_subscriptions()

    assert count >= 1
    mock_amnezia_client.disable_client.assert_called_once()


# ---------------------------------------------------------------------------
# Test: Amnezia API error → pending_provisioning
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_amnezia_error_sets_pending_provisioning(session, mock_amnezia_client):
    await _seed_plan(session)
    await _seed_server(session)
    await session.commit()

    from integrations.amnezia.errors import AmneziaConnectionError
    mock_amnezia_client.create_client.side_effect = AmneziaConnectionError("Connection refused")

    svc = BillingService()
    sub = await svc.handle_payment(
        session,
        telegram_id=666,
        username=None,
        first_name="Error",
        last_name=None,
        provider=PaymentProvider.stars,
        external_id="charge_error_001",
        amount=100,
        currency="XTR",
    )

    assert sub.status == SubscriptionStatus.pending_provisioning
    # No VpnClient should have been created
    vc_result = await session.execute(
        select(VpnClient).where(VpnClient.subscription_id == sub.id)
    )
    assert vc_result.scalar_one_or_none() is None


# ---------------------------------------------------------------------------
# Test: Server selection — weight × (1-load)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_server_selection_by_load(session):
    server_a = VpnServer(
        name="A", base_url="http://a:4001", api_key="k",
        region="EU", weight=100, status=VpnServerStatus.active,
        max_clients=100, current_clients=90,
    )
    server_b = VpnServer(
        name="B", base_url="http://b:4001", api_key="k",
        region="EU", weight=100, status=VpnServerStatus.active,
        max_clients=100, current_clients=5,
    )
    session.add_all([server_a, server_b])
    await session.commit()

    repo = VpnServerRepository(session)
    picks = {"A": 0, "B": 0}
    for _ in range(50):
        s = await repo.select_server()
        picks[s.name] += 1

    assert picks["B"] > picks["A"], f"Expected B to win more, got {picks}"


# ---------------------------------------------------------------------------
# Test: Disabled server is never selected
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_disabled_server_not_selected(session):
    session.add(VpnServer(
        name="Off", base_url="http://off:4001", api_key="k",
        region="EU", weight=1000, status=VpnServerStatus.disabled,
        max_clients=500, current_clients=0,
    ))
    session.add(VpnServer(
        name="On", base_url="http://on:4001", api_key="k",
        region="EU", weight=1, status=VpnServerStatus.active,
        max_clients=500, current_clients=0,
    ))
    await session.commit()

    repo = VpnServerRepository(session)
    for _ in range(10):
        s = await repo.select_server()
        assert s.name == "On"


# ---------------------------------------------------------------------------
# Test: Amnezia adapter create_client HTTP schema
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_amnezia_client_create():
    import respx
    import httpx
    from integrations.amnezia.client import AmneziaClient
    from integrations.amnezia.schemas import CreateClientRequest

    with respx.mock(base_url="http://vpn:4001") as mock:
        mock.post("/clients").mock(
            return_value=httpx.Response(
                200,
                json={
                    "message": "Клиент создан",
                    "client": {
                        "id": "abc-123",
                        "config": "vpn://somebase64",
                        "protocol": "amneziawg",
                    },
                },
            )
        )
        client = AmneziaClient(base_url="http://vpn:4001", api_key="mykey")
        resp = await client.create_client(
            CreateClientRequest(clientName="test_user", protocol="amneziawg")
        )

    assert resp.client.id == "abc-123"
    assert resp.client.config == "vpn://somebase64"
    assert resp.client.protocol == "amneziawg"


# ---------------------------------------------------------------------------
# Test: Admin extend subscription
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_admin_extend_subscription(session, mock_amnezia_client):
    await _seed_plan(session)
    await _seed_server(session)
    await session.commit()

    svc = BillingService()
    sub = await svc.handle_payment(
        session,
        telegram_id=777,
        username=None,
        first_name="Admin",
        last_name=None,
        provider=PaymentProvider.stars,
        external_id="charge_admin_extend",
        amount=100,
        currency="XTR",
    )
    await session.commit()
    original_expiry = sub.expires_at

    await svc.admin_extend_subscription(session, sub.id, days=15)
    await session.commit()

    from sqlalchemy.orm import joinedload
    from models.models import Subscription
    result = await session.execute(select(Subscription).where(Subscription.id == sub.id))
    refreshed = result.scalar_one()

    # Compare natively (both naive from SQLite or both aware from PG)
    assert refreshed.expires_at > original_expiry
