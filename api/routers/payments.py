"""
Payments router.
Bot calls POST /api/v1/payments/stars or /api/v1/payments/usdt
after a successful Telegram payment event.
"""
from __future__ import annotations

import os
from typing import Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from api.dependencies import verify_internal_key
from billing.database import get_db
from billing.repositories.other_repos import VpnClientRepository
from billing.services.billing_service import BillingService
from models.models import PaymentProvider

router = APIRouter(dependencies=[Depends(verify_internal_key)])
_svc = BillingService()

PUBLIC_BASE_URL = os.environ.get("PUBLIC_BASE_URL", "").rstrip("/")


class StarsPaymentRequest(BaseModel):
    telegram_id: int
    username: Optional[str] = None
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    telegram_payment_charge_id: str   # unique ID from Telegram
    total_amount: int                 # in Stars (XTR)
    plan_id: Optional[int] = None
    mode: str = "new"                 # "new" | "renew"
    target_subscription_id: Optional[int] = None


class UsdtPaymentRequest(BaseModel):
    telegram_id: int
    username: Optional[str] = None
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    invoice_id: str                   # unique ID from crypto provider
    amount: float
    currency: str = "USDT"
    plan_id: Optional[int] = None
    mode: str = "new"                 # "new" | "renew"
    target_subscription_id: Optional[int] = None


class PaymentResponse(BaseModel):
    subscription_id: int
    status: str
    expires_at: Optional[str]
    config_url: Optional[str]
    connect_url: Optional[str]  # public one-tap "open in Amnezia" link


async def _payment_response(session, sub) -> PaymentResponse:
    vpn_client = await VpnClientRepository(session).get_by_subscription(sub.id)
    connect_url = None
    if vpn_client and vpn_client.public_token and PUBLIC_BASE_URL:
        connect_url = f"{PUBLIC_BASE_URL}/connect/{vpn_client.public_token}"
    return PaymentResponse(
        subscription_id=sub.id,
        status=sub.status.value,
        expires_at=sub.expires_at.isoformat() if sub.expires_at else None,
        config_url=vpn_client.config_url if vpn_client else None,
        connect_url=connect_url,
    )


@router.post("/stars", response_model=PaymentResponse)
async def handle_stars_payment(req: StarsPaymentRequest, session=Depends(get_db)):
    sub = await _svc.handle_payment(
        session,
        telegram_id=req.telegram_id,
        username=req.username,
        first_name=req.first_name,
        last_name=req.last_name,
        provider=PaymentProvider.stars,
        external_id=req.telegram_payment_charge_id,
        amount=req.total_amount,
        currency="XTR",
        plan_id=req.plan_id,
        mode=req.mode,
        target_subscription_id=req.target_subscription_id,
    )
    return await _payment_response(session, sub)


@router.post("/usdt", response_model=PaymentResponse)
async def handle_usdt_payment(req: UsdtPaymentRequest, session=Depends(get_db)):
    sub = await _svc.handle_payment(
        session,
        telegram_id=req.telegram_id,
        username=req.username,
        first_name=req.first_name,
        last_name=req.last_name,
        provider=PaymentProvider.usdt,
        external_id=req.invoice_id,
        amount=req.amount,
        currency=req.currency,
        plan_id=req.plan_id,
        mode=req.mode,
        target_subscription_id=req.target_subscription_id,
    )
    return await _payment_response(session, sub)
