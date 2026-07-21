"""
Admin router — used by Telegram admin commands and (optionally) a web UI.
Protected by internal billing key.
"""
from __future__ import annotations

import os
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from api.dependencies import verify_internal_key
from billing.database import get_db
from billing.repositories.other_repos import PaymentRepository, PlanRepository
from billing.repositories.server_repo import VpnServerRepository
from billing.repositories.subscription_repo import SubscriptionRepository
from billing.repositories.user_repo import UserRepository
from billing.services.billing_service import BillingService
from integrations.amnezia.client import AmneziaClient
from models.models import VpnServerStatus

router = APIRouter(dependencies=[Depends(verify_internal_key)])
_svc = BillingService()


# ---- Users ----

@router.get("/users")
async def list_users(offset: int = 0, limit: int = 50, session=Depends(get_db)):
    repo = UserRepository(session)
    users = await repo.get_all(offset=offset, limit=limit)
    total = await repo.count()
    return {
        "total": total,
        "items": [
            {
                "id": u.id,
                "telegram_id": u.telegram_id,
                "username": u.username,
                "first_name": u.first_name,
                "is_banned": u.is_banned,
                "created_at": u.created_at.isoformat(),
            }
            for u in users
        ],
    }


# ---- Subscriptions ----

@router.get("/subscriptions")
async def list_subscriptions(offset: int = 0, limit: int = 50, session=Depends(get_db)):
    repo = SubscriptionRepository(session)
    subs = await repo.get_all(offset=offset, limit=limit)
    return {
        "items": [
            {
                "id": s.id,
                "user_id": s.user_id,
                "status": s.status.value,
                "expires_at": s.expires_at.isoformat() if s.expires_at else None,
                "plan": s.plan.name if s.plan else None,
            }
            for s in subs
        ]
    }


class ExtendRequest(BaseModel):
    days: int = 30


@router.post("/subscriptions/{sub_id}/extend")
async def extend_subscription(sub_id: int, req: ExtendRequest, session=Depends(get_db)):
    await _svc.admin_extend_subscription(session, sub_id, req.days)
    return {"ok": True}


@router.post("/subscriptions/{sub_id}/disable")
async def disable_subscription(sub_id: int, session=Depends(get_db)):
    await _svc.admin_disable_subscription(session, sub_id)
    return {"ok": True}


# ---- Payments ----

@router.get("/payments")
async def list_payments(offset: int = 0, limit: int = 50, session=Depends(get_db)):
    repo = PaymentRepository(session)
    payments = await repo.get_all(offset=offset, limit=limit)
    return {
        "items": [
            {
                "id": p.id,
                "user_id": p.user_id,
                "provider": p.provider.value,
                "amount": float(p.amount),
                "currency": p.currency,
                "status": p.status.value,
                "paid_at": p.paid_at.isoformat() if p.paid_at else None,
            }
            for p in payments
        ]
    }


# ---- Servers ----

@router.get("/servers")
async def list_servers(session=Depends(get_db)):
    repo = VpnServerRepository(session)
    servers = await repo.get_all()
    result = []
    for s in servers:
        load_info: dict[str, Any] = {}
        try:
            amnezia = AmneziaClient(base_url=s.base_url, api_key=s.api_key)
            info = await amnezia.get_server_info()
            load_info = {"cpu": info.cpu, "memory": info.memory, "uptime": info.uptime}
        except Exception:
            load_info = {"error": "unreachable"}
        result.append(
            {
                "id": s.id,
                "name": s.name,
                "region": s.region,
                "status": s.status.value,
                "weight": s.weight,
                "protocol": s.protocol,
                "current_clients": s.current_clients,
                "max_clients": s.max_clients,
                "load": load_info,
            }
        )
    return {"items": result}


class ServerStatusUpdate(BaseModel):
    status: str  # "active" | "disabled"


@router.patch("/servers/{server_id}")
async def update_server_status(
    server_id: int, req: ServerStatusUpdate, session=Depends(get_db)
):
    repo = VpnServerRepository(session)
    server = await repo.get_by_id(server_id)
    if not server:
        raise HTTPException(status_code=404, detail="Server not found")
    try:
        server.status = VpnServerStatus(req.status)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid status: {req.status}")
    return {"ok": True, "new_status": server.status.value}


class ServerCreateRequest(BaseModel):
    name: str
    base_url: str
    api_key: str
    region: Optional[str] = "EU"
    weight: int = 100
    max_clients: int = 200
    protocol: str = "amneziawg2"  # must match protocols enabled on that server


@router.post("/servers")
async def create_server(req: ServerCreateRequest, session=Depends(get_db)):
    """
    Add a new VPN server. Use this to add servers after the initial deploy —
    the seed script only runs once, so this is the normal way to grow the
    server pool later (bot command: /add_server).
    """
    repo = VpnServerRepository(session)
    server = await repo.create(
        name=req.name,
        base_url=req.base_url,
        api_key=req.api_key,
        region=req.region,
        weight=req.weight,
        max_clients=req.max_clients,
        protocol=req.protocol,
    )
    return {"ok": True, "id": server.id, "name": server.name, "protocol": server.protocol}


@router.delete("/servers/{server_id}")
async def delete_server(server_id: int, session=Depends(get_db)):
    """
    Remove a server that has no clients on it. Servers with existing clients
    should be disabled (PATCH status=disabled) instead of deleted, since
    vpn_clients/subscriptions reference server_id via foreign key.
    """
    repo = VpnServerRepository(session)
    server = await repo.get_by_id(server_id)
    if not server:
        raise HTTPException(status_code=404, detail="Server not found")
    if server.current_clients > 0:
        raise HTTPException(
            status_code=400,
            detail="Server has active clients — disable it instead of deleting",
        )
    await repo.delete(server_id)
    return {"ok": True}


# ---- Plan price ----

class PlanUpdate(BaseModel):
    price_stars: Optional[int] = None
    price_usdt: Optional[float] = None


@router.patch("/plans/{plan_id}")
async def update_plan(plan_id: int, req: PlanUpdate, session=Depends(get_db)):
    repo = PlanRepository(session)
    plan = await repo.get_by_id(plan_id)
    if not plan:
        raise HTTPException(status_code=404, detail="Plan not found")
    if req.price_stars is not None:
        plan.price_stars = req.price_stars
    if req.price_usdt is not None:
        plan.price_usdt = req.price_usdt
    return {"ok": True}
