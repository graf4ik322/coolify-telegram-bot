"""/logs handler — fetch and display application logs."""

from __future__ import annotations

import logging
import os

from aiogram import F, Router
from aiogram.filters import Command, CommandObject
from aiogram.types import CallbackQuery, FSInputFile, InlineKeyboardButton, InlineKeyboardMarkup, Message

from bot.config import settings
from bot.db.models import User
from bot.services.coolify import CoolifyClientError, coolify
from bot.utils.app_resolver import resolve_app
from bot.utils.formatting import format_logs
from bot.utils.states import empty_state, error_text, loading_text, nav_back_main

router = Router()
log = logging.getLogger(__name__)


@router.message(Command("logs"))
async def cmd_logs(message: Message, db_user: User, command: CommandObject) -> None:
    """Fetch logs for an application.

    Usage: ``/logs <app_name_or_uuid>``
    """
    arg = command.args
    if not arg:
        await message.answer("❌ Укажите имя или UUID приложения.\nПример: `/logs my-app`")
        return

    app_uuid = await resolve_app(arg)
    if not app_uuid:
        await message.answer(f"❌ Приложение «{arg}» не найдено.", reply_markup=nav_back_main())
        return

    msg = await message.answer(loading_text("Загружаю логи"))

    try:
        logs = await coolify.get_application_logs(app_uuid, lines=settings.logs_default_lines)
    except CoolifyClientError as exc:
        text, kb = error_text(exc.message, code=str(exc.status))
        await msg.edit_text(text, reply_markup=kb)
        return
    except Exception:
        log.exception("Error fetching logs for %s", arg)
        text, kb = error_text("Не удалось получить логи.")
        await msg.edit_text(text, reply_markup=kb)
        return

    msg_text, file_content = format_logs(logs)

    if file_content:
        await msg.edit_text(msg_text)
        await _send_log_file(message, app_uuid, file_content)
    else:
        await msg.edit_text(msg_text, reply_markup=nav_back_main())


@router.callback_query(F.data.startswith("logs:"))
async def logs_callback(cb: CallbackQuery, db_user: User) -> None:
    """Handle logs callback from app card."""
    uuid = cb.data.split(":", 1)[1]
    if not uuid:
        await cb.answer("Некорректный запрос", show_alert=True)
        return

    try:
        logs = await coolify.get_application_logs(uuid, lines=settings.logs_default_lines)
    except CoolifyClientError as exc:
        text, kb = error_text(exc.message, code=str(exc.status))
        await cb.message.edit_text(text, reply_markup=kb)
        await cb.answer()
        return

    msg_text, file_content = format_logs(logs)
    await cb.message.edit_text(msg_text)
    if file_content:
        await _send_log_file(cb.message, uuid, file_content)
    await cb.answer()


async def _send_log_file(target: Message, uuid: str, content: str) -> None:
    """Send logs as a text file and clean up afterwards."""
    path = f"/tmp/{uuid}_logs.txt"
    import aiofiles

    try:
        async with aiofiles.open(path, "w") as f:
            await f.write(content)
        await target.answer_document(
            FSInputFile(path, filename=f"{uuid}_logs.txt"),
            caption=f"📋 Полные логи ({len(content)} символов)",
        )
    finally:
        try:
            os.unlink(path)
        except OSError:
            pass
