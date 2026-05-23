from typing import Any, Awaitable, Callable

from aiogram import BaseMiddleware
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message, TelegramObject

from src.configs.config import Config


class AuthMiddleware(BaseMiddleware):
    def __init__(self, config: Config) -> None:
        self._config = config

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        user = data.get("event_from_user")
        if user is None:
            return await handler(event, data)

        if self._config.is_authorized(user.id):
            return await handler(event, data)

        if isinstance(event, Message):
            text = (event.text or "").strip()
            state: FSMContext | None = data.get("state")
            current_state = await state.get_state() if state else None
            if text.startswith("/start") or current_state is not None:
                return await handler(event, data)
            await event.answer("Вы не авторизованы. Введите /start.")
            return None

        if isinstance(event, CallbackQuery):
            await event.answer("Нет доступа", show_alert=True)
            return None

        return None


class DependenciesMiddleware(BaseMiddleware):
    def __init__(self, **deps: Any) -> None:
        self._deps = deps

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        data.update(self._deps)
        return await handler(event, data)
