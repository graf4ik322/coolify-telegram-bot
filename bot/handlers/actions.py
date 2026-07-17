"""Action handlers — start / stop / restart / redeploy with confirmation."""

from __future__ import annotations

import logging
import time
from collections import OrderedDict

from aiogram import F, Router
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup

from bot.config import settings
from bot.db.models import User
from bot.db.repository import log_action
from bot.services.coolify import CoolifyClientError, coolify
from bot.utils.cache import TTLCache
from bot.utils.security import make_confirm_token, verify_confirm_token

router = Router()
log = logging.getLogger(__name__)

# ── Cooldown tracking (auto-expiring, bounded) ──────────────────────────────
_cooldowns = TTLCache[str, float](default_ttl=300.0)  # auto-clean after 5 min


def _check_cooldown(resource_uuid: str) -> bool:
    """Return True if action is allowed (not on cooldown)."""
    last = _cooldowns.get(resource_uuid)
    if last and (time.time() - last) < settings.restart_cooldown_seconds:
        return False
    _cooldowns[resource_uuid] = time.time()
    return True


# ── Available actions mapping ────────────────────────────────────────────────

_ACTIONS = {
    "restart": ("\U0001f504", "\u043f\u0435\u0440\u0435\u0437\u0430\u043f\u0443\u0441\u0442\u0438\u0442\u044c", coolify.restart_application),
    "stop": ("\u23f9", "\u043e\u0441\u0442\u0430\u043d\u043e\u0432\u0438\u0442\u044c", coolify.stop_application),
    "start": ("\u25b6\ufe0f", "\u0437\u0430\u043f\u0443\u0441\u0442\u0438\u0442\u044c", coolify.start_application),
    "redeploy": ("\U0001f4e6", "\u043f\u0435\u0440\u0435\u0434\u0435\u043f\u043b\u043e\u0438\u0442\u044c", coolify.restart_application),
}

_ACTION_LABELS = {
    "restart": "\U0001f504 Restart",
    "stop": "\u23f9 Stop",
    "start": "\u25b6\ufe0f Start",
    "redeploy": "\U0001f4e6 Redeploy",
}

_ACTION_VERBS = {
    "restart": "\u0440\u0435\u0441\u0442\u0430\u0440\u0442",
    "stop": "\u043e\u0441\u0442\u0430\u043d\u043e\u0432\u043a\u0443",
    "start": "\u0437\u0430\u043f\u0443\u0441\u043a",
    "redeploy": "\u0440\u0435\u0434\u0435\u043f\u043b\u043e\u0439",
}

# Service action methods mapping
_SERVICE_ACTIONS = {
    "restart": coolify.restart_service,
    "stop": coolify.stop_service,
    "start": coolify.start_service,
}


@router.callback_query(F.data.startswith("act:"))
async def action_request(cb: CallbackQuery, db_user: User) -> None:
    """Handle action button press — show confirmation dialog."""
    parts = cb.data.split(":", 2)
    if len(parts) < 3:
        await cb.answer("Некорректный запрос", show_alert=True)
        return

    action = parts[1]
    uuid = parts[2]

    if not uuid:
        await cb.answer("Некорректный UUID", show_alert=True)
        return

    # Fetch app name from API for display
    try:
        app = await coolify.get_application(uuid)
        name = app.name
    except CoolifyClientError:
        name = uuid[:8]

    # Permission check
    if db_user.role not in ("operator", "admin"):
        await cb.answer("❌ У вас нет прав на это действие.", show_alert=True)
        return

    # Cooldown check for restart
    if action == "restart" and not _check_cooldown(uuid):
        remaining = int(settings.restart_cooldown_seconds - (time.time() - _cooldowns.get(uuid, 0)))
        await cb.answer(
            f"⏳ Подождите {max(1, remaining)} сек перед повторным перезапуском.",
            show_alert=True,
        )
        return

    token = make_confirm_token(action, uuid, name)
    ttl = int(token.expires_at - time.time())

    verb = _ACTION_VERBS.get(action, action)

    text = (
        f"⚠️ **Подтвердите действие**\n\n"
        f"{_ACTION_LABELS.get(action, action)} **{name}**?\n"
        f"Подтверждение истечёт через _{ttl} сек._"
    )

    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=f"✅ Подтвердить {_ACTION_LABELS.get(action, action)}",
                    callback_data=f"confirm:{token.value}",
                ),
            ],
            [
                InlineKeyboardButton(
                    text="❌ Отмена",
                    callback_data=f"cancel:{uuid}",
                ),
            ],
        ]
    )

    await cb.message.edit_text(text, reply_markup=kb)
    await cb.answer()


@router.callback_query(F.data.startswith("confirm:"))
async def action_confirm(cb: CallbackQuery, db_user: User) -> None:
    """Execute confirmed action."""
    token_str = cb.data[len("confirm:"):]
    token = verify_confirm_token(token_str)

    if token is None:
        # Stale — offer refresh
        parts = cb.data.split(":")
        kb = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="🔙 К карточке",
                        callback_data=f"back:app:{parts[-2] if len(parts) > 2 else ''}",
                    ),
                    InlineKeyboardButton(
                        text="🏠 Главное меню",
                        callback_data="menu:main",
                    ),
                ],
            ]
        )
        await cb.message.edit_text(
            "⏰ **Время подтверждения истекло.**\n"
            "Вернитесь в карточку приложения и повторите попытку.",
            reply_markup=kb,
        )
        await cb.answer()
        return

    action_fn = _ACTIONS.get(token.action)
    if action_fn is None:
        await cb.answer(f"Неизвестное действие: {token.action}", show_alert=True)
        return

    _, label, fn = action_fn

    await cb.message.edit_text(f"⏳ Выполняю **{label}** **{token.resource_name}**...")
    await cb.answer()

    try:
        result = await fn(token.resource_uuid)
        status = "success"
        err_msg = None
    except CoolifyClientError as exc:
        result = None
        status = "failed"
        err_msg = exc.message
    except Exception as exc:
        result = None
        status = "failed"
        err_msg = str(exc)
        log.exception("Action %s failed for %s", token.action, token.resource_uuid)

    # Audit
    await log_action(
        telegram_id=db_user.telegram_id,
        action=token.action,
        resource_type="application",
        resource_uuid=token.resource_uuid,
        resource_name=token.resource_name,
        status=status,
        error_message=err_msg,
    )

    # Navigation buttons after action
    nav_kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🔙 К карточке",
                    callback_data=f"back:app:{token.resource_uuid}",
                ),
                InlineKeyboardButton(
                    text="🏠 Главное меню",
                    callback_data="menu:main",
                ),
            ],
        ]
    )

    if status == "success":
        if token.action == "redeploy":
            dep_uuid = result.deployment_uuid if result and hasattr(result, "deployment_uuid") else "?"
            await cb.message.edit_text(
                f"✅ **{label.title()}** **{token.resource_name}** запущен.\n"
                f"📋 Деплой: `{dep_uuid}`",
                reply_markup=nav_kb,
            )
        else:
            await cb.message.edit_text(
                f"✅ **{label.title()}** **{token.resource_name}** выполнен.",
                reply_markup=nav_kb,
            )
    else:
        await cb.message.edit_text(
            f"❌ **{label.title()}** **{token.resource_name}** не удался.\n"
            f"`{err_msg}`\n\n"
            "_Проверьте Coolify панель для деталей._",
            reply_markup=nav_kb,
        )


@router.callback_query(F.data.startswith("cancel:"))
async def action_cancel(cb: CallbackQuery, db_user: User) -> None:
    """Cancel pending action and return to app card."""
    uuid = cb.data.split(":", 1)[1] if ":" in cb.data else ""

    nav_kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🔙 К карточке",
                    callback_data=f"back:app:{uuid}" if uuid else "noop",
                ),
                InlineKeyboardButton(
                    text="🏠 Главное меню",
                    callback_data="menu:main",
                ),
            ],
        ]
    )

    await cb.message.edit_text("❌ Действие отменено.", reply_markup=nav_kb)
    await cb.answer()


# ── Resource actions (from projects handler) ─────────────────────────────────

@router.callback_query(F.data.startswith("act_r:"))
async def resource_action_request(cb: CallbackQuery, db_user: User) -> None:
    """Handle action button from resource detail view.

    Format: act_r:<type>:<uuid>:<action>
    """
    parts = cb.data.split(":")
    if len(parts) < 4:
        await cb.answer("❌ Некорректные данные", show_alert=True)
        return

    res_type, res_uuid, action = parts[1], parts[2], parts[3]

    if action not in _ACTIONS:
        await cb.answer(f"❌ Неизвестное действие: {action}", show_alert=True)
        return

    # Check cooldown
    if not _check_cooldown(res_uuid):
        await cb.answer(
            f"⏳ Подождите {settings.restart_cooldown_seconds}с между действиями",
            show_alert=True,
        )
        return

    # Get resource name for display
    try:
        if res_type == "application":
            app = await coolify.get_application(res_uuid)
            res_name = app.name
        elif res_type == "service":
            srv = await coolify.get_service(res_uuid)
            res_name = srv.name
        else:
            res_name = res_uuid[:8]
    except CoolifyClientError:
        res_name = res_uuid[:8]

    label = _ACTION_LABELS.get(action, action)
    verb = _ACTION_VERBS.get(action, action)

    text = (
        f"⚠️ **Подтвердите действие**\n\n"
        f"Тип: **{res_type.upper()}**\n"
        f"Ресурс: **{res_name}**\n"
        f"Действие: {label}\n\n"
        f"Подтвердите {verb} ресурса?"
    )

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(
                text=f"✅ Да, {verb}",
                callback_data=f"act_cnf_r:{res_type}:{res_uuid}:{action}",
            ),
            InlineKeyboardButton(
                text="❌ Нет",
                callback_data=f"act_cnl_r:{res_type}:{res_uuid}",
            ),
        ],
    ])

    await cb.message.edit_text(text, reply_markup=kb)
    await cb.answer()


@router.callback_query(F.data.startswith("act_cnf_r:"))
async def resource_action_confirm(cb: CallbackQuery, db_user: User) -> None:
    """Execute confirmed resource action."""
    parts = cb.data.split(":")
    if len(parts) < 4:
        await cb.answer("❌ Некорректные данные", show_alert=True)
        return

    res_type, res_uuid, action = parts[1], parts[2], parts[3]
    emoji, _, _ = _ACTIONS.get(action, ("⚙️", "", None))

    await cb.answer()
    await cb.message.edit_text(f"{emoji} **Выполняю {action}...**")

    try:
        if res_type == "service" and action in _SERVICE_ACTIONS:
            result = await _SERVICE_ACTIONS[action](res_uuid)
        elif res_type == "application":
            _, _, method = _ACTIONS.get(action, (None, None, None))
            if method:
                result = await method(res_uuid)
            else:
                raise ValueError(f"Unknown action: {action}")
        else:
            # Fallback to application actions
            _, _, method = _ACTIONS.get(action, (None, None, None))
            if method:
                result = await method(res_uuid)
            else:
                raise ValueError(f"Unknown action: {action}")

        # Log action
        await log_action(
            telegram_id=cb.from_user.id,
            action=action,
            resource_type=res_type,
            resource_uuid=res_uuid,
            resource_name=res_uuid[:12],
            details=None,
        )

        verb = _ACTION_VERBS.get(action, action)
        await cb.message.edit_text(
            f"✅ **{verb.title()} выполнен**\n\n"
            f"Тип: {res_type.upper()}\n"
            f"Ресурс: `{res_uuid[:8]}...`\n"
            f"Результат: `{result}`",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(
                    text="🔙 К ресурсу",
                    callback_data=f"res:{res_type}:{res_uuid}",
                )],
                [InlineKeyboardButton(text="🏠 Главное меню", callback_data="menu:main")],
            ]),
        )

    except CoolifyClientError as exc:
        await cb.message.edit_text(
            f"❌ **Ошибка API**\n\n{exc.message}",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(
                    text="🔙 Повторить",
                    callback_data=f"act_r:{res_type}:{res_uuid}:{action}",
                )],
            ]),
        )
    except Exception:
        log.exception("Error executing %s on %s %s", action, res_type, res_uuid)
        await cb.message.edit_text(
            f"❌ **Не удалось выполнить {action}**",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(
                    text="🔙 К ресурсу",
                    callback_data=f"res:{res_type}:{res_uuid}",
                )],
            ]),
        )


@router.callback_query(F.data.startswith("act_cnl_r:"))
async def resource_action_cancel(cb: CallbackQuery, db_user: User) -> None:
    """Cancel pending resource action."""
    parts = cb.data.split(":")
    res_type = parts[1] if len(parts) > 1 else "application"
    res_uuid = parts[2] if len(parts) > 2 else ""

    await cb.message.edit_text(
        "❌ Действие отменено.",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(
                text="🔙 К ресурсу",
                callback_data=f"res:{res_type}:{res_uuid}",
            )],
            [InlineKeyboardButton(text="🏠 Главное меню", callback_data="menu:main")],
        ]),
    )
    await cb.answer()
