"""/logs handler — fetch and display application logs."""

from __future__ import annotations

import logging

from aiogram import F, Router
from aiogram.filters import Command, CommandObject
from aiogram.types import CallbackQuery, FSInputFile, InlineKeyboardButton, InlineKeyboardMarkup, Message

from bot.config import settings
from bot.db.models import User
from bot.services.coolify import CoolifyClientError, coolify
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

    app_uuid = await _resolve_app(arg)
    if not app_uuid:
        await message.answer(f"❌ Приложение «{arg}» не найдено.")
        return

    try:
        logs = await coolify.get_application_logs(app_uuid, lines=settings.logs_default_lines)
    except CoolifyClientError as exc:
        await message.answer(f"❌ Ошибка получения логов: {exc.message}")
        return
    except Exception:
        log.exception("Error fetching logs for %s", arg)
        await message.answer("❌ Не удалось получить логи.")
        return

    msg_text, file_content = format_logs(logs)
    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🔙 Назад", callback_data="back:apps")],
        ]
    )

    if file_content:
        # Send as file
        await message.answer(msg_text, reply_markup=kb)
        path = f"/tmp/{app_uuid}_logs.txt"
        with open(path, "w") as f:
            f.write(file_content)
        await message.answer_document(
            FSInputFile(path, filename=f"{app_uuid}_logs.txt"),
            caption=f"📋 Полные логи ({len(file_content)} символов)",
        )
    else:
        await message.answer(msg_text, reply_markup=kb)


@router.callback_query(F.data.startswith("logs:"))
async def logs_callback(cb: CallbackQuery, db_user: User) -> None:
    """Handle logs callback from app card."""
    parts = cb.data.split(":", 2)
    if len(parts) < 2:
        await cb.answer("Некорректный запрос", show_alert=True)
        return
    uuid = parts[1]
    name = parts[2] if len(parts) > 2 else uuid[:8]

    try:
        logs = await coolify.get_application_logs(uuid, lines=settings.logs_default_lines)
    except CoolifyClientError as exc:
        await cb.message.edit_text(f"❌ Ошибка получения логов: {exc.message}")
        return

    msg_text, file_content = format_logs(logs)
    await cb.message.edit_text(msg_text)
    if file_content:
        path = f"/tmp/{uuid}_logs.txt"
        with open(path, "w") as f:
            f.write(file_content)
        await cb.message.answer_document(
            FSInputFile(path, filename=f"{uuid}_logs.txt"),
            caption=f"📋 Полные логи ({name})",
        )
    await cb.answer()


async def _resolve_app(name_or_uuid: str) -> str | None:
    """Resolve app name or UUID to a UUID."""
    # Try direct UUID lookup
    try:
        app = await coolify.get_application(name_or_uuid)
        return app.uuid
    except CoolifyClientError:
        pass

    # Search by name
    try:
        apps = await coolify.list_applications()
        for app in apps:
            if app.name.lower() == name_or_uuid.lower():
                return app.uuid
    except CoolifyClientError:
        pass

    return None
