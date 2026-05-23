import logging

from aiogram import Bot

from src.configs.config import Config
from src.starvellapi.updater.events import (
    BaseEvent,
    CommandInvokedEvent,
    NewMessageEvent,
    NewOrderEvent,
    NewReviewEvent,
    OrderStatusChangedEvent,
)
from src.tgbot import keyboards as kb
from src.utils import short_order_id
from src.utils.worker import Worker

log = logging.getLogger("telegrambot.notifer")


class TelegramNotifier:
    def __init__(self, bot: Bot, config: Config, worker: Worker) -> None:
        self._bot = bot
        self._config = config
        self._worker = worker

    async def __call__(self, event: BaseEvent) -> None:
        text, markup = self._render(event)
        if text is None:
            return
        for user_id in list(self._config.authorized_telegram_users):
            try:
                await self._bot.send_message(user_id, text, reply_markup=markup)
            except Exception as e:
                log.warning("уведомление %s не ушло: %s", user_id, e)

    def _render(self, event: BaseEvent):
        if isinstance(event, CommandInvokedEvent):
            if not self._config.notify_commands:
                return None, None
            text = (
                f"⚙️ <b>Команда {event.command}</b>\n"
                f"От: {event.author_username}\n"
                f"Чат: <code>{event.chat.id}</code>\n"
                f"Время: {self._worker.format_dt(event.message.created_at)}\n\n"
                f"Сообщение: {event.message.content}\n"
                f"Ответ бота: {event.response}"
            )
            return text, None
        if isinstance(event, NewMessageEvent):
            if not self._config.notify_messages:
                return None, None
            author = self._worker.get_username(event.message.author_id)
            content = event.message.content or ""
            text = (
                f"💬 <b>Новое сообщение в чате {author}.</b>\n"
                f"Содержание: {content}."
            )
            return text, kb.message_actions_kb(event.chat.id, bool(self._config.quick_replies))
        if isinstance(event, NewOrderEvent):
            if not self._config.notify_orders:
                return None, None
            order = event.order
            buyer = (
                order.buyer.username
                if order.buyer
                else self._worker.get_username(order.buyer_id)
            )
            text = (
                f"🆕 <b>Новый заказ</b>\n"
                f"ID: <code>{short_order_id(order.id)}</code>\n"
                f"Статус: {order.status.value}\n"
                f"Сумма: {order.total_price:.2f}₽\n"
                f"Покупатель: {buyer}\n"
                f"Создан: {self._worker.format_dt(order.created_at)}"
            )
            return text, kb.order_actions_kb(order.id)
        if isinstance(event, OrderStatusChangedEvent):
            if not self._config.notify_order_status:
                return None, None
            order = event.order
            text = (
                f"📊 <b>Статус заказа</b>\n"
                f"ID: <code>{short_order_id(order.id)}</code>\n"
                f"Новый статус: {order.status.value}"
            )
            return text, kb.order_actions_kb(order.id)
        if isinstance(event, NewReviewEvent):
            if not self._config.notify_reviews:
                return None, None
            review = event.review
            text = (
                f"⭐ <b>Новый отзыв</b>\n"
                f"От: {review.author_username or self._worker.get_username(review.author_id)}\n"
                f"Оценка: {review.rating}★\n"
                f"Заказ: <code>{short_order_id(review.order_id)}</code>\n\n"
                f"{review.content}"
            )
            return text, kb.review_actions_kb()
        return None, None
