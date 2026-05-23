import asyncio
import secrets
import time
from typing import Any

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

_TTL = 60.0


class ConfirmStore:
    def __init__(self) -> None:
        self._items: dict[str, tuple[float, dict[str, Any]]] = {}
        self._lock = asyncio.Lock()

    async def create(self, payload: dict[str, Any]) -> str:
        token = secrets.token_urlsafe(8)
        async with self._lock:
            self._items[token] = (time.monotonic(), payload)
            self._gc_locked()
        return token

    async def pop(self, token: str) -> dict[str, Any] | None:
        async with self._lock:
            self._gc_locked()
            entry = self._items.pop(token, None)
        if entry is None:
            return None
        return entry[1]

    def _gc_locked(self) -> None:
        now = time.monotonic()
        expired = [k for k, (t, _) in self._items.items() if now - t > _TTL]
        for k in expired:
            self._items.pop(k, None)


def confirm_kb(token: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ Подтвердить", callback_data=f"cf:y:{token}"),
                InlineKeyboardButton(text="❌ Отмена", callback_data=f"cf:n:{token}"),
            ]
        ]
    )
