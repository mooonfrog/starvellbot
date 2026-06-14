import asyncio
import collections
import time

class RateLimiter:

    def __init__(self, max_calls: int, period: float=60.0) -> None:
        if max_calls <= 0:
            raise ValueError('max_calls должен быть > 0')
        self._max_calls: int = int(max_calls)
        self._period: float = float(period)
        self._calls: collections.deque[float] = collections.deque()
        self._lock = asyncio.Lock()

    async def acquire(self) -> None:
        async with self._lock:
            while True:
                now = time.monotonic()
                while self._calls and now - self._calls[0] >= self._period:
                    self._calls.popleft()
                if len(self._calls) < self._max_calls:
                    self._calls.append(now)
                    return
                wait = self._period - (now - self._calls[0])
                await asyncio.sleep(max(wait, 0.05))