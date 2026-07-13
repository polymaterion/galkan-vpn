"""
Bot configuration loaded from ENV.
"""
import os
from typing import Optional
from pydantic_settings import BaseSettings


class BotSettings(BaseSettings):
    TELEGRAM_TOKEN: str
    BILLING_BASE_URL: str = "http://billing:8000"
    BILLING_SECRET_KEY: str = ""

    ADMIN_IDS: str = ""  # comma-separated

    CRYPTOPAY_TOKEN: str = ""
    CRYPTOPAY_NETWORK: str = "mainnet"

    PLAN_PRICE_STARS: int = 100
    PLAN_PRICE_USDT: float = 3.00
    PLAN_DURATION_DAYS: int = 30

    SUPPORT_LINK: str = "https://t.me/support"

    @property
    def admin_ids_list(self) -> list[int]:
        return [int(x.strip()) for x in self.ADMIN_IDS.split(",") if x.strip()]

    class Config:
        env_file = ".env"
        extra = "ignore"


settings = BotSettings()
