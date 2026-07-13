from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from api.dependencies import verify_internal_key
from billing.database import get_db
from billing.repositories.other_repos import PlanRepository
from billing.repositories.subscription_repo import SubscriptionRepository
from billing.repositories.user_repo import UserRepository

router = APIRouter(dependencies=[Depends(verify_internal_key)])


class SubscriptionOut(BaseModel):
    id: int
    status: str
    expires_at: Optional[str]
    starts_at: Optional[str]
    config_url: Optional[str]
    plan_name: Optional[str]
    plan_price_stars: Optional[int]
    plan_price_usdt: Optional[float]
    plan_duration_days: Optional[int]


class PlanOut(BaseModel):
    id: int
    name: str
    description: Optional[str]
    duration_days: int
    price_stars: int
    price_usdt: float


@router.get("/my", response_model=Optional[SubscriptionOut])
async def get_my_subscription(telegram_id: int, session=Depends(get_db)):
    user_repo = UserRepository(session)
    user = await user_repo.get_by_telegram_id(telegram_id)
    if not user:
        return None
    sub_repo = SubscriptionRepository(session)
    sub = await sub_repo.get_latest_for_user(user.id)
    if not sub:
        return None
    return _sub_out(sub)


@router.get("/plan", response_model=Optional[PlanOut])
async def get_plan(session=Depends(get_db)):
    plan_repo = PlanRepository(session)
    plan = await plan_repo.get_active_plan()
    if not plan:
        return None
    return PlanOut(
        id=plan.id,
        name=plan.name,
        description=plan.description,
        duration_days=plan.duration_days,
        price_stars=plan.price_stars,
        price_usdt=float(plan.price_usdt),
    )


def _sub_out(sub) -> SubscriptionOut:
    config_url = sub.vpn_client.config_url if sub.vpn_client else None
    plan = sub.plan
    return SubscriptionOut(
        id=sub.id,
        status=sub.status.value,
        expires_at=sub.expires_at.isoformat() if sub.expires_at else None,
        starts_at=sub.starts_at.isoformat() if sub.starts_at else None,
        config_url=config_url,
        plan_name=plan.name if plan else None,
        plan_price_stars=plan.price_stars if plan else None,
        plan_price_usdt=float(plan.price_usdt) if plan else None,
        plan_duration_days=plan.duration_days if plan else None,
    )
