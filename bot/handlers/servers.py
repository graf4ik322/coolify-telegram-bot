"""/servers handler — list servers and their health."""

from __future__ import annotations

import logging

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from bot.db.models import User
from bot.services.coolify import CoolifyClientError, coolify
from bot.utils.formatting import format_server_short, status_emoji
from bot.utils.states import empty_state, error_text, loading_text, nav_main_only

router = Router()
log = logging.getLogger(__name__)


@router.message(Command("servers"))
async def cmd_servers(message: Message, db_user: User) -> None:
    """Show list of all servers."""
    msg = await message.answer(loading_text("Загружаю список серверов"))

    try:
        servers = await coolify.list_servers()
        health = await coolify.health()
    except CoolifyClientError as exc:
        text, kb = error_text(exc.message, code=str(exc.status), retry_callback="refresh:servers")
        await msg.edit_text(text, reply_markup=kb)
        return
    except Exception:
        log.exception("Error fetching servers")
        text, kb = error_text("Не удалось получить список серверов.", retry_callback="refresh:servers")
        await msg.edit_text(text, reply_markup=kb)
        return

    if not servers:
        await msg.edit_text(empty_state("servers"), reply_markup=nav_main_only())
        return

    lines = [f"🖥 **Серверы** ({len(servers)}):\n"]
    for srv in servers:
        lines.append(format_server_short(srv))
    lines.append(f"\n🩺 **Health:** {status_emoji(health.status)} {health.status}")

    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🔄 Обновить", callback_data="refresh:servers")],
        ]
    )
    await message.answer("\n".join(lines), reply_markup=kb)


@router.callback_query(F.data == "refresh:servers")
async def refresh_servers(cb: CallbackQuery, db_user: User) -> None:
    """Refresh server list."""
    await cb.answer("Обновляю...")
    # Re-run command logic
    await cmd_servers(cb.message, db_user)  # type: ignore[arg-type]
