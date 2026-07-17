"""Pydantic models for Coolify API responses."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


# ── Application ──────────────────────────────────────────────────────────────

class Application(BaseModel):
    """Coolify application resource."""

    id: int | None = None
    uuid: str
    name: str
    description: str | None = None
    fqdn: str | None = None
    git_repository: str | None = None
    git_branch: str | None = None
    git_commit_sha: str | None = None
    docker_registry_image_name: str | None = None
    docker_registry_image_tag: str | None = None
    build_pack: str | None = None
    status: str | None = None
    is_auto_deploy_enabled: bool = True
    is_force_https_enabled: bool = True
    destination_docker: str | None = None
    created_at: str | None = None
    updated_at: str | None = None


# ── Application Deployment Queue ─────────────────────────────────────────────

class ApplicationDeploymentQueue(BaseModel):
    """A deployment queue entry."""

    id: int | None = None
    application_uuid: str | None = None
    deployment_uuid: str | None = None
    status: str | None = None  # queued, building, running, failed, finished, cancelled
    commit_sha: str | None = None
    commit_message: str | None = None
    author: str | None = None
    started_at: str | None = None
    finished_at: str | None = None
    logs: str | None = None
    created_at: str | None = None
    updated_at: str | None = None


# ── Server ───────────────────────────────────────────────────────────────────

class Server(BaseModel):
    """Coolify server resource."""

    id: int | None = None
    uuid: str
    name: str
    description: str | None = None
    ip: str | None = None
    host: str | None = None
    port: int = 22
    user: str = "root"
    is_reachable: bool | None = None
    is_swarm_manager: bool | None = None
    is_swarm_worker: bool | None = None
    is_build_server: bool | None = None
    settings: dict[str, Any] | None = None
    created_at: str | None = None
    updated_at: str | None = None


# ── Team ─────────────────────────────────────────────────────────────────────

class Team(BaseModel):
    """Coolify team."""

    id: int
    name: str
    description: str | None = None
    created_at: str | None = None
    updated_at: str | None = None


# ── Health ───────────────────────────────────────────────────────────────────

class HealthResponse(BaseModel):
    """Health check response."""

    status: str = "ok"
    version: str | None = None
    uptime: int | None = None


# ── Deploy Request ───────────────────────────────────────────────────────────

class DeployResponse(BaseModel):
    """Response from triggering a deployment."""

    deployment_uuid: str | None = None
    status: str = "queued"
    message: str = ""


# ── Generic ──────────────────────────────────────────────────────────────────

class CoolifyError(BaseModel):
    """Standard Coolify API error."""

    message: str
    status: int = 500
