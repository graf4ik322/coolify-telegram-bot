"""Async HTTP client for Coolify REST API v1."""

from __future__ import annotations

import logging
from typing import Any

import aiohttp

from bot.config import settings
from bot.services.models import (
    Application,
    ApplicationDeploymentQueue,
    CoolifyError,
    DeployResponse,
    HealthResponse,
    Server,
    Team,
)

log = logging.getLogger(__name__)


class CoolifyClientError(Exception):
    """Wrapper for Coolify API errors."""

    def __init__(self, status: int, message: str) -> None:
        self.status = status
        self.message = message
        super().__init__(f"[{status}] {message}")


class CoolifyClient:
    """Thin async wrapper around Coolify REST API.

    All public methods raise ``CoolifyClientError`` on non-2xx responses
    (including network errors mapped to 503).
    """

    BASE_URL = settings.coolify_api_url.rstrip("/")

    def __init__(self) -> None:
        self._session: aiohttp.ClientSession | None = None

    # ── lifecycle ──────────────────────────────────────────────────────────

    async def _ensure_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(
                headers={
                    "Authorization": f"Bearer {settings.coolify_api_token}",
                    "Content-Type": "application/json",
                },
                timeout=aiohttp.ClientTimeout(total=10),
            )
        return self._session

    async def close(self) -> None:
        if self._session and not self._session.closed:
            await self._session.close()

    # ── internal ───────────────────────────────────────────────────────────

    async def _request(
        self,
        method: str,
        path: str,
        **kwargs: Any,
    ) -> Any:
        session = await self._ensure_session()
        url = f"{self.BASE_URL}{path}"
        try:
            async with session.request(method, url, **kwargs) as resp:
                if resp.status >= 400:
                    try:
                        body = await resp.json()
                        msg = body.get("message", body.get("error", str(body)))
                    except Exception:
                        msg = await resp.text()
                    raise CoolifyClientError(resp.status, msg)
                if resp.status == 204:
                    return None
                return await resp.json()
        except CoolifyClientError:
            raise
        except aiohttp.ClientError as exc:
            raise CoolifyClientError(503, f"Network error: {exc}") from exc

    # ── Health / Version ───────────────────────────────────────────────────

    async def health(self) -> HealthResponse:
        data = await self._request("GET", "/health")
        return HealthResponse(**data)

    async def version(self) -> str:
        data = await self._request("GET", "/version")
        return data.get("version", "unknown")

    # ── Teams ──────────────────────────────────────────────────────────────

    async def current_team(self) -> Team:
        data = await self._request("GET", "/teams/current")
        return Team(**data)

    # ── Applications ────────────────────────────────────────────────────────

    async def list_applications(self, tag: str | None = None) -> list[Application]:
        params: dict[str, str] = {}
        if tag:
            params["tag"] = tag
        data = await self._request("GET", "/applications", params=params)
        return [Application(**app) for app in data]

    async def get_application(self, uuid: str) -> Application:
        data = await self._request("GET", f"/applications/{uuid}")
        return Application(**data)

    async def get_application_logs(self, uuid: str, lines: int = 100) -> str:
        data = await self._request(
            "GET",
            f"/applications/{uuid}/logs",
            params={"lines": str(lines)},
        )
        # Coolify returns either a string or an object with logs field
        if isinstance(data, str):
            return data
        if isinstance(data, dict):
            return data.get("logs", data.get("message", str(data)))
        return str(data)

    # ── Application Lifecycle ──────────────────────────────────────────────

    async def start_application(self, uuid: str, force: bool = False) -> dict[str, Any]:
        params = {"force": "true"} if force else {}
        return await self._request("GET", f"/applications/{uuid}/start", params=params)

    async def stop_application(self, uuid: str, cleanup: bool = True) -> dict[str, Any]:
        params = {"docker_cleanup": "true"} if cleanup else {}
        return await self._request("GET", f"/applications/{uuid}/stop", params=params)

    async def restart_application(self, uuid: str) -> dict[str, Any]:
        return await self._request("GET", f"/applications/{uuid}/restart")

    # ── Deploy ─────────────────────────────────────────────────────────────

    async def deploy(
        self,
        tag: str | None = None,
        force: bool = False,
    ) -> DeployResponse:
        params: dict[str, str] = {}
        if tag:
            params["tag"] = tag
        if force:
            params["force"] = "true"
        data = await self._request("GET", "/deploy", params=params)
        return DeployResponse(**data)

    async def list_deployments(self) -> list[ApplicationDeploymentQueue]:
        data = await self._request("GET", "/deployments")
        return [ApplicationDeploymentQueue(**d) for d in data]

    async def get_deployment(self, uuid: str) -> ApplicationDeploymentQueue:
        data = await self._request("GET", f"/deployments/{uuid}")
        return ApplicationDeploymentQueue(**data)

    async def cancel_deployment(self, uuid: str) -> dict[str, Any]:
        return await self._request("POST", f"/deployments/{uuid}/cancel")

    # ── Servers ────────────────────────────────────────────────────────────

    async def list_servers(self) -> list[Server]:
        data = await self._request("GET", "/servers")
        return [Server(**srv) for srv in data]

    async def get_server(self, uuid: str) -> Server:
        data = await self._request("GET", f"/servers/{uuid}")
        return Server(**data)

    # ── Convenience for all resources ──────────────────────────────────────

    async def list_all_resources(self) -> list[dict[str, Any]]:
        """Return all resources via the unified /resources endpoint."""
        return await self._request("GET", "/resources")


# Singleton instance
coolify = CoolifyClient()
