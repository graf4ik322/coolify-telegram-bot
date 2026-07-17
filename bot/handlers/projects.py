# -*- coding: utf-8 -*-
"""Projects handler - full project drill-down navigation.

Mirrors Coolify browser GUI:
  Projects -> Project -> Environment -> Resources -> Resource Detail -> Actions/Logs

Uses single-message editing throughout.
"""

from __future__ import annotations

import logging
import re

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from bot.db.models import User
from bot.services.coolify import CoolifyClientError, coolify
from bot.utils.cache import TTLCache
from bot.utils.formatting import status_emoji
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

@router.message(Command("projects"))
async def cmd_projects(message: Message, db_user: User) -> None:
    """Show all projects (sends NEW message)."""
    msg = await message.answer(loading_text("Загружаю проекты"))
    try:
        projects = await _get_projects()
    except CoolifyClientError as exc:
        text, kb = error_text(exc.message, code=str(exc.status), retry_callback="proj:retry_list")
        await msg.edit_text(text, reply_markup=kb)
        return
    except Exception:
        log.exception("Error listing projects")
        text, kb = error_text("Не удалось получить список проектов.", retry_callback="proj:retry_list")
        await msg.edit_text(text, reply_markup=kb)
        return
    if not projects:
        await msg.edit_text(empty_state("projects"), reply_markup=nav_back_main())
        return
    lines = ["\U0001f4cb **Проекты**\n"]
    kb_buttons = []
    for p in projects:
        desc = f" \u2014 {p.description[:60]}" if p.description else ""
        lines.append(f"\U0001f3d7 **{p.name}**{desc}")
        lines.append(f"`{p.uuid[:8]}...`")
        lines.append("")
        kb_buttons.append([InlineKeyboardButton(text=f"\U0001f4c2 {p.name}", callback_data=f"proj:{p.uuid}")])
    kb_buttons.append([InlineKeyboardButton(text="\U0001f3e0 Главное меню", callback_data="menu:main")])
    kb = InlineKeyboardMarkup(inline_keyboard=kb_buttons)
    await msg.edit_text("\n".join(lines), reply_markup=kb)

async def _get_projects() -> list:
    cached = _projects_cache.get("projects")
    if cached is not None: return cached
    projects = await coolify.list_projects()
    _projects_cache["projects"] = projects
    return projects

async def _get_apps() -> list:
    cached = _apps_all_cache.get("app_list")
    if cached is not None: return cached
    apps = await coolify.list_applications()
    _apps_all_cache["app_list"] = apps
    return apps

async def _get_services() -> list:
    cached = _services_cache.get("service_list")
    if cached is not None: return cached
    services = await coolify.list_services()
    _services_cache["service_list"] = services
    return services

@router.callback_query(F.data.startswith("proj:"))
async def project_detail(cb: CallbackQuery, db_user: User) -> None:
    """Show project detail with environments list."""
    project_uuid = cb.data.split(":", 1)[1]
    if project_uuid == "retry_list":
        await cb.answer(); await cmd_projects(cb.message, db_user); return
    await cb.answer()
    await cb.message.edit_text(loading_text("Загружаю проект"))
    try:
        project = await coolify.get_project(project_uuid)
        envs = await coolify.list_environments(project_uuid)
    except CoolifyClientError as exc:
        text, kb = error_text(exc.message, code=str(exc.status), retry_callback=f"proj:{project_uuid}")
        await cb.message.edit_text(text, reply_markup=kb); return
    except Exception:
        log.exception("Error loading project %s", project_uuid)
        text, kb = error_text("Не удалось загрузить проект.", retry_callback=f"proj:{project_uuid}")
        await cb.message.edit_text(text, reply_markup=kb); return
    lines = [f"\U0001f3d7 **{project.name}**", f"`{project.uuid[:8]}...`"]
    if project.description:
        lines.append(f"\n_{project.description[:200]}_")
    if envs:
        lines.append(f"\n\U0001f30d **Окружения ({len(envs)}):**\n")
    else:
        lines.append(f"\n\U0001f30d **Окружений нет**")
    kb_rows = []
    for env in envs:
        kb_rows.append([InlineKeyboardButton(text=f"\U0001f30d {env.name}", callback_data=f"env:{project_uuid}:{env.name}")])
    kb_rows.append([InlineKeyboardButton(text="\U0001f504 Обновить", callback_data=f"env_refr:{project_uuid}"), InlineKeyboardButton(text="\u2b05\ufe0f Назад", callback_data="menu:projects")])
    kb_rows.append([InlineKeyboardButton(text="\U0001f3e0 Главное меню", callback_data="menu:main")])
    await cb.message.edit_text("\n".join(lines), reply_markup=InlineKeyboardMarkup(inline_keyboard=kb_rows))

@router.callback_query(F.data.startswith("env:"))
async def environment_detail(cb: CallbackQuery, db_user: User) -> None:
    """Show environment detail with resources (apps/services)."""
    parts = cb.data.split(":", 2)
    if len(parts) < 3:
        await cb.answer("❌ Некорректные данные", show_alert=True); return
    project_uuid, env_name = parts[1], parts[2]
    await cb.answer()
    await cb.message.edit_text(loading_text("Загружаю окружение"))
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
        await cb.message.edit_text(text, reply_markup=kb); return
    except Exception:
        log.exception("Error loading environment %s/%s", project_uuid, env_name)
        text, kb = error_text("Не удалось загрузить окружение.", retry_callback=f"env:{project_uuid}:{env_name}")
        await cb.message.edit_text(text, reply_markup=kb); return
    env_label = env_detail.name if env_detail else env_name
    lines = [f"\U0001f3d7 **{project.name}** \u2192 \U0001f30d **{env_label}**"]
    apps = all_apps; services = all_services
    if not apps and not services:
        await cb.message.edit_text(f"\U0001f30d **{env_label}**\n\n{empty_state(apps)}",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="\u2b05\ufe0f Назад к проекту", callback_data=f"proj:{project_uuid}")],
                [InlineKeyboardButton(text="\U0001f3e0 Главное меню", callback_data="menu:main")],
            ]))
        return
    lines.append(f"\n\U0001f4e6 **Приложения:" + "**" if apps else f"\n\U0001f4e6 Приложения: _нет_")
    kb_rows = []
    for app in apps:
        em = status_emoji(app.status)
        lines.append(f"{em} {app.name[:25]}")
        kb_rows.append([InlineKeyboardButton(text=f"{em} {app.name[:25]}", callback_data=f"res:application:{app.uuid}")])
    if services:
        lines.append(f"\n\U0001f9e9 **Сервисы (Compose):**")
        for srv in services:
            em = status_emoji(srv.status)
            lines.append(f"{em} {srv.name[:25]}")
            kb_rows.append([InlineKeyboardButton(text=f"{em} {srv.name[:25]}", callback_data=f"res:service:{srv.uuid}")])
    kb_rows.append([InlineKeyboardButton(text="\u2b05\ufe0f К проекту", callback_data=f"proj:{project_uuid}")])
    kb_rows.append([InlineKeyboardButton(text="\U0001f3e0 Главное меню", callback_data="menu:main")])
    await cb.message.edit_text("\n".join(lines), reply_markup=InlineKeyboardMarkup(inline_keyboard=kb_rows))

@router.callback_query(F.data.startswith("res:"))
async def resource_detail(cb: CallbackQuery, db_user: User) -> None:
    """Show resource detail card with action buttons."""
    parts = cb.data.split(":", 2)
    if len(parts) < 3:
        await cb.answer("❌ Некорректные данные", show_alert=True); return
    res_type, res_uuid = parts[1], parts[2]
    await cb.answer()
    await cb.message.edit_text(loading_text("Загружаю информацию"))
    try:
        if res_type == "application":
            app = await coolify.get_application(res_uuid)
            deploys = await coolify.list_deployments()
            latest = None
            for d in deploys:
                if d.application_uuid == res_uuid: latest = d; break
            em = status_emoji(app.status)
            lines = [f"\U0001f4e6 **{app.name}**", f"Статус: {em} **{app.status or 'неизвестен'}**", f"`{app.uuid[:8]}...`"]
            if app.fqdn: lines.append(f"\U0001f310 [{app.fqdn}](https://{app.fqdn})")
            if app.description: lines.append(f"\n_{app.description[:300]}_")
            if app.git_repository:
                lines.append(f"\n\U0001f4c2 `{app.git_repository}`")
                if app.git_branch: lines.append(f"\U0001f33f `{app.git_branch}`")
            if app.docker_registry_image_name:
                lines.append(f"\U0001f433 `{app.docker_registry_image_name}:{app.docker_registry_image_tag or 'latest'}`")
            if latest:
                from bot.utils.formatting import fmt_relative_time
                lines.append(f"\n\U0001f504 Последний деплой: **{latest.status}**")
                if latest.finished_at: lines.append(f"\u23f1 {fmt_relative_time(latest.finished_at)}")
        elif res_type == "service":
            srv = await coolify.get_service(res_uuid)
            em = status_emoji(srv.status)
            lines = [f"\U0001f9e9 **{srv.name}**", f"Статус: {em} **{srv.status or 'неизвестен'}**", f"`{srv.uuid[:8]}...`"]
            if srv.description: lines.append(f"\n_{srv.description[:300]}_")
            if srv.service_type: lines.append(f"\n\U0001f4cb Тип: `{srv.service_type}`")
            if srv.docker_compose_raw:
                svc_names = re.findall(r'^\s+([a-zA-Z0-9_-]+):', srv.docker_compose_raw, re.MULTILINE)
                if svc_names: lines.append(f"\n\U0001f433 **Контейнеры ({len(svc_names)}):**")
                for sn in svc_names: lines.append(f"  \u2022 `{sn}`")
        else:
            lines = [f"\U0001f4ce Ресурс (`{res_uuid[:8]}...`)\n\nТип: {res_type}"]
        lines.append(f"\n\n**Действия:**")
        kb_rows = [
            [InlineKeyboardButton(text=f"\u25b6\ufe0f Start", callback_data=f"act_r:{res_type}:{res_uuid}:start"),
             InlineKeyboardButton(text=f"\u23f9 Stop", callback_data=f"act_r:{res_type}:{res_uuid}:stop")],
            [InlineKeyboardButton(text=f"\U0001f504 Restart", callback_data=f"act_r:{res_type}:{res_uuid}:restart")],
            [InlineKeyboardButton(text=f"\U0001f4cb Logs", callback_data=f"log_r:{res_type}:{res_uuid}")],
            [InlineKeyboardButton(text="\u2b05\ufe0f Назад", callback_data="menu:projects")],
            [InlineKeyboardButton(text="\U0001f3e0 Главное меню", callback_data="menu:main")],
        ]
        await cb.message.edit_text("\n".join(lines), reply_markup=InlineKeyboardMarkup(inline_keyboard=kb_rows))
    except CoolifyClientError as exc:
        text, kb = error_text(exc.message, code=str(exc.status), retry_callback=f"res:{res_type}:{res_uuid}")
        await cb.message.edit_text(text, reply_markup=kb)
    except Exception:
        log.exception("Error loading resource %s/%s", res_type, res_uuid)
        text, kb = error_text("Не удалось загрузить информацию о ресурсе.", retry_callback=f"res:{res_type}:{res_uuid}")
        await cb.message.edit_text(text, reply_markup=kb)

@router.callback_query(F.data.startswith("env_refr:"))
async def refresh_environments(cb: CallbackQuery, db_user: User) -> None:
    project_uuid = cb.data.split(":", 1)[1]
    _projects_cache.pop("projects", None)
    _apps_all_cache.pop("app_list", None)
    _services_cache.pop("service_list", None)
    await cb.answer("\U0001f504 Обновлено")
    await project_detail(cb, db_user)

@router.callback_query(F.data == "menu:projects_go")
async def menu_projects_go(cb: CallbackQuery, db_user: User) -> None:
    await cb.answer(); await cmd_projects(cb.message, db_user)

@router.callback_query(F.data == "menu:projects")
async def menu_back_projects(cb: CallbackQuery, db_user: User) -> None:
    await cb.answer(); await cmd_projects(cb.message, db_user)