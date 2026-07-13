"""
Seed script: creates one default plan and two sample VPN servers.
Run once after migrate.
"""
import asyncio
import os

from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from sqlalchemy import select, text

from models.models import Plan, VpnServer, VpnServerStatus

DATABASE_URL = os.environ["DATABASE_URL"]


async def seed():
    engine = create_async_engine(DATABASE_URL)
    async_session = async_sessionmaker(engine, expire_on_commit=False)

    async with async_session() as session:
        # --- Plan ---
        result = await session.execute(select(Plan).limit(1))
        if not result.scalar_one_or_none():
            plan = Plan(
                name="VPN — 30 дней",
                description="Безлимитный VPN на 30 дней. AmneziaWG протокол.",
                duration_days=30,
                price_stars=int(os.getenv("PLAN_PRICE_STARS", "100")),
                price_usdt=float(os.getenv("PLAN_PRICE_USDT", "3.00")),
                is_active=True,
            )
            session.add(plan)
            print("[seed] Created default plan")
        else:
            print("[seed] Plan already exists, skip")

        # --- VPN Servers (sample, configure real ones via admin or env) ---
        result = await session.execute(select(VpnServer).limit(1))
        if not result.scalar_one_or_none():
            servers = [
                VpnServer(
                    name="Server EU-1",
                    base_url=os.getenv("VPN_SERVER1_URL", "http://vpn-server-1:4001"),
                    api_key=os.getenv("VPN_SERVER1_KEY", "replace_with_real_api_key"),
                    region="EU",
                    weight=100,
                    status=VpnServerStatus.active,
                    max_clients=200,
                    current_clients=0,
                ),
                VpnServer(
                    name="Server EU-2",
                    base_url=os.getenv("VPN_SERVER2_URL", "http://vpn-server-2:4001"),
                    api_key=os.getenv("VPN_SERVER2_KEY", "replace_with_real_api_key"),
                    region="EU",
                    weight=80,
                    status=VpnServerStatus.active,
                    max_clients=200,
                    current_clients=0,
                ),
            ]
            session.add_all(servers)
            print("[seed] Created 2 sample VPN servers")
        else:
            print("[seed] VPN servers already exist, skip")

        await session.commit()

    await engine.dispose()
    print("[seed] Done.")


if __name__ == "__main__":
    asyncio.run(seed())
