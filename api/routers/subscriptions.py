from __future__ import annotations

import os
from typing import Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from api.dependencies import verify_internal_key
from billing.database import get_db
from billing.repositories.other_repos import PlanRepository
from billing.repositories.subscription_repo import SubscriptionRepository
from billing.repositories.user_repo import UserRepository

router = APIRouter(dependencies=[Depends(verify_internal_key)])

PUBLIC_BASE_URL = os.environ.get("PUBLIC_BASE_URL", "").rstrip("/")


class SubscriptionOut(BaseModel):
    id: int
    status: str
    expires_at: Optional[str]
    starts_at: Optional[str]
    config_url: Optional[str]
    connect_url: Optional[str]
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
    """Latest device/subscription for this user. Kept for backward-compat
    quick status checks — for the full list of devices use /devices."""
    user_repo = UserRepository(session)
    user = await user_repo.get_by_telegram_id(telegram_id)
    if not user:
        return None
    sub_repo = SubscriptionRepository(session)
    sub = await sub_repo.get_latest_for_user(user.id)
    if not sub:
        return None
    return _sub_out(sub)


@router.get("/devices", response_model=list[SubscriptionOut])
async def get_my_devices(telegram_id: int, session=Depends(get_db)):
    """Every device (subscription) this user has ever bought, newest first."""
    user_repo = UserRepository(session)
    user = await user_repo.get_by_telegram_id(telegram_id)
    if not user:
        return []
    sub_repo = SubscriptionRepository(session)
    subs = await sub_repo.get_all_for_user(user.id)
    return [_sub_out(s) for s in subs]


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
    vc = sub.vpn_client
    config_url = vc.config_url if vc else None
    connect_url = None
    if vc and vc.public_token and PUBLIC_BASE_URL:
        connect_url = f"{PUBLIC_BASE_URL}/connect/{vc.public_token}"
    plan = sub.plan
    return SubscriptionOut(
        id=sub.id,
        status=sub.status.value,
        expires_at=sub.expires_at.isoformat() if sub.expires_at else None,
        starts_at=sub.starts_at.isoformat() if sub.starts_at else None,
        config_url=config_url,
        connect_url=connect_url,
        plan_name=plan.name if plan else None,
        plan_price_stars=plan.price_stars if plan else None,
        plan_price_usdt=float(plan.price_usdt) if plan else None,
        plan_duration_days=plan.duration_days if plan else None,
    )
