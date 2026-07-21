"""
Seed script: creates one default plan and any VPN servers configured via env vars.
Run once after migrate.

VPN servers are picked up dynamically from env vars of the form:
  VPN_SERVER{N}_URL, VPN_SERVER{N}_KEY  (N = 1, 2, 3, ...)
  VPN_SERVER{N}_NAME, VPN_SERVER{N}_REGION, VPN_SERVER{N}_WEIGHT  (optional)
  VPN_SERVER{N}_PROTOCOL  (optional, default "amneziawg2" — must match what's
    actually installed/enabled on that server's amnezia-api instance, see its
    .env: PROTOCOLS_ENABLED. Wrong value causes 400 Bad Request on client creation.)

Only servers with both *_URL and *_KEY actually set (non-empty, not a leftover
placeholder) are created. This means:
  - With just VPN_SERVER1_URL/VPN_SERVER1_KEY set, only one server is seeded.
  - To add more servers later, either add VPN_SERVER2_URL/VPN_SERVER2_KEY (etc.)
    to .env *before* the very first run of this script, or — since this script
    only runs once (it skips seeding if any VpnServer already exists) — use the
    admin API/bot command to add servers afterwards:
      POST /api/v1/admin/servers   (see api/routers/admin.py)
      /add_server command in the bot admin panel
"""
import asyncio
import os

from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from sqlalchemy import select

from models.models import Plan, VpnServer, VpnServerStatus

DATABASE_URL = os.environ["DATABASE_URL"]

# Values that mean "not actually configured, don't seed this server"
_PLACEHOLDER_MARKERS = {"", "replace_with_real_api_key"}
_MAX_SERVER_SLOTS = 10  # how many VPN_SERVER{N}_* slots to scan for


def _configured_servers() -> list[VpnServer]:
    """Build VpnServer objects from VPN_SERVER{N}_* env vars that are actually set."""
    servers: list[VpnServer] = []
    for n in range(1, _MAX_SERVER_SLOTS + 1):
        url = os.getenv(f"VPN_SERVER{n}_URL", "").strip()
        key = os.getenv(f"VPN_SERVER{n}_KEY", "").strip()

        if not url or not key or key in _PLACEHOLDER_MARKERS:
            # Not configured — skip silently. This is expected for slots beyond
            # the servers you actually have (e.g. VPN_SERVER2 when you only run one).
            continue

        servers.append(
            VpnServer(
                name=os.getenv(f"VPN_SERVER{n}_NAME", f"Server {n}"),
                base_url=url,
                api_key=key,
                region=os.getenv(f"VPN_SERVER{n}_REGION", "EU"),
                weight=int(os.getenv(f"VPN_SERVER{n}_WEIGHT", "100")),
                status=VpnServerStatus.active,
                max_clients=int(os.getenv(f"VPN_SERVER{n}_MAX_CLIENTS", "200")),
                current_clients=0,
                protocol=os.getenv(f"VPN_SERVER{n}_PROTOCOL", "amneziawg2"),
            )
        )
    return servers


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

        # --- VPN Servers: only ones with real config in env ---
        result = await session.execute(select(VpnServer).limit(1))
        if not result.scalar_one_or_none():
            servers = _configured_servers()
            if servers:
                session.add_all(servers)
                names = ", ".join(s.name for s in servers)
                print(f"[seed] Created {len(servers)} VPN server(s): {names}")
            else:
                print(
                    "[seed] WARNING: no VPN_SERVER*_URL/*_KEY configured in env — "
                    "no VPN servers were created. Add at least VPN_SERVER1_URL and "
                    "VPN_SERVER1_KEY to .env and re-run, or add a server later via "
                    "the admin API/bot."
                )
        else:
            print("[seed] VPN servers already exist, skip")

        await session.commit()

    await engine.dispose()
    print("[seed] Done.")


if __name__ == "__main__":
    asyncio.run(seed())
