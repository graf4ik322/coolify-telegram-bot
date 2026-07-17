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


# ── Command: /logs ───────────────────────────────────────────────────────────

@router.message(Command("logs"))
async def cmd_logs(message: Message, db_user: User, command: CommandObject) -> None:
    """Fetch logs for an application.

    Usage: ``/logs <app_name_or_uuid>``
    """
    arg = command.args
    if not arg:
        await message.answer("❌ Укажите имя или UUID приложения.\\nПример: `/logs my-app`")
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
        await msg.edit_text(msg_text or "📭 Логи пусты.", reply_markup=nav_back_main())


# ── Resource logs callback (from projects handler) ───────────────────────────

@router.callback_query(F.data.startswith("log_r:"))
async def resource_logs(cb: CallbackQuery, db_user: User) -> None:
    """Show logs for a resource from the projects handler.

    Format: log_r:<type>:<uuid>
    """
    parts = cb.data.split(":", 2)
    if len(parts) < 3:
        await cb.answer("❌ Некорректные данные", show_alert=True)
        return

    res_type, res_uuid = parts[1], parts[2]

    await cb.answer()
    await cb.message.edit_text(loading_text("Загружаю логи"))

    try:
        if res_type == "application":
            logs_text = await coolify.get_application_logs(res_uuid, lines=settings.logs_default_lines)
            msg_text, file_content = format_logs(logs_text)
        elif res_type == "service":
            # Services don't have a direct logs endpoint in Coolify API v1
            # Show the docker-compose config and info about per-container logs
            srv = await coolify.get_service(res_uuid)
            msg_text = (
                f"🧩 **{srv.name}** — Логи\\n\\n"
                f"Coolify API v1 не предоставляет endpoint для логов сервисов (Docker Compose).\\n\\n"
                f"**Обходной путь:**\\n"
                f"1. Проверьте контейнеры напрямую на сервере:\\n"
                f"   `docker logs <container_name>`\\n"
                f"2. Или откройте GUI Coolify в браузере.\\n\\n"
                f"**Контейнеры сервиса:**\\n"
            )
            file_content = None
            if srv.docker_compose_raw:
                import re
                svc_names = re.findall(r'^\s+([a-zA-Z0-9_-]+):', srv.docker_compose_raw, re.MULTILINE)
                if svc_names:
                    for sn in svc_names:
                        msg_text += f"\\n• `{srv.name}_{sn}_1` — `docker logs {srv.name}_{sn}_1`"
                else:
                    msg_text += "\\n_Не удалось распарсить docker-compose_"
            else:
                msg_text += "\\n_Нет docker-compose данных_"
        else:
            msg_text = f"❌ Логи для типа {res_type} не поддерживаются."
            file_content = None
    except CoolifyClientError as exc:
        text, kb = error_text(exc.message, code=str(exc.status))
        await cb.message.edit_text(text, reply_markup=kb)
        return
    except Exception:
        log.exception("Error fetching logs for %s/%s", res_type, res_uuid)
        text, kb = error_text("Не удалось получить логи.")
        await cb.message.edit_text(text, reply_markup=kb)
        return

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text="🔙 К ресурсу",
            callback_data=f"res:{res_type}:{res_uuid}",
        )],
        [InlineKeyboardButton(text="🏠 Главное меню", callback_data="menu:main")],
    ])

    await cb.message.edit_text(msg_text, reply_markup=kb)


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
