"""
CryptoPay payment adapter (https://t.me/CryptoBot).
Implements USDT invoice creation and verification.
"""
from __future__ import annotations

import logging
from typing import Optional

import httpx

from bot.config import settings

logger = logging.getLogger(__name__)

CRYPTOPAY_MAINNET = "https://pay.crypt.bot/api"
CRYPTOPAY_TESTNET = "https://testnet-pay.crypt.bot/api"


class CryptoPayAdapter:
    def __init__(self):
        base_url = (
            CRYPTOPAY_MAINNET
            if settings.CRYPTOPAY_NETWORK == "mainnet"
            else CRYPTOPAY_TESTNET
        )
        self._base = base_url
        self._token = settings.CRYPTOPAY_TOKEN

    def _client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            base_url=self._base,
            headers={"Crypto-Pay-API-Token": self._token},
            timeout=15.0,
        )

    async def create_invoice(
        self,
        amount: float,
        asset: str = "USDT",
        description: str = "VPN Subscription",
        payload: str = "",
        expires_in: int = 3600,
    ) -> dict:
        """
        Create a CryptoPay invoice.
        Returns the full invoice dict including pay_url.
        """
        async with self._client() as c:
            resp = await c.post(
                "/createInvoice",
                json={
                    "asset": asset,
                    "amount": str(amount),
                    "description": description,
                    "payload": payload,
                    "expires_in": expires_in,
                },
            )
            resp.raise_for_status()
            data = resp.json()
            if not data.get("ok"):
                raise RuntimeError(f"CryptoPay error: {data}")
            return data["result"]

    async def get_invoice(self, invoice_id: int) -> Optional[dict]:
        async with self._client() as c:
            resp = await c.get("/getInvoices", params={"invoice_ids": str(invoice_id)})
            resp.raise_for_status()
            data = resp.json()
            items = data.get("result", {}).get("items", [])
            return items[0] if items else None

    async def is_paid(self, invoice_id: int) -> bool:
        inv = await self.get_invoice(invoice_id)
        return inv is not None and inv.get("status") == "paid"


crypto_pay = CryptoPayAdapter()
