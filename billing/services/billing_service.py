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

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from billing.database import AsyncSessionLocal
from billing.redis_lock import redis_lock, LockTimeoutError
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

    async def _find_subscription_for_duplicate_event(
        self,
        session: AsyncSession,
        *,
        provider: PaymentProvider,
        external_id: str,
        telegram_id: int,
    ) -> Optional[Subscription]:
        """
        Look up the subscription that a duplicate payment event should
        resolve to. Shared by both duplicate-detection paths in
        handle_payment(): the cheap exists()-based shortcut and the
        IntegrityError handler that catches a genuine concurrent race.
        """
        pay_repo = PaymentRepository(session)
        payment = await pay_repo.get_by_external_id(provider, external_id)
        if payment and payment.subscription_id:
            sub_repo = SubscriptionRepository(session)
            sub = await sub_repo.get_by_id(payment.subscription_id)
            if sub:
                return sub
        # Fallback heuristic (shouldn't normally be reached)
        user_repo = UserRepository(session)
        user = await user_repo.get_by_telegram_id(telegram_id)
        if user:
            sub_repo = SubscriptionRepository(session)
            sub = await sub_repo.get_latest_for_user(user.id)
            if sub:
                return sub
        return None

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
        mode: str = "new",   # "new" = always provision a brand-new device;
                             # "renew" = extend one specific existing device
        target_subscription_id: Optional[int] = None,  # required if mode="renew"
    ) -> Subscription:
        """
        Idempotent payment handler.
        - Creates user if not exists.
        - Creates order + payment if not already processed.
        - Marks payment as paid.
        - mode="new" (default): ALWAYS provisions a brand-new VPN device/subscription.
          One payment = one device, hard rule — even if the user already has other
          active devices on the same Telegram account, this never extends them.
        - mode="renew": extends the expiry of one specific existing subscription
          (target_subscription_id), which must belong to this user. Use this for
          "renew my existing device" rather than "buy me a new one".
        Returns the resulting Subscription.
        """
        evt_repo = ProcessedEventRepository(session)
        event_key = f"{provider.value}:{external_id}"

        # --- Idempotency check (fast path) ---
        # This exists() check is a TOCTOU race by itself — two near-simultaneous
        # retries of the same webhook can both see False here before either one
        # commits. It's kept only as a cheap shortcut to skip the work below on
        # the common case (a real retry, arriving after the first one already
        # completed). The actual guarantee against double-processing is the DB
        # unique constraint on ProcessedEvent.event_id / Payment(provider,
        # external_id), enforced below via the IntegrityError handler.
        if await evt_repo.exists(event_key):
            logger.info("Duplicate event %s ignored", event_key)
            existing = await self._find_subscription_for_duplicate_event(
                session, provider=provider, external_id=external_id, telegram_id=telegram_id
            )
            if existing:
                return existing
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

        # --- Validate renew target BEFORE recording the payment ---
        sub_repo = SubscriptionRepository(session)
        target_sub: Optional[Subscription] = None
        if mode == "renew":
            if not target_subscription_id:
                raise ValueError("target_subscription_id is required when mode='renew'")
            target_sub = await sub_repo.get_by_id(target_subscription_id)
            if not target_sub or target_sub.user_id != user.id:
                raise ValueError("Subscription to renew not found or does not belong to this user")

        # --- Create order + payment + idempotency marker, atomically ---
        # These three inserts are wrapped in one SAVEPOINT so a concurrent
        # duplicate (another retry of the same webhook, racing past the
        # exists() shortcut above) is caught by the DB unique constraints
        # (ProcessedEvent.event_id, Payment(provider, external_id)) instead
        # of silently double-provisioning. On conflict we roll back just this
        # savepoint and fall through to the same "return the existing
        # subscription" path used by the fast-path duplicate check.
        order_repo = OrderRepository(session)
        pay_repo = PaymentRepository(session)
        try:
            async with session.begin_nested():
                order = await order_repo.create(user_id=user.id, plan_id=plan.id)
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
                await evt_repo.mark(event_key)
        except IntegrityError:
            logger.info("Concurrent duplicate event %s caught at insert time", event_key)
            existing = await self._find_subscription_for_duplicate_event(
                session, provider=provider, external_id=external_id, telegram_id=telegram_id
            )
            if existing:
                return existing
            raise ValueError("Duplicate event (race) but no subscription found — investigate")

        audit = AuditRepository(session)
        await audit.log(
            AuditAction.payment_received,
            user_id=user.id,
            entity_type="payment",
            entity_id=payment.id,
            details=json.dumps({"provider": provider.value, "external_id": external_id, "mode": mode}),
        )

        # --- Create a brand-new device, or renew one specific existing device ---
        if mode == "renew":
            sub = await self._renew_subscription(session, target_sub, plan)
        else:
            sub = await self._create_new_subscription(session, user_id=user.id, plan=plan)

        await pay_repo.link_subscription(payment, sub.id)
        await session.flush()

        # --- Provision VPN (may fail; worker will retry) ---
        await self._provision_subscription(session, sub)

        return sub

    # -----------------------------------------------------------------
    # Trial period
    # -----------------------------------------------------------------

    async def grant_trial(
        self,
        session: AsyncSession,
        *,
        telegram_id: int,
        username: Optional[str] = None,
        first_name: Optional[str] = None,
        last_name: Optional[str] = None,
    ) -> Subscription:
        """
        Grants the one-time free trial subscription to a Telegram user.
        Used both for brand-new users (auto-granted on their first /start)
        and for pre-existing users going through the /start=trial deep
        link. Idempotent per-user via User.trial_used — a second call
        raises instead of silently handing out a second trial.

        Unlike handle_payment(), there's no payment/order here: this is a
        straight subscription grant, reusing the same
        create-then-provision path so the resulting device behaves
        identically to a paid one (shows up in "my devices", expires and
        gets disabled by the scheduler like any other subscription, etc).
        """
        user_repo = UserRepository(session)
        user, _ = await user_repo.get_or_create(
            telegram_id=telegram_id,
            username=username,
            first_name=first_name,
            last_name=last_name,
        )

        if user.trial_used:
            raise ValueError("Trial already used")

        plan_repo = billing_plan_repo(session)
        plan = await plan_repo.get_trial_plan()
        if not plan:
            raise ValueError("No trial plan configured")

        user.trial_used = True

        sub = await self._create_new_subscription(session, user_id=user.id, plan=plan)
        await session.flush()

        audit = AuditRepository(session)
        await audit.log(
            AuditAction.trial_granted,
            user_id=user.id,
            entity_type="subscription",
            entity_id=sub.id,
        )

        await self._provision_subscription(session, sub)
        return sub

    async def has_used_trial(self, session: AsyncSession, telegram_id: int) -> bool:
        user_repo = UserRepository(session)
        user = await user_repo.get_by_telegram_id(telegram_id)
        return bool(user and user.trial_used)

    # -----------------------------------------------------------------
    # Subscription lifecycle
    # -----------------------------------------------------------------

    async def _create_new_subscription(
        self,
        session: AsyncSession,
        *,
        user_id: int,
        plan,
    ) -> Subscription:
        """Always creates a brand-new subscription — i.e. a new device slot.
        Never looks at or touches any existing subscription for this user."""
        sub_repo = SubscriptionRepository(session)
        audit = AuditRepository(session)

        now = datetime.now(timezone.utc)
        duration = timedelta(days=plan.duration_days)

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

    async def _renew_subscription(
        self,
        session: AsyncSession,
        existing: Subscription,
        plan,
    ) -> Subscription:
        """Extends one specific, already-identified subscription. Same device, same key."""
        audit = AuditRepository(session)

        now = datetime.now(timezone.utc)
        duration = timedelta(days=plan.duration_days)

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
            user_id=existing.user_id,
            entity_type="subscription",
            entity_id=existing.id,
        )
        return existing

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
                    async with redis_lock(f"vpn-server:{server.id}"):
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
                except (AmneziaError, LockTimeoutError) as e:
                    logger.warning("Enable client failed: %s", e)
                    sub.status = SubscriptionStatus.pending_provisioning
                    # Must increment retry_count here too, or a subscription
                    # stuck on this branch never reaches the >=5 threshold in
                    # retry_pending_provisioning() and retries forever instead
                    # of escalating to `error`.
                    sub.retry_count = (sub.retry_count or 0) + 1
                    await audit.log(
                        AuditAction.provisioning_failed,
                        user_id=sub.user_id,
                        entity_type="subscription",
                        entity_id=sub.id,
                        details=str(e),
                    )
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
            async with redis_lock(f"vpn-server:{server.id}"):
                resp = await amnezia.create_client(req)
        except (AmneziaError, LockTimeoutError) as e:
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

        # Persist VPN client record. If a row for this subscription already
        # exists (e.g. marked `deleted` by a prior failed reissue attempt —
        # see admin_reissue_device), update it in place rather than
        # inserting a second row: subscription_id is unique, so a blind
        # create() here would raise IntegrityError against that stale row.
        if existing_vc:
            existing_vc.server_id = server.id
            existing_vc.amnezia_client_id = resp.client.id
            existing_vc.client_name = client_name
            existing_vc.config_url = resp.client.config
            existing_vc.protocol = resp.client.protocol
            existing_vc.status = VpnClientStatus.active
            vc = existing_vc
        else:
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
                            async with redis_lock(f"vpn-server:{server.id}"):
                                await amnezia.disable_client(vc.amnezia_client_id, vc.protocol)
                            vc.status = VpnClientStatus.disabled
                            await server_repo.decrement_clients(server.id)
                        except (AmneziaError, LockTimeoutError) as e:
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
                async with redis_lock(f"vpn-server:{server.id}"):
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

    async def admin_reissue_device(self, session: AsyncSession, sub_id: int) -> str:
        """
        (Re-)provision a device's VPN client, covering two distinct failure
        modes with one command:

        1. A VpnClient row exists but is broken — e.g. amnezia-api returned
           a config that was never applied to the VPN server's WireGuard
           interface (see billing/redis_lock.py for why that could happen).
           We best-effort delete the old client on its VPN server (it may
           already be gone there, which is fine — that's exactly the broken
           state this command exists to fix), then update the row in place
           (subscription_id is unique, so we never insert a second row for
           the same subscription).

        2. No VpnClient row exists at all — provisioning failed before a
           client was ever created (e.g. no VPN server was configured yet
           at purchase time, which leaves the Subscription in `error` status
           with nothing under it). In this case we create a fresh VpnClient
           row via the repository instead of trying to update a row that
           was never there.

        Returns the new config_url.
        """
        sub_repo = SubscriptionRepository(session)
        vc_repo = VpnClientRepository(session)
        server_repo = VpnServerRepository(session)
        audit = AuditRepository(session)

        sub = await sub_repo.get_by_id(sub_id)
        if not sub:
            raise ValueError("Subscription not found")

        vc = await vc_repo.get_by_subscription(sub.id)

        old_server = await server_repo.get_by_id(vc.server_id) if vc else None
        if vc and old_server:
            amnezia = AmneziaClient(base_url=old_server.base_url, api_key=old_server.api_key)
            try:
                async with redis_lock(f"vpn-server:{old_server.id}"):
                    await amnezia.delete_client(vc.amnezia_client_id, vc.protocol)
            except (AmneziaError, LockTimeoutError) as e:
                # Expected in the exact scenario this command fixes: the
                # server never had this peer in the first place.
                logger.info(
                    "Best-effort delete of old client %s failed (continuing): %s",
                    vc.amnezia_client_id,
                    e,
                )
            # The old client is being removed from old_server here,
            # unconditionally, regardless of what happens with the new
            # server below (including create_client failing and this whole
            # function re-raising). Decrementing now — rather than later,
            # only on the overall success path — keeps current_clients
            # accurate even when reissue fails partway through: otherwise
            # old_server's count stays permanently inflated by one for a
            # client that no longer exists there.
            await server_repo.decrement_clients(old_server.id)

        server = await server_repo.select_server()
        if not server:
            raise ValueError("No available VPN servers to provision onto")

        client_name = f"tg_{sub.user_id}_{sub.id}"
        amnezia = AmneziaClient(base_url=server.base_url, api_key=server.api_key)
        req = CreateClientRequest(clientName=client_name, protocol=server.protocol, expiresAt=None)
        try:
            async with redis_lock(f"vpn-server:{server.id}"):
                resp = await amnezia.create_client(req)
        except (AmneziaError, LockTimeoutError) as e:
            logger.error("Reissue failed to create client on server %d: %s", server.id, e)
            sub.status = SubscriptionStatus.pending_provisioning
            sub.retry_count = (sub.retry_count or 0) + 1
            if vc:
                # The old client was already best-effort deleted from
                # old_server above (and its count decremented) — mark this
                # row deleted so the next retry cycle's _provision_subscription
                # correctly treats it as "no client exists, create fresh"
                # (its `status != deleted` check gates the enable_client
                # branch) instead of endlessly retrying enable_client against
                # a client that no longer exists on any server.
                vc.status = VpnClientStatus.deleted
            await audit.log(
                AuditAction.provisioning_failed,
                user_id=sub.user_id,
                entity_type="subscription",
                entity_id=sub.id,
                details=str(e),
            )
            # Re-raise so the API layer returns 503 instead of a bare 200
            # with no config_url — the caller (admin, via the bot) needs to
            # know this attempt didn't produce a usable device.
            raise

        # old_server's count was already decremented right after the
        # best-effort delete above (unconditionally, regardless of which
        # server gets selected next), so this increment is no longer paired
        # with a matching decrement at the same point in time and needs no
        # "only if the server changed" special-casing.
        await server_repo.increment_clients(server.id)

        if vc:
            vc.server_id = server.id
            vc.amnezia_client_id = resp.client.id
            vc.client_name = client_name
            vc.config_url = resp.client.config
            vc.protocol = resp.client.protocol
            vc.status = VpnClientStatus.active
            vc_id = vc.id
        else:
            new_vc = await vc_repo.create(
                subscription_id=sub.id,
                server_id=server.id,
                amnezia_client_id=resp.client.id,
                client_name=client_name,
                config_url=resp.client.config,
                protocol=resp.client.protocol,
            )
            vc_id = new_vc.id

        sub.status = SubscriptionStatus.active
        sub.server_id = server.id
        sub.last_provisioned_at = datetime.now(timezone.utc)

        await audit.log(
            AuditAction.vpn_client_created,
            entity_type="vpn_client",
            entity_id=vc_id,
            details="Provisioned via admin command" if not vc else "Reissued via admin command",
        )

        return resp.client.config


def billing_plan_repo(session: AsyncSession):
    from billing.repositories.other_repos import PlanRepository
    return PlanRepository(session)
