"""
Pydantic schemas for the amnezia-api REST responses.
These match the actual JSON structure from kyoresuas/amnezia-api.
"""
from __future__ import annotations

from typing import Any, Optional
from pydantic import BaseModel, Field, field_validator


class DeviceRecord(BaseModel):
    id: str
    name: Optional[str] = None
    allowedIps: Optional[list[str]] = None
    lastHandshake: Optional[int] = None
    traffic: Optional[dict[str, int]] = None
    online: Optional[bool] = None
    endpoint: Optional[str] = None
    expiresAt: Optional[int] = None
    protocol: Optional[str] = None


class AmneziaClientRecord(BaseModel):
    """One user (username) with one or more devices."""
    username: str
    devices: list[DeviceRecord] = Field(default_factory=list)


class CreateClientRequest(BaseModel):
    clientName: str
    protocol: str = "amneziawg2"
    expiresAt: Optional[int] = None  # unix timestamp or null


class CreatedClient(BaseModel):
    id: str
    config: str   # vpn:// URL
    protocol: str


class CreateClientResponse(BaseModel):
    message: Optional[str] = None
    client: CreatedClient


class UpdateClientRequest(BaseModel):
    """PATCH /clients body (clientId/protocol added by AmneziaClient). status: "active" | "disabled"."""
    status: Optional[str] = None
    expiresAt: Optional[int] = None


class DeleteClientRequest(BaseModel):
    clientId: str
    protocol: str = "amneziawg"


# ---------------------------------------------------------------------------
# Server metrics
# ---------------------------------------------------------------------------

class ContainerStat(BaseModel):
    name: Optional[str] = None
    status: Optional[str] = None
    cpu: Optional[float] = None
    memory: Optional[str] = None


class ServerInfo(BaseModel):
    """Response from GET /server"""
    cpu: Optional[Any] = None
    memory: Optional[Any] = None
    disk: Optional[Any] = None
    uptime: Optional[Any] = None
    load: Optional[Any] = None
    network: Optional[Any] = None
    containers: Optional[list[ContainerStat]] = None
    # Some versions nest everything under "server":
    server: Optional[dict[str, Any]] = None

    @property
    def active_clients(self) -> int:
        """Best-effort client count from server info."""
        if self.containers:
            return len(self.containers)
        return 0
