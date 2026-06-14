import asyncio
import logging
from collections import deque
from typing import Deque, Iterable, Optional
from aiogram import Bot
_TG_LIMIT = 3500

class TelegramLogHandler(logging.Handler):

    def __init__(self, level: int=logging.INFO) -> None:
        super().__init__(level)
        self._buffer: Deque[str] = deque()
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._task: Optional[asyncio.Task] = None
        self._bot: Optional[Bot] = None
        self._chat_ids: list[int] = []
        self._stopped = False

    def attach(self, bot: Bot, chat_ids: Iterable[int], loop: asyncio.AbstractEventLoop) -> None:
        self._bot = bot
        self._chat_ids = list(chat_ids)
        self._loop = loop
        if self._task is None or self._task.done():
            self._task = loop.create_task(self._run())

    def update_chat_ids(self, chat_ids: Iterable[int]) -> None:
        self._chat_ids = list(chat_ids)

    def stop(self) -> None:
        self._stopped = True
        if self._task is not None:
            self._task.cancel()

    def emit(self, record: logging.LogRecord) -> None:
        try:
            msg = self.format(record)
        except Exception:
            return
        self._buffer.append(msg)

    async def _run(self) -> None:
        while not self._stopped:
            try:
                await asyncio.sleep(2.0)
                if not self._buffer or not self._bot or (not self._chat_ids):
                    continue
                lines: list[str] = []
                while self._buffer:
                    lines.append(self._buffer.popleft())
                chunks = self._chunk('\n'.join(lines))
                for chunk in chunks:
                    text = f'<pre>{self._escape(chunk)}</pre>'
                    for chat_id in list(self._chat_ids):
                        try:
                            await self._bot.send_message(chat_id, text, disable_notification=True)
                        except Exception:
                            pass
            except asyncio.CancelledError:
                break
            except Exception:
                pass

    @staticmethod
    def _escape(text: str) -> str:
        return text.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')

    @staticmethod
    def _chunk(text: str) -> list[str]:
        if len(text) <= _TG_LIMIT:
            return [text] if text else []
        out: list[str] = []
        for i in range(0, len(text), _TG_LIMIT):
            out.append(text[i:i + _TG_LIMIT])
        return out