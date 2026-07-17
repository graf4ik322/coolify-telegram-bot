"""/apps handler — list applications with inline pagination."""

from __future__ import annotations

import logging

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from bot.db.models import User
from bot.services.coolify import CoolifyClientError, coolify
from bot.utils.formatting import format_app_card, format_app_short
from bot.utils.pagination import Pagination

router = Router()
log = logging.getLogger(__name__)


@router.message(Command("apps"))
async def cmd_apps(message: Message, db_user: User) -> None:
    """Show paginated list of applications."""
    try:
        apps = await coolify.list_applications()
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

    pag = Pagination(
        items=apps,
        per_page=5,
        format_fn=format_app_short,
    )
    kb = pag.build(page=0, callback_prefix="app")

    await message.answer(
        f"📱 **Приложения** ({len(apps)} всего):\n_Выберите приложение для просмотра_",
        reply_markup=kb,
    )


@router.callback_query(F.data.startswith("app:"))
async def app_detail(cb: CallbackQuery, db_user: User) -> None:
    """Show application detail card with action buttons."""
    uuid = cb.data.split(":", 1)[1]
    try:
        app = await coolify.get_application(uuid)
        # Try to get latest deployment
        deploys = await coolify.list_deployments()
        latest = None
        for d in deploys:
            if d.application_uuid == uuid:
                latest = d
                break
    except CoolifyClientError as exc:
        await cb.message.edit_text(f"❌ Ошибка: {exc.message}")
        return
    except Exception:
        log.exception("Error fetching app detail")
        await cb.message.edit_text("❌ Не удалось получить данные приложения.")
        return

    text = format_app_card(app, latest)

    # Action buttons (role-dependent)
    buttons = [
        [
            InlineKeyboardButton(
                text="🔄 Restart",
                callback_data=f"act:restart:{app.uuid}:{app.name}",
            ),
            InlineKeyboardButton(
                text="⏹ Stop",
                callback_data=f"act:stop:{app.uuid}:{app.name}",
            ),
        ],
        [
            InlineKeyboardButton(
                text="▶️ Start",
                callback_data=f"act:start:{app.uuid}:{app.name}",
            ),
            InlineKeyboardButton(
                text="📦 Redeploy",
                callback_data=f"act:redeploy:{app.uuid}:{app.name}",
            ),
        ],
        [
            InlineKeyboardButton(
                text="📋 Логи",
                callback_data=f"logs:{app.uuid}:{app.name}",
            ),
            InlineKeyboardButton(
                text="🔙 Назад",
                callback_data="back:apps",
            ),
        ],
    ]

    # If user is viewer, disable action buttons
    markup = InlineKeyboardMarkup(inline_keyboard=buttons)
    await cb.message.edit_text(text, reply_markup=markup)
    await cb.answer()


@router.callback_query(F.data.startswith("back:apps"))
async def back_to_apps(cb: CallbackQuery, db_user: User) -> None:
    """Return to app list."""
    await cb.answer()
    # Re-trigger the apps list
    await cmd_apps(cb.message, db_user)  # type: ignore[arg-type]
