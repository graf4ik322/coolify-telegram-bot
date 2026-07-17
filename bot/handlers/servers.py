"""/servers handler — list servers and their health."""

from __future__ import annotations

import logging

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from bot.db.models import User
from bot.services.coolify import CoolifyClientError, coolify
from bot.utils.formatting import format_server_short, status_emoji

router = Router()
log = logging.getLogger(__name__)


@router.message(Command("servers"))
async def cmd_servers(message: Message, db_user: User) -> None:
    """Show list of all servers."""
    try:
        servers = await coolify.list_servers()
        health = await coolify.health()
    except CoolifyClientError as exc:
        await message.answer(f"❌ Ошибка Coolify API: {exc.message}")
        return
    except Exception:
        log.exception("Error fetching servers")
        await message.answer("❌ Не удалось получить список серверов.")
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
