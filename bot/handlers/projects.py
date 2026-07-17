"""Projects handler - full project drill-down navigation.

Mirrors Coolify browser GUI:
  Projects -> Project -> Environment -> Resources -> Resource Detail -> Actions/Logs

Supports both /projects command (sends new message) and callback navigation (edits same message).
"""

from __future__ import annotations

import asyncio
import logging
import re

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from bot.db.models import User
from bot.services.coolify import CoolifyClientError, coolify
from bot.services.models import Application
from bot.utils.cache import TTLCache
from bot.utils.formatting import status_emoji, fmt_relative_time
from bot.utils.states import (
    empty_state,
    error_text,
    loading_text,
    nav_back_main,
)

router = Router()
log = logging.getLogger(__name__)

# Cache
_projects_cache = TTLCache[str, list](default_ttl=60.0, max_size=5)
_apps_all_cache = TTLCache[str, list](default_ttl=60.0, max_size=5)
_services_cache = TTLCache[str, list](default_ttl=60.0, max_size=5)


async def _enrich_status(items: list) -> list:
    """Fetch full details for items with missing status (parallel, with timeout)."""
    need = [i for i in items if not getattr(i, 'status', None)]
    if not need:
        return items

    async def fetch(item):
        try:
            if isinstance(item, Application):
                return await coolify.get_application(item.uuid)
            elif hasattr(item, 'uuid'):
                return await coolify.get_service(item.uuid)
        except CoolifyClientError:
            pass
        return None

    results = await asyncio.gather(*[fetch(i) for i in need], return_exceptions=True)
    enriched = {}
    for i, item in enumerate(need):
        r = results[i]
        if isinstance(r, Exception):
            log.debug("Failed to enrich %s: %s", item.uuid, r)
        elif r is not None:
            enriched[item.uuid] = r

    return [enriched.get(i.uuid, i) for i in items]

# Russian UI strings
_LOADING_PROJECTS = "Загружаю проекты"
_ERR_PROJECTS = "Не удалось получить список проектов."
_MAIN_MENU = "Главное меню"
_PROJECTS = "Проекты"
_LOADING_PROJ = "Загружаю проект"
_ERR_PROJ = "Не удалось загрузить проект."
_ENVIRONMENTS = "Окружения"
_NO_ENVS = "Окружений нет"
_REFRESH = "Обновить"
_BACK = "Назад"
_LOADING_ENV = "Загружаю окружение"
_ERR_ENV = "Не удалось загрузить окружение."
_ERR_DATA = "Некорректные данные"
_APPS = "Приложения"
_SERVICES = "Сервисы (Compose)"
_TO_PROJ = "К проекту"
_BACK_PROJ = "Назад к проекту"
_NONE = "нет"
_LOADING_INFO = "Загружаю информацию"
_ERR_INFO = "Не удалось загрузить информацию о ресурсе."
_STATUS = "Статус"
_UNKNOWN = "неизвестен"
_DEPLOY = "Последний деплой"
_TYPE = "Тип"
_CONTAINERS = "Контейнеры"
_ACTIONS = "Действия"
_RESOURCE = "Ресурс"
_UPDATED = "Обновлено"


async def _get_projects() -> list:
    cached = _projects_cache.get("projects")
    if cached is not None:
        return cached
    projects = await coolify.list_projects()
    _projects_cache["projects"] = projects
    return projects


async def _get_apps() -> list:
    cached = _apps_all_cache.get("app_list")
    if cached is not None:
        return cached
    apps = await coolify.list_applications()
    apps = await _enrich_status(apps)
    _apps_all_cache["app_list"] = apps
    return apps


async def _get_services() -> list:
    cached = _services_cache.get("service_list")
    if cached is not None:
        return cached
    services = await coolify.list_services()
    services = await _enrich_status(services)
    _services_cache["service_list"] = services
    return services


# ── Entry from command (sends new message) ─────────────────────────────────

@router.message(Command("projects"))
async def cmd_projects(message: Message, db_user: User) -> None:
    """Show all projects (sends NEW message)."""
    msg = await message.answer(loading_text(_LOADING_PROJECTS))
    await _show_projects(msg.edit_text, db_user)


# ── Entry from callback (edits existing message) ───────────────────────────

async def show_projects_from_callback(cb: CallbackQuery, db_user: User) -> None:
    """Show project list, editing the existing message."""
    await cb.answer()
    await cb.message.edit_text(loading_text(_LOADING_PROJECTS))
    await _show_projects(cb.message.edit_text, db_user)


async def _show_projects(edit_fn, db_user: User) -> None:
    """Core logic: fetch projects and build list with inline buttons."""
    try:
        projects = await _get_projects()
    except CoolifyClientError as exc:
        text, kb = error_text(exc.message, code=str(exc.status), retry_callback="proj:retry_list")
        await edit_fn(text, reply_markup=kb)
        return
    except Exception:
        log.exception("Error listing projects")
        text, kb = error_text(_ERR_PROJECTS, retry_callback="proj:retry_list")
        await edit_fn(text, reply_markup=kb)
        return

    if not projects:
        await edit_fn(empty_state("projects"), reply_markup=nav_back_main())
        return

    lines = ["\U0001f4cb **" + _PROJECTS + "**\n"]
    kb_rows = []

    for p in projects:
        desc = f" \u2014 {p.description[:60]}" if p.description else ""
        lines.append(f"\U0001f3d7 **{p.name}**{desc}")
        lines.append(f"`{p.uuid[:8]}...`")
        lines.append("")
        kb_rows.append([
            InlineKeyboardButton(
                text=f"\U0001f4c2 {p.name}",
                callback_data=f"proj:{p.uuid}",
            )
        ])

    kb_rows.append([
        InlineKeyboardButton(text="\U0001f3e0 " + _MAIN_MENU, callback_data="menu:main")
    ])
    kb = InlineKeyboardMarkup(inline_keyboard=kb_rows)

    await edit_fn("\n".join(lines), reply_markup=kb)


# ── Project Detail ─────────────────────────────────────────────────────────

@router.callback_query(F.data.startswith("proj:"))
async def project_detail(cb: CallbackQuery, db_user: User) -> None:
    """Show project with environments as clickable buttons."""
    project_uuid = cb.data.split(":", 1)[1]
    if project_uuid == "retry_list":
        await cb.answer()
        await show_projects_from_callback(cb, db_user)
        return

    await cb.answer()

    try:
        project = await coolify.get_project(project_uuid)
        envs = await coolify.list_environments(project_uuid)
    except CoolifyClientError as exc:
        text, kb = error_text(exc.message, code=str(exc.status), retry_callback=f"proj:{project_uuid}")
        await cb.message.edit_text(text, reply_markup=kb)
        return
    except Exception:
        log.exception("Error loading project %s", project_uuid)
        text, kb = error_text(_ERR_PROJ, retry_callback=f"proj:{project_uuid}")
        await cb.message.edit_text(text, reply_markup=kb)
        return

    lines = [
        f"\U0001f3d7 **{project.name}**",
        f"`{project.uuid[:8]}...`",
    ]
    if project.description:
        lines.append(f"\n_{project.description[:200]}_")

    if envs:
        lines.append(f"\n\U0001f30d **" + _ENVIRONMENTS + " ({len(envs)}):**\n")
    else:
        lines.append(f"\n\U0001f30d **" + _NO_ENVS + "**")
        await cb.message.edit_text(
            "\n".join(lines),
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="\u2b05\ufe0f " + _BACK, callback_data="menu:projects")],
                [InlineKeyboardButton(text="\U0001f3e0 " + _MAIN_MENU, callback_data="menu:main")],
            ]),
        )
        return

    kb_rows = []
    for env in envs:
        kb_rows.append([
            InlineKeyboardButton(
                text=f"\U0001f30d {env.name}",
                callback_data=f"env:{project_uuid}:{env.name}",
            )
        ])

    kb_rows.append([
        InlineKeyboardButton(text="\U0001f504 " + _REFRESH, callback_data=f"env_refr:{project_uuid}"),
        InlineKeyboardButton(text="\u2b05\ufe0f " + _BACK, callback_data="menu:projects"),
    ])
    kb_rows.append([InlineKeyboardButton(text="\U0001f3e0 " + _MAIN_MENU, callback_data="menu:main")])

    await cb.message.edit_text(
        "\n".join(lines),
        reply_markup=InlineKeyboardMarkup(inline_keyboard=kb_rows),
    )


# ── Environment Detail ──────────────────────────────────────────────────────

@router.callback_query(F.data.startswith("env:"))
async def environment_detail(cb: CallbackQuery, db_user: User) -> None:
    """Show resources inside an environment."""
    parts = cb.data.split(":", 2)
    if len(parts) < 3:
        await cb.answer(_ERR_DATA, show_alert=True)
        return

    project_uuid, env_name = parts[1], parts[2]
    await cb.answer()

    try:
        project = await coolify.get_project(project_uuid)
        all_apps = await _get_apps()
        all_services = await _get_services()
        try:
            env_detail = await coolify.get_environment(project_uuid, env_name)
        except CoolifyClientError:
            env_detail = None
    except CoolifyClientError as exc:
        text, kb = error_text(exc.message, code=str(exc.status), retry_callback=f"env:{project_uuid}:{env_name}")
        await cb.message.edit_text(text, reply_markup=kb)
        return
    except Exception:
        log.exception("Error loading environment %s/%s", project_uuid, env_name)
        text, kb = error_text(_ERR_ENV, retry_callback=f"env:{project_uuid}:{env_name}")
        await cb.message.edit_text(text, reply_markup=kb)
        return

    env_label = env_detail.name if env_detail else env_name
    lines = [
        f"\U0001f3d7 **{project.name}** \u2192 \U0001f30d **{env_label}**",
    ]

    apps = all_apps
    services = all_services

    if not apps and not services:
        lines.append(f"\n\U0001f4e6 " + _APPS + ": _" + _NONE + "_")
        await cb.message.edit_text(
            "\n".join(lines),
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="\u2b05\ufe0f " + _BACK_PROJ, callback_data=f"proj:{project_uuid}")],
                [InlineKeyboardButton(text="\U0001f3e0 " + _MAIN_MENU, callback_data="menu:main")],
            ]),
        )
        return

    if apps:
        lines.append(f"\n\U0001f4e6 **" + _APPS + ":**")
    else:
        lines.append(f"\n\U0001f4e6 " + _APPS + ": _" + _NONE + "_")

    kb_rows = []

    for app in apps:
        em = status_emoji(app.status)
        short = app.name[:25]
        lines.append(f"{em} {short}")
        kb_rows.append([
            InlineKeyboardButton(
                text=f"{em} {short}",
                callback_data=f"res:application:{app.uuid}",
            )
        ])

    if services:
        lines.append(f"\n\U0001f9e9 **" + _SERVICES + ":**")
        for srv in services:
            em = status_emoji(srv.status)
            short = srv.name[:25]
            lines.append(f"{em} {short}")
            kb_rows.append([
                InlineKeyboardButton(
                    text=f"{em} {short}",
                    callback_data=f"res:service:{srv.uuid}",
                )
            ])

    kb_rows.append([
        InlineKeyboardButton(text="\u2b05\ufe0f " + _TO_PROJ, callback_data=f"proj:{project_uuid}")
    ])
    kb_rows.append([InlineKeyboardButton(text="\U0001f3e0 " + _MAIN_MENU, callback_data="menu:main")])

    await cb.message.edit_text(
        "\n".join(lines),
        reply_markup=InlineKeyboardMarkup(inline_keyboard=kb_rows),
    )


# ── Resource Detail ─────────────────────────────────────────────────────────

@router.callback_query(F.data.startswith("res:"))
async def resource_detail(cb: CallbackQuery, db_user: User) -> None:
    """Show resource card with action buttons."""
    parts = cb.data.split(":", 2)
    if len(parts) < 3:
        await cb.answer(_ERR_DATA, show_alert=True)
        return

    res_type, res_uuid = parts[1], parts[2]
    await cb.answer()

    try:
        if res_type == "application":
            app = await coolify.get_application(res_uuid)
            deploys = await coolify.list_deployments()
            latest = None
            for d in deploys:
                if d.application_uuid == res_uuid:
                    latest = d
                    break

            em = status_emoji(app.status)
            lines = [
                f"\U0001f4e6 **{app.name}**",
                f"" + _STATUS + ": {em} **{app.status or '" + _UNKNOWN + "'}**",
                f"`{app.uuid[:8]}...`",
            ]
            if app.fqdn:
                lines.append(f"\U0001f310 [{app.fqdn}](https://{app.fqdn})")
            if app.description:
                lines.append(f"\n_{app.description[:300]}_")
            if app.git_repository:
                lines.append(f"\n\U0001f4c2 `{app.git_repository}`")
                if app.git_branch:
                    lines.append(f"\U0001f33f `{app.git_branch}`")
            if app.docker_registry_image_name:
                lines.append(f"\U0001f433 `{app.docker_registry_image_name}:{app.docker_registry_image_tag or 'latest'}`")
            if latest:
                lines.append(f"\n\U0001f504 " + _DEPLOY + ": **{latest.status}**")
                if latest.finished_at:
                    lines.append(f"\u23f1 {fmt_relative_time(latest.finished_at)}")

        elif res_type == "service":
            # Try full detail first, fall back to list data
            try:
                srv = await coolify.get_service(res_uuid)
            except Exception as exc:
                log.warning("get_service(%s) failed: %s — falling back to list data", res_uuid, exc)
                # Search in cached list for this service
                services = await _get_services()
                srv = next((s for s in services if s.uuid == res_uuid), None)
                if not srv:
                    # Last resort: minimal object
                    from bot.services.models import Service as SvcModel
                    srv = SvcModel(uuid=res_uuid, name=res_uuid[:12], status=None)

            em = status_emoji(srv.status)
            lines = [
                f"\U0001f9e9 **{srv.name}**",
                f"" + _STATUS + ": {em} **{srv.status or '" + _UNKNOWN + "'}**",
                f"`{srv.uuid[:8]}...`",
            ]
            if srv.description:
                lines.append(f"\n_{srv.description[:300]}_")
            if srv.service_type:
                lines.append(f"\n\U0001f4cb " + _TYPE + ": `{srv.service_type}`")
            if srv.docker_compose_raw or srv.docker_compose:
                import yaml
                yaml_text = srv.docker_compose or srv.docker_compose_raw or ""
                try:
                    parsed = yaml.safe_load(yaml_text)
                    if parsed and "services" in parsed:
                        svc_names = list(parsed["services"].keys())
                        lines.append(f"\\n\\U0001f433 **" + _CONTAINERS + " ({len(svc_names)}):**")
                        for sn in svc_names:
                            lines.append(f"  \\u2022 `{sn}`")
                except Exception:
                    # Fallback: regex parse
                    svc_names = re.findall(r"^  ([a-zA-Z0-9_-]+):", yaml_text, re.MULTILINE)
                    if svc_names:
                        lines.append(f"\\n\\U0001f433 **" + _CONTAINERS + " ({len(svc_names)}):**")
                        for sn in svc_names:
                            lines.append(f"  \\u2022 `{sn}`")
        else:
            lines = [f"\U0001f4ce " + _RESOURCE + " (`{res_uuid[:8]}...`)\n\n" + _TYPE + ": {res_type}"]

        lines.append(f"\n\n**" + _ACTIONS + ":**")

        kb_rows = [
            [
                InlineKeyboardButton(text="\u25b6\ufe0f Start", callback_data=f"act_r:{res_type}:{res_uuid}:start"),
                InlineKeyboardButton(text="\u23f9 Stop", callback_data=f"act_r:{res_type}:{res_uuid}:stop"),
            ],
            [
                InlineKeyboardButton(text="\U0001f504 Restart", callback_data=f"act_r:{res_type}:{res_uuid}:restart"),
            ],
            [
                InlineKeyboardButton(text="\U0001f4cb Logs", callback_data=f"log_r:{res_type}:{res_uuid}"),
            ],
            [InlineKeyboardButton(text="\u2b05\ufe0f " + _BACK, callback_data="menu:projects")],
            [InlineKeyboardButton(text="\U0001f3e0 " + _MAIN_MENU, callback_data="menu:main")],
        ]

        await cb.message.edit_text(
            "\n".join(lines),
            reply_markup=InlineKeyboardMarkup(inline_keyboard=kb_rows),
        )

    except CoolifyClientError as exc:
        text, kb = error_text(exc.message, code=str(exc.status), retry_callback=f"res:{res_type}:{res_uuid}")
        await cb.message.edit_text(text, reply_markup=kb)
    except Exception:
        log.exception("Error loading resource %s/%s", res_type, res_uuid)
        # Try to get more details
        err_info = ""
        import traceback
        err_info = traceback.format_exc()[:200]
        log.error("Traceback details: %s", err_info)
        text, kb = error_text(_ERR_INFO, retry_callback=f"res:{res_type}:{res_uuid}")
        await cb.message.edit_text(text, reply_markup=kb)


# ── Environment Refresh ─────────────────────────────────────────────────────

@router.callback_query(F.data.startswith("env_refr:"))
async def refresh_environments(cb: CallbackQuery, db_user: User) -> None:
    """Refresh environment list for a project."""
    project_uuid = cb.data.split(":", 1)[1]
    _projects_cache.pop("projects", None)
    _apps_all_cache.pop("app_list", None)
    _services_cache.pop("service_list", None)
    await cb.answer("\U0001f504 " + _UPDATED)
    await project_detail(cb, db_user)
