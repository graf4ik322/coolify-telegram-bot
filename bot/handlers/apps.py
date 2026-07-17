"""/apps handler — list applications with inline pagination.

Uses single-message editing pattern: every navigation edits the same message
instead of sending new ones. Only the initial ``/apps`` command creates a new
message.
"""

from __future__ import annotations

import logging

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from bot.db.models import User
from bot.services.coolify import CoolifyClientError, coolify
from bot.utils.cache import TTLCache
from bot.utils.formatting import format_app_card, format_app_short
from bot.utils.pagination import Pagination

router = Router()
log = logging.getLogger(__name__)


# ── In-memory app cache (60s TTL for list views) ─────────────────────────────
_app_cache = TTLCache[str, list](default_ttl=60.0, max_size=10)


async def _get_apps() -> list:
    """Get cached app list or fetch fresh."""
    cached = _app_cache.get("app_list")
    if cached is not None:
        return cached
    apps = await coolify.list_applications()
    _app_cache["app_list"] = apps
    return apps


# ── /apps command ────────────────────────────────────────────────────────────

@router.message(Command("apps"))
async def cmd_apps(message: Message, db_user: User) -> None:
    """Show paginated list of applications (sends NEW message)."""
    try:
        apps = await _get_apps()
    except CoolifyClientError as exc:
        await message.answer(f"❌ Ошибка Coolify API: {exc.message}")
        return
    except Exception:
        log.exception("Unexpected error listing apps")
        await message.answer("❌ Не удалось получить список приложений.")
        return

    if not apps:
        await message.answer("📭 Нет приложений.")
        return

    pag = Pagination(items=apps, per_page=5, format_fn=format_app_short)
    kb = pag.build(page=0, callback_prefix="app")
    # Also add "Main Menu" button
    kb.inline_keyboard.append([
        InlineKeyboardButton(text="🏠 Главное меню", callback_data="menu:main"),
    ])

    await message.answer(
        f"📱 **Приложения** ({len(apps)} всего):\n_Выберите приложение для просмотра_",
        reply_markup=kb,
    )


# ── App detail card ──────────────────────────────────────────────────────────

@router.callback_query(F.data.startswith("app:"))
async def app_detail(cb: CallbackQuery, db_user: User) -> None:
    """Show application detail card with role-based action buttons."""
    uuid = cb.data.split(":", 1)[1]
    if not uuid:
        await cb.answer("Некорректный запрос", show_alert=True)
        return

    try:
        app = await coolify.get_application(uuid)
        deploys = await coolify.list_deployments()
        latest = next((d for d in deploys if d.application_uuid == uuid), None)
    except CoolifyClientError as exc:
        await cb.message.edit_text(f"❌ Ошибка: {exc.message}")
        await cb.answer()
        return
    except Exception:
        log.exception("Error fetching app detail")
        await cb.message.edit_text("❌ Не удалось получить данные приложения.")
        await cb.answer()
        return

    text = format_app_card(app, latest)

    # --- Role-based buttons ---
    buttons = []

    # Logs — available to all roles
    buttons.append([
        InlineKeyboardButton(text="📋 Логи", callback_data=f"logs:{uuid}"),
    ])

    # Dangerous actions — operator/admin only
    if db_user.role in ("operator", "admin"):
        buttons.append([
            InlineKeyboardButton(text="🔄 Restart", callback_data=f"act:restart:{uuid}"),
            InlineKeyboardButton(text="⏹ Stop", callback_data=f"act:stop:{uuid}"),
        ])
        buttons.append([
            InlineKeyboardButton(text="▶️ Start", callback_data=f"act:start:{uuid}"),
            InlineKeyboardButton(text="📦 Redeploy", callback_data=f"act:redeploy:{uuid}"),
        ])

    # Navigation — everyone
    buttons.append([
        InlineKeyboardButton(text="🔙 Назад", callback_data="back:app_list"),
        InlineKeyboardButton(text="🏠 Главное меню", callback_data="menu:main"),
    ])

    markup = InlineKeyboardMarkup(inline_keyboard=buttons)
    await cb.message.edit_text(text, reply_markup=markup)
    await cb.answer()


# ── Back to app list (single-message edit) ───────────────────────────────────

@router.callback_query(F.data == "back:app_list")
async def back_to_app_list(cb: CallbackQuery, db_user: User) -> None:
    """Return to app list (edits the SAME message)."""
    await cb.answer()
    try:
        apps = await _get_apps()
    except CoolifyClientError as exc:
        await cb.message.edit_text(f"❌ Ошибка: {exc.message}")
        return

    pag = Pagination(items=apps, per_page=5, format_fn=format_app_short)
    kb = pag.build(page=0, callback_prefix="app")
    kb.inline_keyboard.append([
        InlineKeyboardButton(text="🏠 Главное меню", callback_data="menu:main"),
    ])
    await cb.message.edit_text(
        f"📱 **Приложения** ({len(apps)} всего):\n_Выберите приложение для просмотра_",
        reply_markup=kb,
    )


# ── Back to app card from action ← used by actions.py ────────────────────────

@router.callback_query(F.data.startswith("back:app:"))
async def back_to_app_card(cb: CallbackQuery, db_user: User) -> None:
    """Return to app card from action result."""
    uuid = cb.data.split(":", 2)[2]
    if not uuid:
        await back_to_app_list(cb, db_user)
        return
    # Re-trigger app detail
    cb.data = f"app:{uuid}"
    await app_detail(cb, db_user)
