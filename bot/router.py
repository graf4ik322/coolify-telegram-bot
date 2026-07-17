"""Router registration — import and include all handlers."""

from aiogram import Dispatcher

from bot.handlers import actions, apps, deploy, logs, servers, start, subscribe


def register_routers(dp: Dispatcher) -> None:
    """Register all handler routers with the dispatcher."""
    dp.include_router(start.router)
    dp.include_router(apps.router)
    dp.include_router(servers.router)
    dp.include_router(deploy.router)
    dp.include_router(logs.router)
    dp.include_router(actions.router)
    dp.include_router(subscribe.router)
