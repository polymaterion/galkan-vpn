import random
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models.models import VpnServer, VpnServerStatus


class VpnServerRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_by_id(self, server_id: int) -> Optional[VpnServer]:
        result = await self.session.execute(
            select(VpnServer).where(VpnServer.id == server_id)
        )
        return result.scalar_one_or_none()

    async def get_all(self) -> list[VpnServer]:
        result = await self.session.execute(select(VpnServer).order_by(VpnServer.id))
        return list(result.scalars().all())

    async def create(
        self,
        name: str,
        base_url: str,
        api_key: str,
        region: Optional[str] = "EU",
        weight: int = 100,
        max_clients: int = 200,
        protocol: str = "amneziawg2",
    ) -> VpnServer:
        server = VpnServer(
            name=name,
            base_url=base_url,
            api_key=api_key,
            region=region,
            weight=weight,
            status=VpnServerStatus.active,
            max_clients=max_clients,
            current_clients=0,
            protocol=protocol,
        )
        self.session.add(server)
        await self.session.flush()
        return server

    async def delete(self, server_id: int) -> None:
        server = await self.get_by_id(server_id)
        if server:
            await self.session.delete(server)

    async def get_available_servers(self) -> list[VpnServer]:
        """Return active, not-overloaded servers."""
        result = await self.session.execute(
            select(VpnServer).where(VpnServer.status == VpnServerStatus.active)
        )
        servers = list(result.scalars().all())
        return [s for s in servers if s.current_clients < s.max_clients]

    async def select_server(self) -> Optional[VpnServer]:
        """
        Weighted random selection among available servers.
        Higher weight = more likely to be picked.
        Servers with fewer clients get a small bonus.
        """
        servers = await self.get_available_servers()
        if not servers:
            return None
        if len(servers) == 1:
            return servers[0]

        # Score = weight * (1 - load_ratio)
        def score(s: VpnServer) -> float:
            load_ratio = s.current_clients / max(s.max_clients, 1)
            return s.weight * (1.0 - load_ratio)

        scores = [score(s) for s in servers]
        total = sum(scores)
        if total <= 0:
            return random.choice(servers)

        # Weighted random choice
        pick = random.uniform(0, total)
        cumulative = 0.0
        for server, sc in zip(servers, scores):
            cumulative += sc
            if pick <= cumulative:
                return server
        return servers[-1]

    async def increment_clients(self, server_id: int) -> None:
        server = await self.get_by_id(server_id)
        if server:
            server.current_clients += 1

    async def decrement_clients(self, server_id: int) -> None:
        server = await self.get_by_id(server_id)
        if server and server.current_clients > 0:
            server.current_clients -= 1
