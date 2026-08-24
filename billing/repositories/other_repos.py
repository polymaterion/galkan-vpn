from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models.models import (
    AuditAction,
    AuditLog,
    Order,
    OrderStatus,
    Payment,
    PaymentProvider,
    PaymentStatus,
    Plan,
    ProcessedEvent,
    VpnClient,
    VpnClientStatus,
)


class PlanRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_active_plan(self) -> Optional[Plan]:
        """The purchasable plan shown to customers. Explicitly excludes
        is_trial=True — the trial plan must never appear as something
        buyable, it's only ever assigned via BillingService.grant_trial()."""
        result = await self.session.execute(
            select(Plan)
            .where(Plan.is_active == True, Plan.is_trial == False)
            .order_by(Plan.id)
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def get_trial_plan(self) -> Optional[Plan]:
        result = await self.session.execute(
            select(Plan).where(Plan.is_trial == True).order_by(Plan.id).limit(1)
        )
        return result.scalar_one_or_none()

    async def get_by_id(self, plan_id: int) -> Optional[Plan]:
        result = await self.session.execute(select(Plan).where(Plan.id == plan_id))
        return result.scalar_one_or_none()

    async def get_all(self) -> list[Plan]:
        result = await self.session.execute(select(Plan))
        return list(result.scalars().all())


class OrderRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(self, user_id: int, plan_id: int) -> Order:
        order = Order(user_id=user_id, plan_id=plan_id, status=OrderStatus.pending)
        self.session.add(order)
        await self.session.flush()
        return order

    async def get_by_id(self, order_id: int) -> Optional[Order]:
        result = await self.session.execute(select(Order).where(Order.id == order_id))
        return result.scalar_one_or_none()

    async def get_all(self, offset: int = 0, limit: int = 50) -> list[Order]:
        result = await self.session.execute(
            select(Order).offset(offset).limit(limit).order_by(Order.id.desc())
        )
        return list(result.scalars().all())


class PaymentRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_by_external_id(
        self, provider: PaymentProvider, external_id: str
    ) -> Optional[Payment]:
        result = await self.session.execute(
            select(Payment).where(
                Payment.provider == provider,
                Payment.external_id == external_id,
            )
        )
        return result.scalar_one_or_none()

    async def create(
        self,
        user_id: int,
        order_id: int,
        provider: PaymentProvider,
        external_id: str,
        amount: float,
        currency: str,
    ) -> Payment:
        payment = Payment(
            user_id=user_id,
            order_id=order_id,
            provider=provider,
            external_id=external_id,
            status=PaymentStatus.pending,
            amount=amount,
            currency=currency,
        )
        self.session.add(payment)
        await self.session.flush()
        return payment

    async def mark_paid(self, payment: Payment) -> None:
        payment.status = PaymentStatus.paid
        payment.paid_at = datetime.now(timezone.utc)

    async def link_subscription(self, payment: Payment, subscription_id: int) -> None:
        payment.subscription_id = subscription_id
        await self.session.flush()

    async def get_all(self, offset: int = 0, limit: int = 50) -> list[Payment]:
        result = await self.session.execute(
            select(Payment).offset(offset).limit(limit).order_by(Payment.id.desc())
        )
        return list(result.scalars().all())


class VpnClientRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(
        self,
        subscription_id: int,
        server_id: int,
        amnezia_client_id: str,
        client_name: str,
        config_url: Optional[str],
        protocol: str = "amneziawg2",
    ) -> VpnClient:
        import secrets
        vc = VpnClient(
            subscription_id=subscription_id,
            server_id=server_id,
            amnezia_client_id=amnezia_client_id,
            client_name=client_name,
            config_url=config_url,
            status=VpnClientStatus.active,
            protocol=protocol,
            public_token=secrets.token_hex(24),  # 48 hex chars, unguessable
        )
        self.session.add(vc)
        await self.session.flush()
        return vc

    async def get_by_subscription(self, subscription_id: int) -> Optional[VpnClient]:
        result = await self.session.execute(
            select(VpnClient).where(VpnClient.subscription_id == subscription_id)
        )
        return result.scalar_one_or_none()

    async def get_by_public_token(self, token: str) -> Optional[VpnClient]:
        result = await self.session.execute(
            select(VpnClient).where(VpnClient.public_token == token)
        )
        return result.scalar_one_or_none()


class ProcessedEventRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def exists(self, event_id: str) -> bool:
        result = await self.session.execute(
            select(ProcessedEvent).where(ProcessedEvent.event_id == event_id)
        )
        return result.scalar_one_or_none() is not None

    async def mark(self, event_id: str) -> None:
        evt = ProcessedEvent(event_id=event_id)
        self.session.add(evt)
        await self.session.flush()


class AuditRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def log(
        self,
        action: AuditAction,
        user_id: Optional[int] = None,
        entity_type: Optional[str] = None,
        entity_id: Optional[int] = None,
        details: Optional[str] = None,
    ) -> None:
        log = AuditLog(
            action=action,
            user_id=user_id,
            entity_type=entity_type,
            entity_id=entity_id,
            details=details,
        )
        self.session.add(log)
        await self.session.flush()
