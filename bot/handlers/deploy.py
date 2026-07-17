"""/deployments, /status, /projects handlers."""

from __future__ import annotations

import logging

from aiogram import Router
from aiogram.filters import Command, CommandObject
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from bot.db.models import User
from bot.services.coolify import CoolifyClientError, coolify
from bot.utils.app_resolver import resolve_app
from bot.utils.formatting import format_app_card, fmt_deployment_status, fmt_relative_time
from bot.utils.states import empty_state, error_text, loading_text, nav_back_main, nav_main_only

router = Router()
log = logging.getLogger(__name__)


@router.message(Command("status"))
async def cmd_status(message: Message, db_user: User, command: CommandObject) -> None:
    """Show application detail card.

    Usage: ``/status <app_name_or_uuid>``
    """
    arg = command.args
    if not arg:
        await message.answer("❌ Укажите имя или UUID приложения.\nПример: `/status my-app`")
        return

    msg = await message.answer(loading_text("Загружаю статус"))

    try:
        # Try resolving via shared utility
        app_uuid = await resolve_app(arg)
        if not app_uuid:
            await msg.edit_text(f"❌ Приложение «{arg}» не найдено.", reply_markup=nav_back_main())
            return
        app = await coolify.get_application(app_uuid)

        deploys = await coolify.list_deployments()
        latest = None
        for d in deploys:
            if d.application_uuid == app_uuid:
                latest = d
                break

        text = format_app_card(app, latest)
        await msg.edit_text(text)
    except CoolifyClientError as exc:
        await msg.edit_text(f"❌ Ошибка Coolify API: {exc.message}")
    except Exception:
        log.exception("Error in status command")
        await msg.edit_text("❌ Не удалось получить статус приложения.")


@router.message(Command("deployments"))
async def cmd_deployments(message: Message, db_user: User) -> None:
    """List active/recent deployments."""
    msg = await message.answer(loading_text("Загружаю деплои"))

    try:
        deploys = await coolify.list_deployments()
    except CoolifyClientError as exc:
        text, kb = error_text(exc.message, code=str(exc.status))
        await msg.edit_text(text, reply_markup=kb)
        return
    except Exception:
        log.exception("Error listing deployments")
        text, kb = error_text("Не удалось получить список деплоев.")
        await msg.edit_text(text, reply_markup=kb)
        return

    if not deploys:
        await msg.edit_text(
            empty_state("deployments"),
            reply_markup=nav_back_main(),
        )
        return

    lines = ["📦 **Деплои:**\n"]
    for d in deploys:
        lines.append(fmt_deployment_status(d))
        lines.append("")

    await msg.edit_text(
        "\n".join(lines),
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="🔄 Обновить", callback_data="deploy:refresh")],
                [InlineKeyboardButton(text="🏠 Главное меню", callback_data="menu:main")],
            ]
        ),
    )


async def _show_deployments(cb: CallbackQuery, db_user: User) -> None:
    """Show all deployments (called from main menu callback)."""
    await cb.answer()
    await cb.message.edit_text(loading_text("Загружаю деплои"))

    try:
        deploys = await coolify.list_deployments()
    except CoolifyClientError as exc:
        text, kb = error_text(exc.message, code=str(exc.status), retry_callback="menu:deployments_go")
        await cb.message.edit_text(text, reply_markup=kb)
        return
    except Exception:
        log.exception("Error listing deployments")
        text, kb = error_text("Не удалось получить список деплоев.", retry_callback="menu:deployments_go")
        await cb.message.edit_text(text, reply_markup=kb)
        return

    if not deploys:
        await cb.message.edit_text(empty_state("deployments"), reply_markup=nav_back_main())
        return

    lines = ["📦 **Последние деплои:**\n"]
    for d in deploys[-10:]:
        em = status_emoji(d.status)
        name = d.application_uuid[:8] if d.application_uuid else "?"
        ts = fmt_relative_time(d.finished_at) if d.finished_at else ""
        lines.append(f"{em} `{name}` — {d.status or 'N/A'} {ts}")

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔄 Обновить", callback_data="deploy:refresh")],
        [InlineKeyboardButton(text="🏠 Главное меню", callback_data="menu:main")],
    ])
    await cb.message.edit_text("\n".join(lines), reply_markup=kb)


@router.callback_query(lambda c: c.data == "deploy:refresh")
async def deploy_refresh(cb: CallbackQuery, db_user: User) -> None:
    """Refresh deployment list (live update via editMessageText)."""
    try:
        deploys = await coolify.list_deployments()
    except CoolifyClientError as exc:
        text, kb = error_text(exc.message, code=str(exc.status))
        await cb.message.edit_text(text, reply_markup=kb)
        await cb.answer()
        return

    if not deploys:
        await cb.message.edit_text(
            empty_state("deployments"),
            reply_markup=nav_main_only(),
        )
        await cb.answer()
        return

    lines = ["📦 **Деплои (live):**\n"]
    for d in deploys:
        lines.append(fmt_deployment_status(d))
        lines.append("")

    # Show last refresh time
    from datetime import datetime
    lines.append(f"_Обновлено: {datetime.now().strftime('%H:%M:%S')}_")

    await cb.message.edit_text(
        "\n".join(lines),
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="🔄 Обновить", callback_data="deploy:refresh")],
                [InlineKeyboardButton(text="🏠 Главное меню", callback_data="menu:main")],
            ]
        ),
    )
    await cb.answer()


@router.message(Command("projects"))
async def cmd_projects(message: Message, db_user: User) -> None:
    """Show projects with their environments."""
    msg = await message.answer(loading_text("Загружаю проекты"))

    try:
        projects = await coolify._request("GET", "/projects")
        if not isinstance(projects, list):
            projects = []
    except CoolifyClientError as exc:
        text, kb = error_text(exc.message, code=str(exc.status))
        await msg.edit_text(text, reply_markup=kb)
        return

    if not projects:
        await msg.edit_text(empty_state("projects"), reply_markup=nav_back_main())
        return

    lines = ["📋 **Проекты:**\n"]
    for proj in projects:
        pid = proj.get("uuid", "")
        pname = proj.get("name", "?")
        lines.append(f"🏗 **{pname}** (`{pid[:8]}`)")

        try:
            envs = await coolify._request("GET", f"/projects/{pid}/environments")
            if isinstance(envs, list):
                for env in envs:
                    ename = env.get("name", "?")
                    lines.append(f"  🌍 {ename}")
        except CoolifyClientError:
            lines.append("  ⚠️ окружения недоступны")
        lines.append("")

    await msg.edit_text("\n".join(lines), reply_markup=nav_main_only())
