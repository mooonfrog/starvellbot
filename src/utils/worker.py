import asyncio
import logging
from datetime import datetime, timezone
from typing import Awaitable, Callable, Optional
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
from src.configs.config import Config
from src.starvellapi import Account, Chat
from src.starvellapi.enums import MessageType, OrderStatus
from src.starvellapi.exceptions import StarvellAPIError
from src.starvellapi.updater.events import BaseEvent, CommandInvokedEvent, NewMessageEvent, NewOrderEvent, NewReviewEvent, OrderStatusChangedEvent
from src.utils import short_order_id
from src.utils.console import BLUE, CYAN, GREEN, MAGENTA, RESET, YELLOW, log_block
from src.utils.message_queue import MessageQueue
from src.utils.rate_limiter import RateLimiter
log = logging.getLogger('worker')
EventListener = Callable[[BaseEvent], Awaitable[None]]

class Worker:

    def __init__(self, account: Account, config: Config) -> None:
        self.account: Account = account
        self.config: Config = config
        self.my_id: Optional[int] = None
        self._username_cache: dict[int, str] = {}
        self._buyer_to_chat: dict[int, str] = {}
        self._send_limiter = RateLimiter(max_calls=max(config.send_message_rate_per_minute, 1), period=60.0)
        self._tz = self._build_tz(config.timezone)
        self._listeners: list[EventListener] = []
        self._queue = MessageQueue(self._raw_send, self._send_limiter)
        self._thanks_sent: set[str] = set()

    async def start_queue(self) -> None:
        await self._queue.start()

    async def stop_queue(self) -> None:
        await self._queue.stop()

    async def _raw_send(self, chat_id: str, content: str) -> None:
        text = self.config.apply_watermark(content)
        await self.account.send_message(chat_id, text)

    def _render_chat_message(self, chat_id: str, author_username: str, author_id: int, content: str) -> None:
        title = f'{CYAN}Сообщение в чате:{RESET} {GREEN}{author_username}{RESET} {CYAN}(id: {author_id}){RESET}'
        lines = (content or '').splitlines() or ['']
        print('')
        log_block(log, logging.INFO, title, lines, frame_color=BLUE)

    def _render_new_order(self, order_id: str, status: str, price: float, buyer: str, created_at: str) -> None:
        title = f'{MAGENTA}Новый заказ:{RESET} {GREEN}{short_order_id(order_id)}{RESET}'
        print('')
        log_block(log, logging.INFO, title, [f'Покупатель: {buyer}', f'Сумма: {price:.2f}₽', f'Статус: {status}', f'Создан: {created_at}'], frame_color=GREEN)

    def _render_order_status(self, order_id: str, status: str, created_at: str) -> None:
        title = f'{YELLOW}Статус заказа:{RESET} {GREEN}{short_order_id(order_id)}{RESET}'
        print('')
        log_block(log, logging.INFO, title, [f'Новый статус: {status}', f'Создан: {created_at}'], frame_color=BLUE)

    def _render_review(self, review_id: str, author: str, rating: int, content: str) -> None:
        title = f'{MAGENTA}Новый отзыв:{RESET} {GREEN}{author}{RESET} {CYAN}({rating}★){RESET}'
        lines = [f'ID: {review_id}']
        body = (content or '').splitlines() or ['']
        lines.extend(body)
        print('')
        log_block(log, logging.INFO, title, lines, frame_color=CYAN)

    @staticmethod
    def _build_tz(name: str) -> ZoneInfo:
        try:
            return ZoneInfo(name)
        except ZoneInfoNotFoundError:
            log.warning('таймзона %r не нашлась, ставлю UTC', name)
            return ZoneInfo('UTC')

    def add_listener(self, listener: EventListener) -> None:
        self._listeners.append(listener)

    async def initialize(self) -> None:
        profile = await self.account.get_profile()
        self.my_id = profile.user.id
        self._username_cache[profile.user.id] = profile.user.username
        try:
            chats = await self.account.get_chats(limit=100)
            for chat in chats:
                self._cache_chat_participants(chat)
            if not self.config.greeted_chat_ids:
                for chat in chats:
                    self.config.greeted_chat_ids.append(chat.id)
                self.config.save()
        except StarvellAPIError as e:
            log.warning('кэш ников не прогрелся: %s', e)

        log.info('worker готов, аккаунт: %s (id=%s)', profile.user.username, profile.user.id)

    def reload_settings(self) -> None:
        self._send_limiter = RateLimiter(max_calls=max(self.config.send_message_rate_per_minute, 1), period=60.0)
        self._queue.update_limiter(self._send_limiter)
        self._tz = self._build_tz(self.config.timezone)

    def _cache_chat_participants(self, chat: Chat) -> None:
        for participant in chat.participants:
            if participant.username:
                self._username_cache[participant.id] = participant.username
            if self.my_id is not None and participant.id != self.my_id:
                self._buyer_to_chat[participant.id] = chat.id

    def get_username(self, user_id: int) -> str:
        cached = self._username_cache.get(user_id)
        if cached:
            return cached
        return f'User_{user_id}'

    def format_dt(self, iso: str) -> str:
        if not iso:
            return ''
        try:
            value = iso.replace('Z', '+00:00')
            dt = datetime.fromisoformat(value)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt.astimezone(self._tz).strftime('%Y-%m-%d %H:%M:%S')
        except ValueError:
            return iso

    async def safe_send_message(self, chat_id: str, content: str, **kwargs) -> bool:
        formatted = self._format_message(content, **kwargs)
        return await self._queue.enqueue(chat_id, formatted)

    async def safe_send_image(self, chat_id: str, image_bytes: bytes) -> bool:
        try:
            await self.account.send_image(chat_id, image_bytes)
            return True
        except Exception as e:
            log.error('не удалось отправить фото в чат %s: %s', chat_id, e)
            return False

    def _get_russian_date(self, dt: datetime) -> str:
        months = ['', 'января', 'февраля', 'марта', 'апреля', 'мая', 'июня', 'июля', 'августа', 'сентября', 'октября', 'ноября', 'декабря']
        return f'{dt.day} {months[dt.month]} {dt.year}'

    def _format_message(self, text: str, **kwargs) -> str:
        if not text:
            return ''
        now = datetime.now(self._tz)
        kwargs.setdefault('time', now.strftime('%H:%M'))
        kwargs.setdefault('date', self._get_russian_date(now))
        for key, value in kwargs.items():
            tag = '{' + key + '}'
            if tag in text:
                text = text.replace(tag, str(value))
        return text

    async def process_event(self, event: BaseEvent) -> None:
        events_to_dispatch: list[BaseEvent] = [event]
        try:
            if isinstance(event, NewMessageEvent):
                if not self._should_dispatch_message(event):
                    events_to_dispatch = []
                else:
                    self._cache_chat_participants(event.chat)
                    command_event = await self._handle_new_message(event)
                    if command_event is not None:
                        events_to_dispatch = [command_event]
            elif isinstance(event, NewOrderEvent):
                await self._handle_new_order(event)
            elif isinstance(event, OrderStatusChangedEvent):
                await self._handle_order_status_changed(event)
            elif isinstance(event, NewReviewEvent):
                await self._handle_new_review(event)
            else:
                log.debug('неизвестный ивент: %r', event)
        except Exception:
            log.exception('упал на обработке %r', event)
        for ev in events_to_dispatch:
            for listener in list(self._listeners):
                try:
                    await listener(ev)
                except Exception:
                    log.exception('слушатель свалился')

    def _should_dispatch_message(self, event: NewMessageEvent) -> bool:
        msg = event.message
        if msg.type != MessageType.DEFAULT:
            return False
        if msg.author_id == self.my_id:
            return False
        if not (msg.content or '').strip():
            return False
        author_username = self.get_username(msg.author_id)
        if self.config.is_blacklisted(author_username):
            return False
        return True

    async def _handle_new_message(self, event: NewMessageEvent) -> Optional[CommandInvokedEvent]:
        msg = event.message
        chat = event.chat
        if msg.type != MessageType.DEFAULT:
            return None
        if msg.author_id == self.my_id:
            return None
        author_username = self.get_username(msg.author_id)
        if self.config.is_blacklisted(author_username):
            log.info('%s в чс, скип', author_username)
            return None
        command_event = await self._try_handle_starvell_command(chat_id=chat.id, content=msg.content, event=event, author_username=author_username)
        if command_event is not None:
            self.config.mark_chat_greeted(chat.id)
            await self._maybe_read_chat(chat.id)
            return command_event
        self._render_chat_message(chat.id, author_username, msg.author_id, msg.content)
        await self._maybe_send_greeting(chat.id, author_username)
        await self._apply_triggers(chat.id, msg.content, author_username)
        await self._maybe_read_chat(chat.id)
        return None

    async def _maybe_send_greeting(self, chat_id: str, username: str) -> None:
        if not self.config.greeting_enabled or not self.config.greeting_text:
            self.config.mark_chat_greeted(chat_id)
            return
        if self.config.is_chat_greeted(chat_id):
            return
        await self.safe_send_message(chat_id, self.config.greeting_text, username=username)
        self.config.mark_chat_greeted(chat_id)

    async def _maybe_read_chat(self, chat_id: str) -> None:
        if not self.config.auto_read_chats:
            return
        try:
            await self.account.read_chat(chat_id)
        except StarvellAPIError as e:
            log.debug('read_chat %s упал: %s', chat_id, e)

    async def _try_handle_starvell_command(self, chat_id: str, content: str, event: NewMessageEvent, author_username: str) -> Optional[CommandInvokedEvent]:
        stripped = content.strip()
        if not stripped:
            return None
        first_token = stripped.split(maxsplit=1)[0].lower()
        response = self.config.get_starvell_command(first_token)
        if response is None:
            return None
        await self.safe_send_message(chat_id, response, username=author_username)
        log.info('команду %s написал %s', first_token, author_username)
        return CommandInvokedEvent(command=first_token, message=event.message, chat=event.chat, author_username=author_username, response=response)

    async def _apply_triggers(self, chat_id: str, content: str, username: str) -> None:
        lowered = content.lower()
        for key, response in self.config.triggers.items():
            if key.lower() in lowered:
                await self.safe_send_message(chat_id, response, username=username)
                return

    async def _handle_new_order(self, event: NewOrderEvent) -> None:
        order = event.order
        buyer = order.buyer.username if order.buyer else self.get_username(order.buyer_id)
        self._render_new_order(order_id=order.id, status=order.status.value, price=order.total_price, buyer=buyer, created_at=self.format_dt(order.created_at))

    async def _handle_order_status_changed(self, event: OrderStatusChangedEvent) -> None:
        order = event.order
        self._render_order_status(order_id=order.id, status=order.status.value, created_at=self.format_dt(order.created_at))
        if order.status == OrderStatus.COMPLETED and self.config.thanks_after_complete_enabled and self.config.thanks_text and (order.id not in self._thanks_sent):
            chat_id = await self._resolve_chat_for_buyer(order.buyer_id)
            if chat_id is not None:
                self._thanks_sent.add(order.id)
                buyer_username = self.get_username(order.buyer_id)
                await self.safe_send_message(chat_id, self.config.thanks_text, username=buyer_username, order_id=short_order_id(order.id))

    async def _resolve_chat_for_buyer(self, buyer_id: int) -> Optional[str]:
        cached = self._buyer_to_chat.get(buyer_id)
        if cached:
            return cached
        try:
            chats = await self.account.get_chats(limit=100)
        except StarvellAPIError as e:
            log.warning('чаты для thanks не подтянулись: %s', e)
            return None
        for chat in chats:
            self._cache_chat_participants(chat)
        return self._buyer_to_chat.get(buyer_id)

    async def _handle_new_review(self, event: NewReviewEvent) -> None:
        review = event.review
        author = review.author_username or self.get_username(review.author_id)
        self._render_review(review_id=review.id, author=author, rating=review.rating, content=review.content)
        if not self.config.review_auto_reply_enabled:
            return
        if review.response is not None:
            return
        reply = self.config.review_reply_for(review.rating)
        if not reply:
            return
        formatted_reply = self._format_message(reply, username=author, rating=review.rating)
        try:
            await self.account.create_review_response(review.id, formatted_reply)
        except StarvellAPIError as e:
            log.warning('ответ на отзыв %s не ушёл: %s', review.id, e)