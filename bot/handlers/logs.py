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
        await message.answer(f"❌ Приложение «{arg}» не найдено.")
        return

    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🔙 Назад", callback_data="back:apps")],
        ]
    )

    try:
        logs = await coolify.get_application_logs(app_uuid, lines=settings.logs_default_lines)
    except CoolifyClientError as exc:
        await message.answer(f"❌ Ошибка получения логов: {exc.message}")
        return
    except Exception:
        log.exception("Error fetching logs for %s", arg)
        await message.answer("❌ Не удалось получить логи.", reply_markup=kb)
        return

    msg_text, file_content = format_logs(logs)

    if file_content:
        await message.answer(msg_text, reply_markup=kb)
        await _send_log_file(message, app_uuid, file_content)
    else:
        await message.answer(msg_text, reply_markup=kb)


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
        await cb.message.edit_text(f"❌ Ошибка получения логов: {exc.message}")
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
