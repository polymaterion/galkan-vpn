"""
Unit tests for BillingService.grant_trial() — the free 3-day trial period.
Mirrors the style/fixtures of test_billing_service.py.
"""
import pytest
from sqlalchemy import select

from billing.services.billing_service import BillingService
from billing.repositories.other_repos import AuditRepository, VpnClientRepository
from billing.repositories.subscription_repo import SubscriptionRepository
from billing.repositories.user_repo import UserRepository
from models.models import AuditAction, Plan, SubscriptionStatus, User, VpnServer, VpnServerStatus


async def _seed_trial_plan(session, duration_days: int = 3) -> Plan:
    plan = Plan(
        name="Free trial",
        duration_days=duration_days,
        price_stars=0,
        price_usdt=0,
        is_active=True,
        is_trial=True,
    )
    session.add(plan)
    await session.flush()
    return plan


async def _seed_paid_plan(session) -> Plan:
    plan = Plan(
        name="Paid plan",
        duration_days=30,
        price_stars=100,
        price_usdt=3.0,
        is_active=True,
        is_trial=False,
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
# Happy path: brand-new user gets a provisioned 3-day subscription
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_grant_trial_creates_active_subscription(session, mock_amnezia_client):
    plan = await _seed_trial_plan(session)
    await _seed_server(session)
    await session.commit()

    svc = BillingService()
    sub = await svc.grant_trial(
        session, telegram_id=5001, username="newbie", first_name="New", last_name=None
    )
    await session.commit()

    from sqlalchemy.orm import joinedload
    result = await session.execute(
        select(type(sub)).options(joinedload(type(sub).vpn_client)).where(type(sub).id == sub.id)
    )
    sub = result.unique().scalar_one()

    assert sub.plan_id == plan.id
    assert sub.status == SubscriptionStatus.active
    assert sub.vpn_client is not None
    mock_amnezia_client.create_client.assert_called_once()

    user_repo = UserRepository(session)
    user = await user_repo.get_by_telegram_id(5001)
    assert user.trial_used is True


@pytest.mark.asyncio
async def test_grant_trial_logs_audit_event(session, mock_amnezia_client):
    await _seed_trial_plan(session)
    await _seed_server(session)
    await session.commit()

    svc = BillingService()
    sub = await svc.grant_trial(session, telegram_id=5002, username=None, first_name="Au", last_name=None)
    await session.commit()

    audit = AuditRepository(session)
    from models.models import AuditLog
    result = await session.execute(
        select(AuditLog).where(
            AuditLog.action == AuditAction.trial_granted,
            AuditLog.entity_id == sub.id,
        )
    )
    entries = result.scalars().all()
    assert len(entries) == 1


# ---------------------------------------------------------------------------
# One trial per user, enforced by User.trial_used
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_grant_trial_rejects_second_attempt(session, mock_amnezia_client):
    await _seed_trial_plan(session)
    await _seed_server(session)
    await session.commit()

    svc = BillingService()
    await svc.grant_trial(session, telegram_id=5003, username=None, first_name="Once", last_name=None)
    await session.commit()

    with pytest.raises(ValueError, match="already used"):
        await svc.grant_trial(session, telegram_id=5003, username=None, first_name="Once", last_name=None)

    # Only one client should ever have been created for this user.
    assert mock_amnezia_client.create_client.call_count == 1


@pytest.mark.asyncio
async def test_grant_trial_rejects_for_existing_user_who_already_used_it(session, mock_amnezia_client):
    """Covers the /start=trial deep-link path for pre-existing users: a
    user who already claimed the trial (e.g. via the auto-offered button)
    must not be able to claim a second one through the deep link."""
    await _seed_trial_plan(session)
    await _seed_server(session)
    await session.commit()

    user = User(telegram_id=5004, username="olduser", trial_used=True)
    session.add(user)
    await session.commit()

    svc = BillingService()
    with pytest.raises(ValueError):
        await svc.grant_trial(session, telegram_id=5004, username="olduser", first_name=None, last_name=None)

    assert mock_amnezia_client.create_client.call_count == 0


# ---------------------------------------------------------------------------
# No trial plan configured
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_grant_trial_without_trial_plan_raises(session, mock_amnezia_client):
    # Only a paid plan exists, no is_trial=True row.
    await _seed_paid_plan(session)
    await _seed_server(session)
    await session.commit()

    svc = BillingService()
    with pytest.raises(ValueError, match="No trial plan"):
        await svc.grant_trial(session, telegram_id=5005, username=None, first_name=None, last_name=None)


# ---------------------------------------------------------------------------
# Trial plan must never be returned as the purchasable plan
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_active_plan_excludes_trial_plan(session):
    from billing.repositories.other_repos import PlanRepository

    trial = await _seed_trial_plan(session)
    paid = await _seed_paid_plan(session)
    await session.commit()

    plan_repo = PlanRepository(session)
    active = await plan_repo.get_active_plan()
    assert active is not None
    assert active.id == paid.id
    assert active.id != trial.id

    trial_plan = await plan_repo.get_trial_plan()
    assert trial_plan.id == trial.id


# ---------------------------------------------------------------------------
# has_used_trial helper
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_has_used_trial_reflects_state(session, mock_amnezia_client):
    await _seed_trial_plan(session)
    await _seed_server(session)
    await session.commit()

    svc = BillingService()
    assert await svc.has_used_trial(session, 5006) is False

    await svc.grant_trial(session, telegram_id=5006, username=None, first_name=None, last_name=None)
    await session.commit()

    assert await svc.has_used_trial(session, 5006) is True


# ---------------------------------------------------------------------------
# Trial subscription behaves like any other for the "my devices" listing
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_trial_subscription_appears_in_user_devices(session, mock_amnezia_client):
    await _seed_trial_plan(session)
    await _seed_server(session)
    await session.commit()

    svc = BillingService()
    sub = await svc.grant_trial(session, telegram_id=5007, username=None, first_name=None, last_name=None)
    await session.commit()

    user_repo = UserRepository(session)
    user = await user_repo.get_by_telegram_id(5007)
    sub_repo = SubscriptionRepository(session)
    devices = await sub_repo.get_all_for_user(user.id)

    assert len(devices) == 1
    assert devices[0].id == sub.id
