"""Shared utility to resolve application name/UUID to a UUID.

Used across multiple handlers to avoid code duplication.
"""

from __future__ import annotations

import asyncio
import logging

from bot.services.coolify import CoolifyClientError, coolify

log = logging.getLogger(__name__)


async def resolve_app(name_or_uuid: str) -> str | None:
    """Resolve app name or UUID to a UUID.

    First tries direct UUID lookup (fast path), then searches by name.
    Each call has an 8-second timeout to avoid blocking.
    """
    # Fast path — try direct UUID lookup
    try:
        async with asyncio.timeout(8):
            app = await coolify.get_application(name_or_uuid)
            return app.uuid
    except (CoolifyClientError, TimeoutError, asyncio.CancelledError):
        pass

    # Slow path — search by name
    try:
        async with asyncio.timeout(8):
            apps = await coolify.list_applications()
            for app in apps:
                if app.name.lower() == name_or_uuid.lower():
                    return app.uuid
    except (CoolifyClientError, TimeoutError, asyncio.CancelledError):
        pass

    return None
