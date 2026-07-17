"""Pydantic models for Coolify API responses."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


# ── Resource type constants ──────────────────────────────────────────────────

class ResourceType:
    APPLICATION = "application"
    SERVICE = "service"
    DATABASE = "database"


# ── Project ──────────────────────────────────────────────────────────────────

class Project(BaseModel):
    """Coolify project."""

    id: int | None = None
    uuid: str
    name: str
    description: str | None = None


# ── Environment ──────────────────────────────────────────────────────────────

class Environment(BaseModel):
    """Coolify environment within a project."""

    id: int | None = None
    uuid: str | None = None
    name: str
    description: str | None = None
    project_uuid: str | None = None


# ── Resource Summary ─────────────────────────────────────────────────────────

class ResourceSummary(BaseModel):
    """Lightweight resource reference (used in environment listing)."""

    uuid: str
    name: str
    resource_type: str  # application | service | database
    status: str | None = None
    description: str | None = None
    fqdn: str | None = None


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


# ── Service (Docker Compose) ─────────────────────────────────────────────────

class Service(BaseModel):
    """Coolify docker-compose service resource."""

    model_config = {"extra": "ignore"}

    id: int | None = None
    uuid: str | None = None
    name: str | None = None
    description: str | None = None
    environment_id: int | None = None
    server_id: int | None = None
    docker_compose_raw: str | None = None
    docker_compose: str | None = None
    destination_type: str | None = None
    destination_id: int | None = None
    connect_to_docker_network: bool | None = None
    is_container_label_escape_enabled: bool | None = None
    is_container_label_readonly_enabled: bool | None = None
    config_hash: str | None = None
    service_type: str | None = None
    status: str | None = None
    created_at: str | None = None
    updated_at: str | None = None
    deleted_at: str | None = None


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


# ── CoolifyError ─────────────────────────────────────────────────────────────

class CoolifyError(BaseModel):
    """Standard Coolify API error."""

    message: str
    status: int = 500
