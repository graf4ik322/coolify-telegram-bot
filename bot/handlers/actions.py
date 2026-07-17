"""Action handlers — start / stop / restart / redeploy with confirmation."""

from __future__ import annotations

import logging
import time

from aiogram import F, Router
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup

from bot.db.models import User
from bot.db.repository import log_action
from bot.services.coolify import CoolifyClientError, coolify
from bot.utils.formatting import status_emoji
from bot.utils.security import make_confirm_token, verify_confirm_token

router = Router()
log = logging.getLogger(__name__)

# ── Cooldown tracking (in-memory) ────────────────────────────────────────────
_cooldowns: dict[str, float] = {}  # resource_uuid -> timestamp


def _check_cooldown(resource_uuid: str, cooldown_sec: int = 120) -> bool:
    """Return True if action is allowed (not on cooldown)."""
    from bot.config import settings

    last = _cooldowns.get(resource_uuid)
    if last and (time.time() - last) < settings.restart_cooldown_seconds:
        return False
    _cooldowns[resource_uuid] = time.time()
    return True


# ── Available actions mapping ────────────────────────────────────────────────

_ACTIONS = {
    "restart": ("🔄", "перезапустить", coolify.restart_application),
    "stop": ("⏹", "остановить", coolify.stop_application),
    "start": ("▶️", "запустить", coolify.start_application),
    "redeploy": ("📦", "передеплоить", lambda u: coolify.deploy(tag=u)),
}

_ACTION_LABELS = {
    "restart": "🔄 Restart",
    "stop": "⏹ Stop",
    "start": "▶️ Start",
    "redeploy": "📦 Redeploy",
}


@router.callback_query(F.data.startswith("act:"))
async def action_request(cb: CallbackQuery, db_user: User) -> None:
    """Handle action button press — show confirmation dialog."""
    parts = cb.data.split(":", 3)
    if len(parts) < 4:
        await cb.answer("Некорректный запрос", show_alert=True)
        return

    action, uuid, name = parts[1], parts[2], parts[3]

    # Permission check
    if db_user.role not in ("operator", "admin"):
        await cb.answer("❌ У вас нет прав на это действие.", show_alert=True)
        return

    # Cooldown check for restart
    if action == "restart" and not _check_cooldown(uuid):
        await cb.answer(
            "⏳ Подождите 2 минуты перед повторным перезапуском.",
            show_alert=True,
        )
        return

    token = make_confirm_token(action, uuid, name)
    ttl = int(token.expires_at - time.time())

    text = (
        f"⚠️ **Подтвердите действие**\n\n"
        f"{_ACTION_LABELS.get(action, action)} **{name}**?\n"
        f"_Подтверждение истечёт через {ttl} сек._"
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
                InlineKeyboardButton(text="❌ Отмена", callback_data=f"cancel:{uuid}:{name}"),
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
        await cb.message.edit_text(
            "⌛ **Действие устарело.**\n"
            "Вернитесь в карточку приложения и повторите попытку.",
        )
        await cb.answer()
        return

    action_fn = _ACTIONS.get(token.action)
    if action_fn is None:
        await cb.answer(f"Неизвестное действие: {token.action}", show_alert=True)
        return

    _, label, fn = action_fn

    # Execute
    await cb.message.edit_text(
        f"⏳ Выполняю **{label}** **{token.resource_name}**..."
    )
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

    if status == "success":
        if token.action == "redeploy":
            dep_uuid = result.deployment_uuid if result else "?"
            await cb.message.edit_text(
                f"✅ **{label.title()}** **{token.resource_name}** запущен.\n"
                f"📋 Деплой: `{dep_uuid}`\n"
                f"`/deployments` для отслеживания статуса."
            )
        else:
            await cb.message.edit_text(
                f"✅ **{label.title()}** **{token.resource_name}** выполнен."
            )
    else:
        await cb.message.edit_text(
            f"❌ **{label.title()}** **{token.resource_name}** не удался.\n"
            f"`{err_msg}`\n\n"
            "_Проверьте Coolify панель для деталей._"
        )


@router.callback_query(F.data.startswith("cancel:"))
async def action_cancel(cb: CallbackQuery, db_user: User) -> None:
    """Cancel pending action."""
    parts = cb.data.split(":", 2)
    uuid = parts[1] if len(parts) > 1 else "?"
    name = parts[2] if len(parts) > 2 else "?"

    await cb.message.edit_text(f"❌ Действие над **{name}** отменено.")
    await cb.answer()
