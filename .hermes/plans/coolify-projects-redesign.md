# Plan: Coolify Telegram Bot — Project Navigation Redesign

## Problem
Текущий бот показывает приложения плоским списком (`/apps`), а `/projects` только читает проекты без действий. В браузерном GUI Coolify:
- **Projects → Environment → Resources** (Apps/Services/Databases) 
- Каждый ресурс → Restart/Start/Stop/Logs
- Docker-compose сервисы → несколько контейнеров (instances) с раздельными логами

## Changes Needed

### 1. Models (`bot/services/models.py`)
- Add `Service` model (docker-compose services)
- Add `Environment` model
- Add `ResourceSummary` model (lightweight resource reference)
- Add `Container` model for docker-compose instances

### 2. API Client (`bot/services/coolify.py`)
- Add service CRUD methods (list/get/start/stop/restart)
- Add project environment detail: `GET /projects/{uuid}/{env_name}`
- Add services list: `GET /services`
- Add service detail: `GET /services/{uuid}`
- Add `get_service_logs` — since Coolify API has NO /services/{uuid}/logs endpoint, we'll fallback to server-level docker log retrieval or parse container names from docker_compose_raw

### 3. Handlers

#### New file: `bot/handlers/projects.py` (rewrite from deploy.py /projects)
- `cmd_projects` → list all projects with inline buttons
- `project_detail` → show project info + environments list
- `environment_detail` → show resources (apps/services/dbs) in environment
- `resource_detail` → show resource card with action buttons (restart/start/stop/logs)

#### New file: `bot/handlers/services.py`
- Service list, detail, actions
- Service instances (containers) list
- Per-container logs

#### Modify `bot/handlers/apps.py`
- Add project/environment context to app views
- Show app in project tree context

#### Modify `bot/handlers/actions.py`
- Extend to support service actions (start/stop/restart)
- Support container actions

#### Modify `bot/router.py`
- Add new routers: projects, services

### 4. Callback Architecture
- `proj:<uuid>` → Project detail
- `env:<uuid>:<name>` → Environment detail  
- `res:<uuid>:<type>` → Resource detail (type=app|service|db)
- `srv:<uuid>` → Service detail
- `inst:<uuid>:<name>` → Container/Instance detail
- `act:<type>:<uuid>:<action>` → Action confirm (extend existing)
- `logs:<type>:<uuid>` → Logs for resource
- `clogs:<uuid>:<container>` → Container logs

### 5. Multi-Container Logs (Docker-Compose)
For docker-compose services, Coolify API doesn't have /services/{uuid}/logs.
Solution: Parse `docker_compose_raw` to get service names → construct container names → use server SSH/docker commands OR call application-style logs if available.
Fallback: Show raw docker-compose and tell user to check server directly for per-container logs.
Actually, looking more carefully: Coolify internally creates an "application" entry for each docker-compose service. We can trace resources via GET /resources or GET /projects/{uuid}/{env_name}.

## Implementation Order
1. Add models (Service, Environment, ResourceSummary)
2. Extend CoolifyClient (service methods, env methods)
3. Create projects.py handler (full drill-down)
4. Create services.py handler (service management)
5. Update actions.py for services
6. Update apps.py for project context
7. Update router.py
8. Syntax check + integration test

## UX Design / Navigation
- Single-message editing
- Breadcrumb: `🏗 Projects > Project Name > Production > App Name`
- Loading/Empty/Error states per screen
- Pagination for long lists
