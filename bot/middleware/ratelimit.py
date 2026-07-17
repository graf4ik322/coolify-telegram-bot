"""Rate-limit middleware.

Uses Redis when available, falls back to in-memory dict.
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections import defaultdict
from typing import Any, Awaitable, Callable

from aiogram import BaseMiddleware
from aiogram.types import Message, TelegramObject, Update

from bot.config import settings

log = logging.getLogger(__name__)

# ── In-memory fallback ───────────────────────────────────────────────────────

_memory_store: dict[int, list[float]] = defaultdict(list)
_lock = asyncio.Lock()


async def _check_memory(uid: int, max_reqs: int, window: float) -> bool:
    async with _lock:
        now = time.time()
        window_start = now - window
        ts_list = _memory_store[uid]
        # Keep only entries within the window
        _memory_store[uid] = [t for t in ts_list if t > window_start]
        if len(_memory_store[uid]) >= max_reqs:
            return False
        _memory_store[uid].append(now)
        return True


class RateLimitMiddleware(BaseMiddleware):
    """Simple sliding-window rate limiter."""

    def __init__(
        self,
        max_requests: int = 10,
        window_seconds: float = 60.0,
    ) -> None:
        self.max_requests = max_requests
        self.window_seconds = window_seconds

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        if isinstance(event, Update):
            uid = self._extract_user_id(event)
            if uid is None:
                return await handler(event, data)

            allowed = await _check_memory(uid, self.max_requests, self.window_seconds)
            if not allowed:
                log.warning("Rate limit hit for user %d", uid)
                # Optionally notify user
                if event.message:
                    await event.message.reply(
                        f"⏳ Слишком много запросов. "
                        f"Лимит: {self.max_requests} запросов в {int(self.window_seconds)} сек."
                    )
                return None  # Drop the update

        return await handler(event, data)

    @staticmethod
    def _extract_user_id(event: Update) -> int | None:
        if event.message:
            return event.message.from_user.id if event.message.from_user else None
        if event.callback_query:
            return event.callback_query.from_user.id if event.callback_query.from_user else None
        return None
