"""
BillingService — core business logic.

This is the single source of truth for:
  - processing payments (idempotent)
  - creating / extending / disabling subscriptions
  - provisioning VPN access via amnezia-api
  - retrying failed provisioning
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from billing.database import AsyncSessionLocal
from billing.repositories.other_repos import (
    AuditRepository,
    OrderRepository,
    PaymentRepository,
    ProcessedEventRepository,
    VpnClientRepository,
)
from billing.repositories.server_repo import VpnServerRepository
from billing.repositories.subscription_repo import SubscriptionRepository
from billing.repositories.user_repo import UserRepository
from integrations.amnezia.client import AmneziaClient
from integrations.amnezia.errors import AmneziaError
from integrations.amnezia.schemas import CreateClientRequest
from models.models import (
    AuditAction,
    OrderStatus,
    PaymentProvider,
    Subscription,
    SubscriptionStatus,
    VpnClientStatus,
)

logger = logging.getLogger(__name__)


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _extended_expiry(current_expiry: Optional[datetime], duration: timedelta) -> datetime:
    now = datetime.now(timezone.utc)
    base = _as_utc(current_expiry) if current_expiry else now
    if base < now:
        base = now
    return base + duration


class BillingService:
    """
    All methods accept an AsyncSession and are designed to be called
    from FastAPI route handlers (session-per-request) or from the worker.
    """

    # -----------------------------------------------------------------
    # Payment processing
    # -----------------------------------------------------------------

    async def handle_payment(
        self,
        session: AsyncSession,
        *,
        telegram_id: int,
        username: Optional[str],
        first_name: Optional[str],
        last_name: Optional[str],
        provider: PaymentProvider,
        external_id: str,    # unique payment ID from provider
        amount: float,
        currency: str,
        plan_id: Optional[int] = None,
    ) -> Subscription:
        """
        Idempotent payment handler.
        - Creates user if not exists.
        - Creates order + payment if not already processed.
        - Marks payment as paid.
        - Triggers provisioning (or extension).
        Returns the resulting Subscription.
        """
        evt_repo = ProcessedEventRepository(session)
        event_key = f"{provider.value}:{external_id}"

        # --- Idempotency check ---
        if await evt_repo.exists(event_key):
            logger.info("Duplicate event %s ignored", event_key)
            sub_repo = SubscriptionRepository(session)
            user_repo = UserRepository(session)
            user = await user_repo.get_by_telegram_id(telegram_id)
            if user:
                sub = await sub_repo.get_latest_for_user(user.id)
                if sub:
                    return sub
            raise ValueError("Duplicate event but no subscription found — investigate")

        # --- Ensure user exists ---
        user_repo = UserRepository(session)
        user, _ = await user_repo.get_or_create(
            telegram_id=telegram_id,
            username=username,
            first_name=first_name,
            last_name=last_name,
        )

        # --- Resolve plan ---
        plan_repo = billing_plan_repo(session)
        plan = await plan_repo.get_by_id(plan_id) if plan_id else await plan_repo.get_active_plan()
        if not plan:
            raise ValueError("No active plan found")

        # --- Create order + payment ---
        order_repo = OrderRepository(session)
        order = await order_repo.create(user_id=user.id, plan_id=plan.id)

        pay_repo = PaymentRepository(session)
        payment = await pay_repo.create(
            user_id=user.id,
            order_id=order.id,
            provider=provider,
            external_id=external_id,
            amount=amount,
            currency=currency,
        )
        await pay_repo.mark_paid(payment)
        order.status = OrderStatus.completed

        # --- Mark event as processed (before provisioning to avoid retry confusion) ---
        await evt_repo.mark(event_key)

        audit = AuditRepository(session)
        await audit.log(
            AuditAction.payment_received,
            user_id=user.id,
            entity_type="payment",
            entity_id=payment.id,
            details=json.dumps({"provider": provider.value, "external_id": external_id}),
        )

        # --- Create or extend subscription ---
        sub = await self._create_or_extend_subscription(
            session,
            user_id=user.id,
            plan=plan,
        )

        await session.flush()

        # --- Provision VPN (may fail; worker will retry) ---
        await self._provision_subscription(session, sub)

        return sub

    # -----------------------------------------------------------------
    # Subscription lifecycle
    # -----------------------------------------------------------------

    async def _create_or_extend_subscription(
        self,
        session: AsyncSession,
        *,
        user_id: int,
        plan,
    ) -> Subscription:
        sub_repo = SubscriptionRepository(session)
        audit = AuditRepository(session)

        # Check for existing subscription (active, disabled, or error — can be extended)
        existing = await sub_repo.get_latest_for_user(user_id)

        now = datetime.now(timezone.utc)
        duration = timedelta(days=plan.duration_days)

        if existing and existing.status in (
            SubscriptionStatus.active,
            SubscriptionStatus.disabled,
            SubscriptionStatus.error,
            SubscriptionStatus.expired,
            SubscriptionStatus.pending_provisioning,
        ):
            # Extend
            existing.expires_at = _extended_expiry(existing.expires_at, duration)
            existing.last_extended_at = now
            if existing.status in (
                SubscriptionStatus.disabled,
                SubscriptionStatus.error,
                SubscriptionStatus.expired,
            ):
                existing.status = SubscriptionStatus.pending_provisioning
            await audit.log(
                AuditAction.subscription_renewed,
                user_id=user_id,
                entity_type="subscription",
                entity_id=existing.id,
            )
            return existing

        # Create new
        sub = await sub_repo.create(
            user_id=user_id,
            plan_id=plan.id,
            status=SubscriptionStatus.pending_provisioning,
            starts_at=now,
            expires_at=now + duration,
        )
        await audit.log(
            AuditAction.subscription_created,
            user_id=user_id,
            entity_type="subscription",
            entity_id=sub.id,
        )
        return sub

    async def _provision_subscription(
        self,
        session: AsyncSession,
        sub: Subscription,
    ) -> None:
        """
        Create or re-enable a VPN client for this subscription.
        On any error, set status=pending_provisioning so worker retries.
        """
        vc_repo = VpnClientRepository(session)
        server_repo = VpnServerRepository(session)
        audit = AuditRepository(session)
        sub_repo = SubscriptionRepository(session)

        # Already has an active VPN client? Just ensure it's enabled.
        existing_vc = await vc_repo.get_by_subscription(sub.id)
        if existing_vc and existing_vc.status != VpnClientStatus.deleted:
            server = await server_repo.get_by_id(existing_vc.server_id)
            if server:
                amnezia = AmneziaClient(base_url=server.base_url, api_key=server.api_key)
                try:
                    await amnezia.enable_client(
                        existing_vc.amnezia_client_id, protocol=existing_vc.protocol
                    )
                    existing_vc.status = VpnClientStatus.active
                    sub.status = SubscriptionStatus.active
                    sub.last_provisioned_at = datetime.now(timezone.utc)
                    await audit.log(
                        AuditAction.vpn_client_enabled,
                        entity_type="vpn_client",
                        entity_id=existing_vc.id,
                    )
                    return
                except AmneziaError as e:
                    logger.warning("Enable client failed: %s", e)
                    sub.status = SubscriptionStatus.pending_provisioning
                    return

        # Select a VPN server
        server = await server_repo.select_server()
        if not server:
            logger.error("No available VPN servers for provisioning sub %d", sub.id)
            sub.status = SubscriptionStatus.error
            await audit.log(
                AuditAction.provisioning_failed,
                user_id=sub.user_id,
                entity_type="subscription",
                entity_id=sub.id,
                details="No available servers",
            )
            return

        sub.server_id = server.id
        client_name = f"tg_{sub.user_id}_{sub.id}"
        amnezia = AmneziaClient(base_url=server.base_url, api_key=server.api_key)

        try:
            req = CreateClientRequest(
                clientName=client_name,
                protocol=server.protocol,
                expiresAt=None,  # We manage expiry ourselves
            )
            resp = await amnezia.create_client(req)
        except AmneziaError as e:
            logger.warning("Create client failed for sub %d: %s", sub.id, e)
            sub.status = SubscriptionStatus.pending_provisioning
            sub.retry_count = (sub.retry_count or 0) + 1
            await audit.log(
                AuditAction.provisioning_failed,
                user_id=sub.user_id,
                entity_type="subscription",
                entity_id=sub.id,
                details=str(e),
            )
            return

        # Persist VPN client record
        vc = await vc_repo.create(
            subscription_id=sub.id,
            server_id=server.id,
            amnezia_client_id=resp.client.id,
            client_name=client_name,
            config_url=resp.client.config,
            protocol=resp.client.protocol,
        )
        await server_repo.increment_clients(server.id)

        sub.status = SubscriptionStatus.active
        sub.last_provisioned_at = datetime.now(timezone.utc)
        await audit.log(
            AuditAction.vpn_client_created,
            user_id=sub.user_id,
            entity_type="vpn_client",
            entity_id=vc.id,
        )
        logger.info("Provisioned VPN client %s for sub %d", resp.client.id, sub.id)

    # -----------------------------------------------------------------
    # Expiry / disable
    # -----------------------------------------------------------------

    async def disable_expired_subscriptions(self) -> int:
        """Worker task: disable all expired active subscriptions."""
        count = 0
        async with AsyncSessionLocal() as session:
            sub_repo = SubscriptionRepository(session)
            vc_repo = VpnClientRepository(session)
            server_repo = VpnServerRepository(session)
            audit = AuditRepository(session)

            now = datetime.now(timezone.utc)
            expired = await sub_repo.get_expiring_before(now)

            for sub in expired:
                vc = await vc_repo.get_by_subscription(sub.id)
                if vc and vc.status == VpnClientStatus.active:
                    server = await server_repo.get_by_id(vc.server_id)
                    if server:
                        amnezia = AmneziaClient(
                            base_url=server.base_url, api_key=server.api_key
                        )
                        try:
                            await amnezia.disable_client(vc.amnezia_client_id, vc.protocol)
                            vc.status = VpnClientStatus.disabled
                            await server_repo.decrement_clients(server.id)
                        except AmneziaError as e:
                            logger.warning("Disable client %s failed: %s", vc.amnezia_client_id, e)

                sub.status = SubscriptionStatus.expired
                await audit.log(
                    AuditAction.subscription_expired,
                    user_id=sub.user_id,
                    entity_type="subscription",
                    entity_id=sub.id,
                )
                count += 1

            await session.commit()
        return count

    async def retry_pending_provisioning(self) -> int:
        """Worker task: retry provisioning for subscriptions stuck in pending_provisioning."""
        count = 0
        async with AsyncSessionLocal() as session:
            sub_repo = SubscriptionRepository(session)
            audit = AuditRepository(session)
            pending = await sub_repo.get_pending_provisioning()
            for sub in pending:
                if (sub.retry_count or 0) >= 5:
                    sub.status = SubscriptionStatus.error
                    continue
                await self._provision_subscription(session, sub)
                await audit.log(
                    AuditAction.provisioning_retried,
                    user_id=sub.user_id,
                    entity_type="subscription",
                    entity_id=sub.id,
                )
                count += 1
            await session.commit()
        return count

    # -----------------------------------------------------------------
    # Admin actions
    # -----------------------------------------------------------------

    async def admin_disable_subscription(self, session: AsyncSession, sub_id: int) -> None:
        sub_repo = SubscriptionRepository(session)
        vc_repo = VpnClientRepository(session)
        server_repo = VpnServerRepository(session)
        audit = AuditRepository(session)

        sub = await sub_repo.get_by_id(sub_id)
        if not sub:
            raise ValueError("Subscription not found")

        vc = await vc_repo.get_by_subscription(sub.id)
        if vc and vc.status == VpnClientStatus.active:
            server = await server_repo.get_by_id(vc.server_id)
            if server:
                amnezia = AmneziaClient(base_url=server.base_url, api_key=server.api_key)
                await amnezia.disable_client(vc.amnezia_client_id, vc.protocol)
                vc.status = VpnClientStatus.disabled
                await server_repo.decrement_clients(server.id)

        sub.status = SubscriptionStatus.disabled
        await audit.log(
            AuditAction.subscription_disabled,
            entity_type="subscription",
            entity_id=sub.id,
        )

    async def admin_extend_subscription(
        self, session: AsyncSession, sub_id: int, days: int
    ) -> None:
        sub_repo = SubscriptionRepository(session)
        audit = AuditRepository(session)

        sub = await sub_repo.get_by_id(sub_id)
        if not sub:
            raise ValueError("Subscription not found")

        sub.expires_at = _extended_expiry(sub.expires_at, timedelta(days=days))
        sub.last_extended_at = datetime.now(timezone.utc)

        if sub.status == SubscriptionStatus.expired:
            sub.status = SubscriptionStatus.pending_provisioning

        await audit.log(
            AuditAction.subscription_renewed,
            entity_type="subscription",
            entity_id=sub.id,
            details=json.dumps({"days": days}),
        )


def billing_plan_repo(session: AsyncSession):
    from billing.repositories.other_repos import PlanRepository
    return PlanRepository(session)
