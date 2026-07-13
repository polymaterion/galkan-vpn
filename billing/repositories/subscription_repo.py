from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import joinedload
from sqlalchemy.ext.asyncio import AsyncSession

from models.models import Subscription, SubscriptionStatus, VpnClient


class SubscriptionRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_by_id(self, sub_id: int) -> Optional[Subscription]:
        result = await self.session.execute(
            select(Subscription)
            .options(joinedload(Subscription.vpn_client), joinedload(Subscription.plan))
            .where(Subscription.id == sub_id)
        )
        return result.unique().scalar_one_or_none()

    async def get_active_for_user(self, user_id: int) -> Optional[Subscription]:
        result = await self.session.execute(
            select(Subscription)
            .options(joinedload(Subscription.vpn_client), joinedload(Subscription.plan))
            .where(
                Subscription.user_id == user_id,
                Subscription.status == SubscriptionStatus.active,
            )
        )
        return result.unique().scalar_one_or_none()

    async def get_latest_for_user(self, user_id: int) -> Optional[Subscription]:
        result = await self.session.execute(
            select(Subscription)
            .options(joinedload(Subscription.vpn_client), joinedload(Subscription.plan))
            .where(Subscription.user_id == user_id)
            .order_by(Subscription.id.desc())
        )
        return result.unique().scalars().first()

    async def get_expiring_before(self, before: datetime) -> list[Subscription]:
        """Fetch active subscriptions that expire before `before`."""
        result = await self.session.execute(
            select(Subscription)
            .options(joinedload(Subscription.vpn_client))
            .where(
                Subscription.status == SubscriptionStatus.active,
                Subscription.expires_at <= before,
            )
        )
        return list(result.unique().scalars().all())

    async def get_pending_provisioning(self) -> list[Subscription]:
        result = await self.session.execute(
            select(Subscription)
            .options(joinedload(Subscription.vpn_client))
            .where(Subscription.status == SubscriptionStatus.pending_provisioning)
        )
        return list(result.unique().scalars().all())

    async def create(self, **kwargs) -> Subscription:
        sub = Subscription(**kwargs)
        self.session.add(sub)
        await self.session.flush()
        return sub

    async def get_all(
        self, offset: int = 0, limit: int = 50
    ) -> list[Subscription]:
        result = await self.session.execute(
            select(Subscription)
            .options(joinedload(Subscription.user), joinedload(Subscription.plan))
            .offset(offset)
            .limit(limit)
            .order_by(Subscription.id.desc())
        )
        return list(result.unique().scalars().all())
