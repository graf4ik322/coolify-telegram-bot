"""Authentication and authorisation middleware.

Every update is checked against the whitelist. Unknown users are silently
ignored (no reply to avoid leaking bot existence).
"""

from __future__ import annotations

import logging
from typing import Any, Awaitable, Callable

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject, Update

from bot.config import settings
from bot.db.repository import get_user, upsert_user

log = logging.getLogger(__name__)


class AuthMiddleware(BaseMiddleware):
    """Reject updates from users not in the whitelist.

    Falls back to ``ADMIN_IDS`` from config: if an admin ID from the env
    is not yet in the database, they are auto-provisioned as ``admin`` role.
    """

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        if isinstance(event, Update):
            user_id = self._extract_user_id(event)
            if user_id is None:
                return await handler(event, data)

            user = await get_user(user_id)
            if user is None:
                # Not in DB — check ADMIN_IDS fallback
                if user_id in settings.admin_telegram_ids:
                    user = await upsert_user(user_id, role="admin")
                    log.info("Auto-provisioned admin user %d from ADMIN_IDS", user_id)
                else:
                    log.info("Rejected unknown user: %d", user_id)
                    return None

            data["db_user"] = user

        return await handler(event, data)

    @staticmethod
    def _extract_user_id(event: Update) -> int | None:
        if event.message:
            return event.message.from_user.id if event.message.from_user else None
        if event.callback_query:
            return event.callback_query.from_user.id if event.callback_query.from_user else None
        return None
