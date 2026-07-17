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


async def _show_servers(target: Message | CallbackQuery, db_user: User) -> None:
    """Show server list, editing an existing message or sending new one."""
    import time

    # Determine how to send
    if isinstance(target, CallbackQuery):
        send = lambda t, **kw: target.message.edit_text(t, **kw)
    else:
        send = lambda t, **kw: target.answer(t, **kw)

    # Loading
    if isinstance(target, CallbackQuery):
        await send(loading_text("Загружаю список серверов"))
    else:
        target = await target.answer(loading_text("Загружаю список серверов"))
        send = lambda t, **kw: target.edit_text(t, **kw)

    try:
        servers = await coolify.list_servers()
        health = await coolify.health()
    except CoolifyClientError as exc:
        text, kb = error_text(exc.message, code=str(exc.status), retry_callback="refresh:servers")
        await send(text, reply_markup=kb)
        return
    except Exception:
        log.exception("Error fetching servers")
        text, kb = error_text("Не удалось получить список серверов.", retry_callback="refresh:servers")
        await send(text, reply_markup=kb)
        return

    if not servers:
        await send(empty_state("servers"), reply_markup=nav_main_only())
        return

    lines = [f"🖥 **Серверы** ({len(servers)}):\n"]
    for srv in servers:
        lines.append(format_server_short(srv))
    lines.append(f"\n🩺 **Health:** {status_emoji(health.status)} {health.status}")

    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🔄 Обновить", callback_data="refresh:servers")],
            [InlineKeyboardButton(text="🏠 Главное меню", callback_data="menu:main")],
        ]
    )
    await send("\n".join(lines), reply_markup=kb)


@router.message(Command("servers"))
async def cmd_servers(message: Message, db_user: User) -> None:
    """Show list of all servers."""
    await _show_servers(message, db_user)


@router.callback_query(F.data == "refresh:servers")
async def refresh_servers(cb: CallbackQuery, db_user: User) -> None:
    """Refresh server list."""
    await cb.answer("Обновляю...")
    # Re-run command logic
    await cmd_servers(cb.message, db_user)  # type: ignore[arg-type]
