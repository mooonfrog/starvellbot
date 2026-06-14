import logging
from aiogram import Bot
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from src.configs.config import Config
from src.starvellapi.updater.events import BaseEvent, CommandInvokedEvent, NewMessageEvent, NewOrderEvent, NewReviewEvent, OrderStatusChangedEvent
from src.tgbot import keyboards as kb
from src.utils import short_order_id
from src.utils.worker import Worker
log = logging.getLogger('telegrambot.notifer')

def _add_hide_button(markup: InlineKeyboardMarkup | None) -> InlineKeyboardMarkup | None:
    if markup is None:
        return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text='🙈 Скрыть', callback_data='msg:hide')]])
    rows = markup.inline_keyboard.copy()
    rows.append([InlineKeyboardButton(text='🙈 Скрыть', callback_data='msg:hide')])
    return InlineKeyboardMarkup(inline_keyboard=rows)

class TelegramNotifier:

    def __init__(self, bot: Bot, config: Config, worker: Worker) -> None:
        self._bot = bot
        self._config = config
        self._worker = worker

    async def __call__(self, event: BaseEvent) -> None:
        text, markup = self._render(event)
        if text is None:
            return
        markup = _add_hide_button(markup)
        for user_id in list(self._config.authorized_telegram_users):
            try:
                await self._bot.send_message(user_id, text, reply_markup=markup)
            except Exception as e:
                log.warning('уведомление %s не ушло: %s', user_id, e)

    def _render(self, event: BaseEvent):
        if isinstance(event, CommandInvokedEvent):
            if not self._config.notify_commands:
                return (None, None)
            formatted_response = self._worker._format_message(event.response, username=event.author_username)
            text = f'⚙️ <b>Команда {event.command}</b>\nОт: {event.author_username}\nЧат: <code>{event.chat.id}</code>\nВремя: {self._worker.format_dt(event.message.created_at)}\n\nСообщение: {event.message.content}\nОтвет бота: {formatted_response}'
            return (text, None)
        if isinstance(event, NewMessageEvent):
            if not self._config.notify_messages:
                return (None, None)
            author = self._worker.get_username(event.message.author_id)
            content = event.message.content or ''
            text = f'💬 <b>Новое сообщение в чате {author}.</b>\nСодержание: {content}.'
            return (text, kb.message_actions_kb(event.chat.id, bool(self._config.quick_replies)))
        if isinstance(event, NewOrderEvent):
            if not self._config.notify_orders:
                return (None, None)
            order = event.order
            buyer = order.buyer.username if order.buyer else self._worker.get_username(order.buyer_id)
            text = f'🆕 <b>Новый заказ</b>\nID: <code>{short_order_id(order.id)}</code>\nСтатус: {order.status.value}\nСумма: {order.total_price:.2f}₽\nПокупатель: {buyer}\nСоздан: {self._worker.format_dt(order.created_at)}'
            return (text, kb.order_actions_kb(order.id))
        if isinstance(event, OrderStatusChangedEvent):
            if not self._config.notify_order_status:
                return (None, None)
            order = event.order
            text = f'📊 <b>Статус заказа</b>\nID: <code>{short_order_id(order.id)}</code>\nНовый статус: {order.status.value}'
            return (text, kb.order_actions_kb(order.id))
        if isinstance(event, NewReviewEvent):
            if not self._config.notify_reviews:
                return (None, None)
            review = event.review
            text = f'⭐ <b>Новый отзыв</b>\nОт: {review.author_username or self._worker.get_username(review.author_id)}\nОценка: {review.rating}★\nЗаказ: <code>{short_order_id(review.order_id)}</code>\n\n{review.content}'
            return (text, kb.review_actions_kb())
        return (None, None)