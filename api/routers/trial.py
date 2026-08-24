"""
Free trial period. Called by the bot:
  - automatically on a brand-new user's first /start
  - via the /start=trial deep link, for users who already exist but
    haven't used their trial yet (tap-to-confirm screen)
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from api.dependencies import verify_internal_key
from billing.database import get_db
from billing.repositories.user_repo import UserRepository
from billing.services.billing_service import BillingService

router = APIRouter(dependencies=[Depends(verify_internal_key)])
_svc = BillingService()


class GrantTrialRequest(BaseModel):
    telegram_id: int
    username: Optional[str] = None
    first_name: Optional[str] = None
    last_name: Optional[str] = None


class GrantTrialResponse(BaseModel):
    subscription_id: int
    status: str
    expires_at: Optional[str]


@router.post("/grant", response_model=GrantTrialResponse)
async def grant_trial(req: GrantTrialRequest, session=Depends(get_db)):
    # Raises ValueError ("Trial already used" / "No trial plan configured"),
    # mapped to HTTP 400 by the app-level exception handler in api/main.py.
    sub = await _svc.grant_trial(
        session,
        telegram_id=req.telegram_id,
        username=req.username,
        first_name=req.first_name,
        last_name=req.last_name,
    )
    return GrantTrialResponse(
        subscription_id=sub.id,
        status=sub.status.value,
        expires_at=sub.expires_at.isoformat() if sub.expires_at else None,
    )


@router.get("/eligible", response_model=bool)
async def trial_eligible(telegram_id: int, session=Depends(get_db)):
    """Whether this user can still claim the trial (hasn't used it, and a
    trial plan actually exists). The bot uses this to decide whether to
    show the trial button/deep-link confirmation at all."""
    from billing.repositories.other_repos import PlanRepository

    user_repo = UserRepository(session)
    user = await user_repo.get_by_telegram_id(telegram_id)
    if user and user.trial_used:
        return False
    plan_repo = PlanRepository(session)
    plan = await plan_repo.get_trial_plan()
    return plan is not None
