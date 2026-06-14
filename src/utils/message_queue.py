import asyncio
import logging
from dataclasses import dataclass
from typing import Awaitable, Callable, Optional
from src.starvellapi.exceptions import StarvellAPIError
from src.utils.rate_limiter import RateLimiter
log = logging.getLogger('message_queue')

@dataclass
class _Job:
    chat_id: str
    text: str
    future: asyncio.Future
SendFn = Callable[[str, str], Awaitable[object]]

class MessageQueue:

    def __init__(self, send_fn: SendFn, limiter: RateLimiter) -> None:
        self._send_fn = send_fn
        self._limiter = limiter
        self._queue: asyncio.Queue[_Job] = asyncio.Queue()
        self._task: Optional[asyncio.Task] = None
        self._running = False

    async def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._run())

    async def stop(self) -> None:
        self._running = False
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None

    def update_limiter(self, limiter: RateLimiter) -> None:
        self._limiter = limiter

    async def enqueue(self, chat_id: str, text: str) -> bool:
        loop = asyncio.get_running_loop()
        future: asyncio.Future = loop.create_future()
        await self._queue.put(_Job(chat_id=chat_id, text=text, future=future))
        try:
            return bool(await future)
        except Exception:
            return False

    async def _run(self) -> None:
        while self._running:
            try:
                job = await self._queue.get()
            except asyncio.CancelledError:
                break
            await self._limiter.acquire()
            try:
                await self._send_fn(job.chat_id, job.text)
                if not job.future.done():
                    job.future.set_result(True)
            except StarvellAPIError as e:
                log.warning('send в чат %s не прошёл: %s', job.chat_id, e)
                if not job.future.done():
                    job.future.set_result(False)
            except Exception:
                log.exception('send в чат %s упал', job.chat_id)
                if not job.future.done():
                    job.future.set_result(False)