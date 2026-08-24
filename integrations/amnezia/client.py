"""
Thin HTTP adapter over the kyoresuas/amnezia-api REST API.

All business logic lives in billing/services, NOT here.
This module is a pure HTTP client — it maps Python calls to HTTP endpoints.

Endpoints (kyoresuas/amnezia-api, actual REST surface — see /docs on your instance):
  GET    /clients         — list clients
  POST   /clients         — create client
  DELETE /clients         — delete client (body: {clientId, protocol})
  PATCH  /clients         — update client (body: {clientId, protocol, status?, expiresAt?})
  GET    /server          — server status / metrics
  GET    /healthz         — health check

Note: clientId and protocol are always passed in the request body, never in the
URL path — the API has no /clients/{id} route for mutations.
"""
from __future__ import annotations

import logging
from typing import Any, Optional

import httpx
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from integrations.amnezia.errors import (
    AmneziaClientError,
    AmneziaConnectionError,
    AmneziaNotFoundError,
    AmneziaServerError,
)
from integrations.amnezia.schemas import (
    AmneziaClientRecord,
    CreateClientRequest,
    CreateClientResponse,
    ServerInfo,
    UpdateClientRequest,
)

logger = logging.getLogger(__name__)


class AmneziaClient:
    """
    HTTP client for one amnezia-api server instance.
    Each VPN server in the DB gets its own AmneziaClient at call time.
    """

    DEFAULT_TIMEOUT = 15.0

    def __init__(self, base_url: str, api_key: str, timeout: float = DEFAULT_TIMEOUT):
        self._base_url = base_url.rstrip("/")
        self._headers = {
            "x-api-key": api_key,
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        self._timeout = timeout

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _make_client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            base_url=self._base_url,
            headers=self._headers,
            timeout=self._timeout,
        )

    def _raise_for_status(self, resp: httpx.Response) -> None:
        if resp.status_code == 404:
            raise AmneziaNotFoundError(f"Resource not found: {resp.url}")
        if 400 <= resp.status_code < 500:
            body = _safe_json(resp)
            raise AmneziaClientError(
                f"Client error {resp.status_code}: {body.get('message', resp.text)}"
            )
        if resp.status_code >= 500:
            raise AmneziaServerError(
                f"Server error {resp.status_code}: {resp.text[:200]}"
            )

    # ------------------------------------------------------------------
    # Retry decorator factory
    # ------------------------------------------------------------------

    @staticmethod
    def _retryable(fn):
        return retry(
            retry=retry_if_exception_type((AmneziaServerError, AmneziaConnectionError)),
            wait=wait_exponential(multiplier=1, min=2, max=30),
            stop=stop_after_attempt(3),
            reraise=True,
        )(fn)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def healthcheck(self) -> bool:
        """Returns True if the server responds to /healthz."""
        try:
            async with self._make_client() as client:
                resp = await client.get("/healthz")
                return resp.status_code == 200
        except (httpx.ConnectError, httpx.TimeoutException):
            return False

    @_retryable
    async def get_server_info(self) -> ServerInfo:
        """GET /server — returns CPU, RAM, uptime, client count, etc."""
        try:
            async with self._make_client() as client:
                resp = await client.get("/server")
        except (httpx.ConnectError, httpx.TimeoutException) as exc:
            raise AmneziaConnectionError(str(exc)) from exc
        self._raise_for_status(resp)
        data = resp.json()
        return ServerInfo.model_validate(data)

    @_retryable
    async def get_clients(
        self, skip: int = 0, limit: int = 100
    ) -> list[AmneziaClientRecord]:
        """GET /clients?skip=0&limit=100"""
        try:
            async with self._make_client() as client:
                resp = await client.get("/clients", params={"skip": skip, "limit": limit})
        except (httpx.ConnectError, httpx.TimeoutException) as exc:
            raise AmneziaConnectionError(str(exc)) from exc
        self._raise_for_status(resp)
        data = resp.json()
        items = data.get("items", data) if isinstance(data, dict) else data
        return [AmneziaClientRecord.model_validate(i) for i in items]

    @_retryable
    async def create_client(self, req: CreateClientRequest) -> CreateClientResponse:
        """POST /clients"""
        try:
            async with self._make_client() as client:
                resp = await client.post("/clients", json=req.model_dump(exclude_none=True))
        except (httpx.ConnectError, httpx.TimeoutException) as exc:
            raise AmneziaConnectionError(str(exc)) from exc
        self._raise_for_status(resp)
        return CreateClientResponse.model_validate(resp.json())

    @_retryable
    async def delete_client(self, client_id: str, protocol: str = "amneziawg2") -> None:
        """DELETE /clients  body: {clientId, protocol}"""
        try:
            async with self._make_client() as client:
                resp = await client.request(
                    "DELETE",
                    "/clients",
                    json={"clientId": client_id, "protocol": protocol},
                )
        except (httpx.ConnectError, httpx.TimeoutException) as exc:
            raise AmneziaConnectionError(str(exc)) from exc
        self._raise_for_status(resp)

    @_retryable
    async def update_client(
        self, client_id: str, req: UpdateClientRequest, protocol: str = "amneziawg2"
    ) -> None:
        """
        PATCH /clients   body: {clientId, protocol, status?, expiresAt?}
        Used to enable/disable a client (status: "active" | "disabled").
        Note: clientId/protocol travel in the body — there is no /clients/{id} route.
        """
        try:
            async with self._make_client() as client:
                payload = {"clientId": client_id, "protocol": protocol}
                payload.update(req.model_dump(exclude_none=True))
                resp = await client.patch("/clients", json=payload)
        except (httpx.ConnectError, httpx.TimeoutException) as exc:
            raise AmneziaConnectionError(str(exc)) from exc
        # 404 on update might mean this client/protocol pair doesn't exist upstream
        if resp.status_code == 404:
            logger.warning(
                "PATCH /clients (clientId=%s, protocol=%s) returned 404 — "
                "client may not exist on this server",
                client_id,
                protocol,
            )
            return
        self._raise_for_status(resp)

    async def disable_client(self, client_id: str, protocol: str = "amneziawg2") -> None:
        await self.update_client(client_id, UpdateClientRequest(status="disabled"), protocol=protocol)

    async def enable_client(self, client_id: str, protocol: str = "amneziawg2") -> None:
        await self.update_client(client_id, UpdateClientRequest(status="active"), protocol=protocol)

    async def get_client(self, client_id: str) -> Optional[AmneziaClientRecord]:
        """Fetch a single client by scanning the list. amnezia-api has no GET /clients/{id}."""
        clients = await self.get_clients(limit=1000)
        for c in clients:
            for device in c.devices:
                if device.id == client_id:
                    # Wrap single device back into record shape for convenience
                    return c
        return None


# ------------------------------------------------------------------
# Helper
# ------------------------------------------------------------------

def _safe_json(resp: httpx.Response) -> dict[str, Any]:
    try:
        return resp.json()
    except Exception:
        return {}
