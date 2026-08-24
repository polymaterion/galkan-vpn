"""
HTTP client for the Billing Service REST API.
The bot uses this to interact with billing without knowing any DB or VPN details.
"""
from __future__ import annotations

import logging
from typing import Any, Optional

import httpx

from bot.config import settings

logger = logging.getLogger(__name__)


class BillingClient:
    def __init__(self):
        self._base = settings.BILLING_BASE_URL.rstrip("/")
        self._headers = {
            "X-Billing-Key": settings.BILLING_SECRET_KEY,
            "Content-Type": "application/json",
        }

    def _client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            base_url=self._base,
            headers=self._headers,
            timeout=30.0,
        )

    async def get_plan(self) -> Optional[dict]:
        async with self._client() as c:
            resp = await c.get("/api/v1/subscriptions/plan")
            resp.raise_for_status()
            return resp.json()

    async def get_subscription(self, telegram_id: int) -> Optional[dict]:
        async with self._client() as c:
            resp = await c.get("/api/v1/subscriptions/my", params={"telegram_id": telegram_id})
            resp.raise_for_status()
            return resp.json()

    async def get_devices(self, telegram_id: int) -> list[dict]:
        """All devices (subscriptions) this user has ever bought, newest first."""
        async with self._client() as c:
            resp = await c.get("/api/v1/subscriptions/devices", params={"telegram_id": telegram_id})
            resp.raise_for_status()
            return resp.json()

    async def get_user_language(self, telegram_id: int) -> str:
        async with self._client() as c:
            resp = await c.get("/api/v1/users/me", params={"telegram_id": telegram_id})
            resp.raise_for_status()
            data = resp.json()
            return data.get("language") or ""

    async def set_user_language(self, telegram_id: int, language: str) -> dict:
        async with self._client() as c:
            resp = await c.post(
                "/api/v1/users/language",
                json={"telegram_id": telegram_id, "language": language},
            )
            resp.raise_for_status()
            return resp.json()

    async def handle_stars_payment(
        self,
        telegram_id: int,
        username: Optional[str],
        first_name: Optional[str],
        last_name: Optional[str],
        charge_id: str,
        total_amount: int,
        plan_id: Optional[int] = None,
        mode: str = "new",
        target_subscription_id: Optional[int] = None,
    ) -> dict:
        async with self._client() as c:
            resp = await c.post(
                "/api/v1/payments/stars",
                json={
                    "telegram_id": telegram_id,
                    "username": username,
                    "first_name": first_name,
                    "last_name": last_name,
                    "telegram_payment_charge_id": charge_id,
                    "total_amount": total_amount,
                    "plan_id": plan_id,
                    "mode": mode,
                    "target_subscription_id": target_subscription_id,
                },
            )
            resp.raise_for_status()
            return resp.json()

    async def handle_usdt_payment(
        self,
        telegram_id: int,
        username: Optional[str],
        first_name: Optional[str],
        last_name: Optional[str],
        invoice_id: str,
        amount: float,
        plan_id: Optional[int] = None,
        mode: str = "new",
        target_subscription_id: Optional[int] = None,
    ) -> dict:
        async with self._client() as c:
            resp = await c.post(
                "/api/v1/payments/usdt",
                json={
                    "telegram_id": telegram_id,
                    "username": username,
                    "first_name": first_name,
                    "last_name": last_name,
                    "invoice_id": invoice_id,
                    "amount": amount,
                    "currency": "USDT",
                    "plan_id": plan_id,
                    "mode": mode,
                    "target_subscription_id": target_subscription_id,
                },
            )
            resp.raise_for_status()
            return resp.json()

    # --- Trial ---

    async def trial_eligible(self, telegram_id: int) -> bool:
        async with self._client() as c:
            resp = await c.get("/api/v1/trial/eligible", params={"telegram_id": telegram_id})
            resp.raise_for_status()
            return resp.json()

    async def grant_trial(
        self,
        telegram_id: int,
        username: Optional[str],
        first_name: Optional[str],
        last_name: Optional[str],
    ) -> dict:
        """Raises httpx.HTTPStatusError (400) if the trial was already used
        or no trial plan is configured — callers should catch and show a
        friendly message rather than let it propagate."""
        async with self._client() as c:
            resp = await c.post(
                "/api/v1/trial/grant",
                json={
                    "telegram_id": telegram_id,
                    "username": username,
                    "first_name": first_name,
                    "last_name": last_name,
                },
            )
            resp.raise_for_status()
            return resp.json()

    # --- Admin helpers ---

    async def admin_broadcast_ids(self) -> list[int]:
        async with self._client() as c:
            resp = await c.get("/api/v1/admin/users/broadcast_ids")
            resp.raise_for_status()
            return resp.json()["telegram_ids"]

    async def admin_list_users(self, offset: int = 0) -> dict:
        async with self._client() as c:
            resp = await c.get("/api/v1/admin/users", params={"offset": offset, "limit": 20})
            resp.raise_for_status()
            return resp.json()

    async def admin_list_subscriptions(self, offset: int = 0) -> dict:
        async with self._client() as c:
            resp = await c.get(
                "/api/v1/admin/subscriptions", params={"offset": offset, "limit": 20}
            )
            resp.raise_for_status()
            return resp.json()

    async def admin_list_payments(self, offset: int = 0) -> dict:
        async with self._client() as c:
            resp = await c.get(
                "/api/v1/admin/payments", params={"offset": offset, "limit": 20}
            )
            resp.raise_for_status()
            return resp.json()

    async def admin_list_servers(self) -> dict:
        async with self._client() as c:
            resp = await c.get("/api/v1/admin/servers")
            resp.raise_for_status()
            return resp.json()

    async def admin_extend_subscription(self, sub_id: int, days: int) -> dict:
        async with self._client() as c:
            resp = await c.post(
                f"/api/v1/admin/subscriptions/{sub_id}/extend", json={"days": days}
            )
            resp.raise_for_status()
            return resp.json()

    async def admin_disable_subscription(self, sub_id: int) -> dict:
        async with self._client() as c:
            resp = await c.post(f"/api/v1/admin/subscriptions/{sub_id}/disable")
            resp.raise_for_status()
            return resp.json()

    async def admin_reissue_device(self, sub_id: int) -> dict:
        async with self._client() as c:
            resp = await c.post(f"/api/v1/admin/subscriptions/{sub_id}/reissue")
            resp.raise_for_status()
            return resp.json()

    async def admin_set_server_status(self, server_id: int, status: str) -> dict:
        async with self._client() as c:
            resp = await c.patch(
                f"/api/v1/admin/servers/{server_id}", json={"status": status}
            )
            resp.raise_for_status()
            return resp.json()

    async def admin_add_server(
        self,
        name: str,
        base_url: str,
        api_key: str,
        region: str = "EU",
        weight: int = 100,
        max_clients: int = 200,
        protocol: str = "amneziawg2",
    ) -> dict:
        async with self._client() as c:
            resp = await c.post(
                "/api/v1/admin/servers",
                json={
                    "name": name,
                    "base_url": base_url,
                    "api_key": api_key,
                    "region": region,
                    "weight": weight,
                    "max_clients": max_clients,
                    "protocol": protocol,
                },
            )
            resp.raise_for_status()
            return resp.json()


billing_client = BillingClient()
