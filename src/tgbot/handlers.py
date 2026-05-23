import asyncio
import html
import logging
import os
from pathlib import Path

from aiogram import F, Router
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import BufferedInputFile, CallbackQuery, FSInputFile, Message

from src.configs.config import Config
from src.starvellapi import Account
from src.starvellapi.exceptions import StarvellAPIError
from src.tgbot import keyboards as kb
from src.tgbot.confirm import ConfirmStore, confirm_kb
from src.tgbot.states import (
    AuthSG,
    BlacklistSG,
    CommandEditSG,
    CommandSG,
    GreetingSG,
    PluginUploadSG,
    QuickReplySG,
    ReplySG,
    ReviewReplySG,
    ThanksSG,
    TimezoneSG,
    TriggerEditSG,
    TriggerSG,
    WatermarkSG,
)
from src.utils.worker import Worker

log = logging.getLogger("telegrambot.handlers")
router = Router()

LOG_FILE = Path("logs/log.log")


async def _safe_edit(call: CallbackQuery, text: str, markup) -> None:
    try:
        await call.message.edit_text(text, reply_markup=markup)
    except Exception:
        await call.message.answer(text, reply_markup=markup)


def _mono(value: str) -> str:
    if not value:
        return "-"
    return f"<code>{html.escape(str(value))}</code>"


_AUTODELETE_HINT = "  (удалится через 5 сек)"


async def _delete_later(messages: list, delay: float = 5.0) -> None:
    try:
        await asyncio.sleep(delay)
    except asyncio.CancelledError:
        return
    for msg in messages:
        try:
            await msg.delete()
        except Exception:
            pass


def _schedule_delete(*messages, delay: float = 5.0) -> None:
    items = [m for m in messages if m is not None]
    if not items:
        return
    try:
        asyncio.get_running_loop().create_task(_delete_later(items, delay))
    except RuntimeError:
        pass


@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext, config: Config) -> None:
    if config.is_authorized(message.from_user.id):
        await state.clear()
        await message.answer("🩵 starvellbot\n👇 Воспользуйтесь кнопками ниже", reply_markup=kb.main_menu())
        return
    await state.set_state(AuthSG.waiting_password)
    await message.answer("Введите пароль:")


@router.message(AuthSG.waiting_password)
async def auth_password(message: Message, state: FSMContext, config: Config) -> None:
    text = (message.text or "").strip()
    if not config.telegram_password_hash or not config.telegram_password_hash.get("hash"):
        await message.answer(
            "Пароль не задан. Установите его в конфиге через telegram_password_hash."
        )
        return
    ok, error = config.verify_password(message.from_user.id, text)
    if ok:
        config.authorize_user(message.from_user.id)
        await state.clear()
        await message.answer("🩵 starvellbot\n👇 Воспользуйтесь кнопками ниже", reply_markup=kb.main_menu())
        return
    await message.answer(error or "Неверный пароль.")


@router.message(Command("logs"))
async def cmd_logs(message: Message, config: Config) -> None:
    if not config.is_authorized(message.from_user.id):
        return
    if not LOG_FILE.exists():
        await message.answer("Лог-файл пока не создан.")
        return
    try:
        await message.answer_document(
            FSInputFile(LOG_FILE),
            caption="Текущий лог StarvellBot",
        )
    except Exception as e:
        log.exception("лог отдать не получилось")
        await message.answer(f"не отдалось: {e}")


@router.message(Command("restart"))
async def cmd_restart(message: Message, config: Config, confirm_store: ConfirmStore) -> None:
    if not config.is_authorized(message.from_user.id):
        return
    token = await confirm_store.create({"action": "restart"})
    await message.answer(
        "Уверены, что хотите перезапустить бота?",
        reply_markup=confirm_kb(token),
    )


@router.callback_query(F.data.startswith("cf:n:"))
async def cb_confirm_no(call: CallbackQuery, confirm_store: ConfirmStore) -> None:
    token = call.data.split(":", 2)[2]
    await confirm_store.pop(token)
    try:
        await call.message.edit_text("Действие отменено.")
    except Exception:
        pass
    await call.answer()


@router.callback_query(F.data.startswith("cf:y:"))
async def cb_confirm_yes(
    call: CallbackQuery,
    confirm_store: ConfirmStore,
    config: Config,
    app=None,
) -> None:
    token = call.data.split(":", 2)[2]
    payload = await confirm_store.pop(token)
    if payload is None:
        await call.answer("Запрос истёк или уже выполнен", show_alert=True)
        try:
            await call.message.edit_text("Запрос подтверждения истёк.")
        except Exception:
            pass
        return

    action = payload.get("action")
    if action == "restart":
        try:
            await call.message.edit_text("Перезапускаю бота...")
        except Exception:
            pass
        log.warning("/restart подтверждён, user_id=%s", call.from_user.id)
        os.environ["STARVELLBOT_RESTART"] = "1"
        loop = asyncio.get_running_loop()
        loop.call_later(0.5, lambda: loop.stop())
        await call.answer()
        return

    if action == "plugin_delete":
        uuid = payload.get("uuid")
        if app is None or uuid not in getattr(app, "plugins", {}):
            await call.answer("Плагин не найден", show_alert=True)
            return
        plugin = app.plugins[uuid]
        try:
            Path(plugin.path).unlink(missing_ok=True)
        except Exception as e:
            await call.answer(f"Ошибка удаления: {e}", show_alert=True)
            return
        try:
            await call.message.edit_text(
                f"<b>{plugin.name}</b>\nФайл удалён. Нажми /restart, чтобы перечитать плагины.",
                reply_markup=kb.back_kb("menu:plugins"),
            )
        except Exception:
            pass
        await call.answer("Удалено")
        return

    await call.answer("Неизвестное действие", show_alert=True)


@router.callback_query(F.data == "menu:main")
async def cb_main(call: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await _safe_edit(call, "🩵 starvellbot\n👇 Воспользуйтесь кнопками ниже", kb.main_menu())
    await call.answer()


@router.callback_query(F.data.startswith("cancel:"))
async def cb_cancel(call: CallbackQuery, state: FSMContext) -> None:
    target = call.data.split(":", 1)[1] or "menu:main"
    await state.clear()
    try:
        await call.message.delete()
    except Exception:
        pass
    if target == "menu:main":
        try:
            await call.bot.send_message(call.message.chat.id, "🩵 starvellbot\n👇 Воспользуйтесь кнопками ниже", reply_markup=kb.main_menu())
        except Exception:
            pass
    await call.answer("Отменено")


@router.callback_query(F.data == "menu:status")
async def cb_status(call: CallbackQuery, account: Account) -> None:
    try:
        profile = await account.get_profile()
        text = (
            f"<b>Профиль</b>\n"
            f"Пользователь: {profile.user.username} (id={profile.user.id})\n"
            f"Баланс: {profile.balance:.2f}₽\n"
            f"На удержании: {profile.held:.2f}₽\n"
            f"Продажи: {profile.sales_orders}\n"
            f"Покупки: {profile.purchase_orders}\n"
            f"Непрочитанных чатов: {len(profile.unread_chat_ids)}"
        )
    except StarvellAPIError as e:
        text = f"Ошибка: {e}"
    await _safe_edit(call, text, kb.back_kb())
    await call.answer()


def _triggers_text(config: Config) -> str:
    text = "<b>Триггеры</b>\nЕсли в сообщении встретится ключ - отправлю ответ."
    if config.triggers:
        lines = [f"• {_mono(k)} → {_mono(v)}" for k, v in config.triggers.items()]
        text = text + "\n\n" + "\n".join(lines)
    return text


async def _show_triggers(call: CallbackQuery, config: Config) -> None:
    await _safe_edit(call, _triggers_text(config), kb.triggers_kb(config))


@router.callback_query(F.data == "menu:triggers")
async def cb_triggers(call: CallbackQuery, config: Config) -> None:
    await _show_triggers(call, config)
    await call.answer()


@router.callback_query(F.data.startswith("trig:open:"))
async def cb_trig_open(call: CallbackQuery, config: Config) -> None:
    key = call.data.split(":", 2)[2]
    response = config.triggers.get(key)
    if response is None:
        await call.answer("Триггер уже удалён", show_alert=True)
        await _show_triggers(call, config)
        return
    text = (
        f"<b>Триггер</b>\n"
        f"Ключ: {_mono(key)}\n"
        f"Ответ: {_mono(response)}"
    )
    await _safe_edit(call, text, kb.trigger_card_kb(key))
    await call.answer()


@router.callback_query(F.data.startswith("trig:edit:"))
async def cb_trig_edit(call: CallbackQuery, state: FSMContext) -> None:
    key = call.data.split(":", 2)[2]
    await state.set_state(TriggerEditSG.waiting_response)
    await state.update_data(key=key)
    await call.message.answer(f"Введите новый ответ для <code>{key}</code>:", reply_markup=kb.cancel_kb("menu:triggers"))
    await call.answer()


@router.message(TriggerEditSG.waiting_response)
async def trig_edit_response(message: Message, state: FSMContext, config: Config) -> None:
    text = (message.text or "").strip()
    data = await state.get_data()
    key = data.get("key", "")
    if text == "/cancel" or not text or not key:
        await state.clear()
        await message.answer("Отменено.", reply_markup=kb.main_menu())
        return
    config.set_trigger(key, text)
    await state.clear()
    await message.answer(
        f"Ответ для <code>{key}</code> обновлён.",
        reply_markup=kb.triggers_kb(config),
    )


@router.callback_query(F.data == "trig:add")
async def cb_trig_add(call: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(TriggerSG.waiting_key)
    await call.message.answer("Введите ключевое слово:", reply_markup=kb.cancel_kb("menu:triggers"))
    await call.answer()


@router.message(TriggerSG.waiting_key)
async def trig_key(message: Message, state: FSMContext) -> None:
    text = (message.text or "").strip()
    if text == "/cancel":
        await state.clear()
        await message.answer("Отменено.", reply_markup=kb.main_menu())
        return
    await state.update_data(key=text)
    await state.set_state(TriggerSG.waiting_response)
    await message.answer("Теперь введите ответ:", reply_markup=kb.cancel_kb("menu:triggers"))


@router.message(TriggerSG.waiting_response)
async def trig_response(message: Message, state: FSMContext, config: Config) -> None:
    data = await state.get_data()
    key = data.get("key", "")
    response = (message.text or "").strip()
    if not key or not response:
        await state.clear()
        await message.answer("Пустые значения, отмена.", reply_markup=kb.main_menu())
        return
    config.set_trigger(key, response)
    await state.clear()
    await message.answer(
        f"Триггер <code>{key}</code> сохранён.",
        reply_markup=kb.triggers_kb(config),
    )


@router.callback_query(F.data.startswith("trig:rm:"))
async def cb_trig_rm(call: CallbackQuery, config: Config) -> None:
    key = call.data.split(":", 2)[2]
    config.remove_trigger(key)
    await _show_triggers(call, config)
    await call.answer("Удалено")


def _commands_text(config: Config) -> str:
    text = (
        "<b>Команды Starvell</b>\n"
        "Покупатель пишет команду в чат - бот отвечает заданным текстом."
    )
    if config.starvell_commands:
        lines = [
            f"• {_mono(k)} → {_mono(v)}" for k, v in config.starvell_commands.items()
        ]
        text += "\n\n" + "\n".join(lines)
    return text


async def _show_commands(call: CallbackQuery, config: Config) -> None:
    await _safe_edit(call, _commands_text(config), kb.commands_kb(config))


@router.callback_query(F.data == "menu:commands")
async def cb_commands(call: CallbackQuery, config: Config) -> None:
    await _show_commands(call, config)
    await call.answer()


@router.callback_query(F.data.startswith("cmd:open:"))
async def cb_cmd_open(call: CallbackQuery, config: Config) -> None:
    key = call.data.split(":", 2)[2]
    response = config.starvell_commands.get(key)
    if response is None:
        await call.answer("Команда уже удалена", show_alert=True)
        await _show_commands(call, config)
        return
    text = (
        f"<b>Команда</b>\n"
        f"Ключ: {_mono(key)}\n"
        f"Ответ: {_mono(response)}"
    )
    await _safe_edit(call, text, kb.command_card_kb(key))
    await call.answer()


@router.callback_query(F.data.startswith("cmd:edit:"))
async def cb_cmd_edit(call: CallbackQuery, state: FSMContext) -> None:
    key = call.data.split(":", 2)[2]
    await state.set_state(CommandEditSG.waiting_response)
    await state.update_data(key=key)
    await call.message.answer(f"Введите новый ответ для <code>{key}</code>:", reply_markup=kb.cancel_kb("menu:commands"))
    await call.answer()


@router.message(CommandEditSG.waiting_response)
async def cmd_edit_response(message: Message, state: FSMContext, config: Config) -> None:
    text = (message.text or "").strip()
    data = await state.get_data()
    key = data.get("key", "")
    if text == "/cancel" or not text or not key:
        await state.clear()
        await message.answer("Отменено.", reply_markup=kb.main_menu())
        return
    config.set_starvell_command(key, text)
    await state.clear()
    await message.answer(
        f"Ответ для <code>{key}</code> обновлён.",
        reply_markup=kb.commands_kb(config),
    )


@router.callback_query(F.data == "cmd:add")
async def cb_cmd_add(call: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(CommandSG.waiting_key)
    await call.message.answer(
        "Введите команду (например <code>!вызов</code>):",
        parse_mode="HTML",
        reply_markup=kb.cancel_kb("menu:commands"),
    )
    await call.answer()


@router.message(CommandSG.waiting_key)
async def cmd_key(message: Message, state: FSMContext) -> None:
    text = (message.text or "").strip()
    if text == "/cancel":
        await state.clear()
        await message.answer("Отменено.", reply_markup=kb.main_menu())
        return
    await state.update_data(key=text)
    await state.set_state(CommandSG.waiting_response)
    await message.answer("Теперь введите ответ:", reply_markup=kb.cancel_kb("menu:commands"))


@router.message(CommandSG.waiting_response)
async def cmd_response(message: Message, state: FSMContext, config: Config) -> None:
    data = await state.get_data()
    key = data.get("key", "")
    response = (message.text or "").strip()
    if not key or not response:
        await state.clear()
        await message.answer("Пустые значения, отмена.", reply_markup=kb.main_menu())
        return
    config.set_starvell_command(key, response)
    await state.clear()
    await message.answer(
        f"Команда <code>{key}</code> сохранена.",
        reply_markup=kb.commands_kb(config),
    )


@router.callback_query(F.data.startswith("cmd:rm:"))
async def cb_cmd_rm(call: CallbackQuery, config: Config) -> None:
    key = call.data.split(":", 2)[2]
    config.remove_starvell_command(key)
    await _show_commands(call, config)
    await call.answer("Удалено")


@router.callback_query(F.data.startswith("msg:reply:"))
async def cb_msg_reply(call: CallbackQuery, state: FSMContext) -> None:
    chat_id = call.data.split(":", 2)[2]
    await state.set_state(ReplySG.waiting_text)
    prompt = await call.message.answer(
        f"Введите ответ в чат {_mono(chat_id)}:{_AUTODELETE_HINT}",
        parse_mode="HTML",
        reply_markup=kb.cancel_kb(),
    )
    await state.update_data(chat_id=chat_id, prompt_chat_id=prompt.chat.id, prompt_message_id=prompt.message_id)
    await call.answer()


async def _delete_by_id(bot, chat_id: int, message_id: int) -> None:
    try:
        await bot.delete_message(chat_id, message_id)
    except Exception:
        pass


async def _delete_prompt_later(bot, chat_id: int, message_id: int, delay: float = 5.0) -> None:
    try:
        await asyncio.sleep(delay)
    except asyncio.CancelledError:
        return
    await _delete_by_id(bot, chat_id, message_id)


@router.message(ReplySG.waiting_text)
async def msg_reply_text(
    message: Message,
    state: FSMContext,
    worker: Worker,
) -> None:
    text = (message.text or "").strip()
    data = await state.get_data()
    chat_id = data.get("chat_id")
    prompt_chat_id = data.get("prompt_chat_id")
    prompt_message_id = data.get("prompt_message_id")

    if text == "/cancel" or not text or not chat_id:
        await state.clear()
        cancel_msg = await message.answer(f"Отменено.{_AUTODELETE_HINT}")
        _schedule_delete(message, cancel_msg)
        if prompt_chat_id and prompt_message_id:
            asyncio.create_task(_delete_prompt_later(message.bot, prompt_chat_id, prompt_message_id))
        return

    sent = await worker.safe_send_message(chat_id, text)
    await state.clear()
    if sent:
        confirm = await message.answer(f"Отправлено.{_AUTODELETE_HINT}")
    else:
        confirm = await message.answer(f"Не удалось отправить сообщение.{_AUTODELETE_HINT}")
    _schedule_delete(message, confirm)
    if prompt_chat_id and prompt_message_id:
        asyncio.create_task(_delete_prompt_later(message.bot, prompt_chat_id, prompt_message_id))


@router.callback_query(F.data == "msg:hide")
async def cb_msg_hide(call: CallbackQuery) -> None:
    try:
        await call.message.delete()
    except Exception:
        try:
            await call.message.edit_reply_markup(reply_markup=None)
        except Exception:
            pass
    await call.answer()


@router.callback_query(F.data == "menu:blacklist")
async def cb_blacklist(call: CallbackQuery, config: Config) -> None:
    text = "<b>Чёрный список</b>\nНики (без @). Жми ❌ чтобы убрать."
    if config.blacklist_usernames:
        text += "\n\n" + "\n".join(f"• {_mono(u)}" for u in config.blacklist_usernames)
    await _safe_edit(call, text, kb.blacklist_kb(config))
    await call.answer()


@router.callback_query(F.data == "bl:add")
async def cb_bl_add(call: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(BlacklistSG.waiting_add)
    await call.message.answer("Введите ник для блокировки:", reply_markup=kb.cancel_kb("menu:blacklist"))
    await call.answer()


@router.message(BlacklistSG.waiting_add)
async def bl_add(message: Message, state: FSMContext, config: Config) -> None:
    username = (message.text or "").strip()
    if not username or username == "/cancel":
        await state.clear()
        await message.answer("Отменено.", reply_markup=kb.main_menu())
        return
    config.add_blacklist(username)
    await state.clear()
    await message.answer(
        f"Ник {username.lstrip('@').lower()} добавлен в ЧС.",
        reply_markup=kb.blacklist_kb(config),
    )


@router.callback_query(F.data.startswith("bl:rm:"))
async def cb_bl_rm(call: CallbackQuery, config: Config) -> None:
    username = call.data.split(":", 2)[2]
    config.remove_blacklist(username)
    await _safe_edit(call, "Ник удалён из ЧС.", kb.blacklist_kb(config))
    await call.answer()


@router.callback_query(F.data == "menu:reviews")
async def cb_reviews(call: CallbackQuery, config: Config) -> None:
    lines = [
        f"{r}★ → {_mono(config.review_replies.get(str(r), '-'))}"
        for r in (5, 4, 3, 2, 1)
    ]
    text = "<b>Авто-ответ на отзывы</b>\n" + "\n".join(lines)
    await _safe_edit(call, text, kb.reviews_kb(config))
    await call.answer()


@router.callback_query(F.data == "rev:toggle")
async def cb_rev_toggle(call: CallbackQuery, config: Config) -> None:
    config.review_auto_reply_enabled = not config.review_auto_reply_enabled
    config.save()
    await cb_reviews(call, config)


@router.callback_query(F.data.startswith("rev:edit:"))
async def cb_rev_edit(call: CallbackQuery, state: FSMContext) -> None:
    rating = call.data.split(":")[2]
    await state.set_state(ReviewReplySG.waiting_text)
    await state.update_data(rating=rating)
    await call.message.answer(f"Введите текст ответа для {rating}★:", reply_markup=kb.cancel_kb("menu:reviews"))
    await call.answer()


@router.message(ReviewReplySG.waiting_text)
async def rev_text(message: Message, state: FSMContext, config: Config) -> None:
    text = (message.text or "").strip()
    data = await state.get_data()
    rating = data.get("rating")
    if not text or text == "/cancel" or not rating:
        await state.clear()
        await message.answer("Отменено.", reply_markup=kb.main_menu())
        return
    config.review_replies[str(rating)] = text
    config.save()
    await state.clear()
    await message.answer("Сохранено.", reply_markup=kb.reviews_kb(config))


_TOGGLES_TEXT = (
    "<b>Переключатели</b>\n"
    "Глобальные настройки бота. Тапни по пункту, чтобы переключить."
)


async def _show_toggles(call: CallbackQuery, config: Config) -> None:
    await _safe_edit(call, _TOGGLES_TEXT, kb.toggles_kb(config))


@router.callback_query(F.data == "menu:toggles")
async def cb_toggles(call: CallbackQuery, state: FSMContext, config: Config) -> None:
    await state.clear()
    await _show_toggles(call, config)
    await call.answer()


@router.callback_query(F.data == "menu:notify")
async def cb_notify(call: CallbackQuery, config: Config) -> None:
    text = (
        "<b>Уведомления в Telegram</b>\n"
        "Какие события присылать в чат с ботом."
    )
    await _safe_edit(call, text, kb.notify_kb(config))
    await call.answer()


@router.callback_query(F.data.startswith("ntf:"))
async def cb_notify_toggle(call: CallbackQuery, config: Config) -> None:
    key = call.data.split(":", 1)[1]
    attr_map = {
        "messages": "notify_messages",
        "orders": "notify_orders",
        "order_status": "notify_order_status",
        "reviews": "notify_reviews",
        "commands": "notify_commands",
    }
    attr = attr_map.get(key)
    if attr is None:
        await call.answer("Неизвестная настройка", show_alert=True)
        return
    setattr(config, attr, not getattr(config, attr))
    config.save()
    await cb_notify(call, config)


@router.callback_query(F.data == "menu:thanks")
async def cb_thanks(call: CallbackQuery, config: Config) -> None:
    text = (
        "<b>Авто-благодарность</b>\n"
        "Отправляется покупателю в чат, когда заказ завершается (обе стороны подтвердили заказ).\n\n"
        f"Текст: {_mono(config.thanks_text)}"
    )
    await _safe_edit(call, text, kb.thanks_kb(config))
    await call.answer()


@router.callback_query(F.data == "menu:watermark")
async def cb_watermark(call: CallbackQuery, config: Config) -> None:
    text = (
        "<b>Watermark</b>\n"
        "Дописывается ко всем исходящим сообщениям бота в Starvell.\n\n"
        f"Текст: {_mono(config.watermark_text)}"
    )
    await _safe_edit(call, text, kb.watermark_kb(config))
    await call.answer()


@router.callback_query(F.data == "menu:greeting")
async def cb_greeting(call: CallbackQuery, config: Config) -> None:
    text = (
        "<b>Приветствие новых чатов</b>\n"
        "Отправляется один раз, когда в чате появляется первое сообщение от покупателя.\n\n"
        f"Текст: {_mono(config.greeting_text)}"
    )
    await _safe_edit(call, text, kb.greeting_kb(config))
    await call.answer()


@router.callback_query(F.data == "tg:greeting")
async def cb_tg_greeting(call: CallbackQuery, config: Config) -> None:
    config.greeting_enabled = not config.greeting_enabled
    config.save()
    await cb_greeting(call, config)


@router.callback_query(F.data == "tg:greeting_edit")
async def cb_tg_greeting_edit(call: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(GreetingSG.waiting_text)
    await call.message.answer(
        "Введите текст приветствия:",
        reply_markup=kb.cancel_kb("menu:greeting"),
    )
    await call.answer()


@router.message(GreetingSG.waiting_text)
async def greeting_text(message: Message, state: FSMContext, config: Config) -> None:
    text = (message.text or "").strip()
    if text == "/cancel" or not text:
        await state.clear()
        await message.answer("Отменено.", reply_markup=kb.main_menu())
        return
    config.greeting_text = text
    config.save()
    await state.clear()
    await message.answer("Текст обновлён.", reply_markup=kb.greeting_kb(config))


@router.callback_query(F.data == "tg:wm")
async def cb_tg_wm(call: CallbackQuery, config: Config) -> None:
    config.watermark_enabled = not config.watermark_enabled
    config.save()
    await cb_watermark(call, config)


@router.callback_query(F.data == "tg:ok")
async def cb_tg_ok(call: CallbackQuery, config: Config) -> None:
    config.online_keeper = not config.online_keeper
    config.save()
    await _show_toggles(call, config)
    await call.answer("Изменение применится после перезапуска бота")


@router.callback_query(F.data == "tg:autoread")
async def cb_tg_autoread(call: CallbackQuery, config: Config) -> None:
    config.auto_read_chats = not config.auto_read_chats
    config.save()
    await _show_toggles(call, config)
    await call.answer()


@router.callback_query(F.data == "tg:wm_edit")
async def cb_tg_wm_edit(call: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(WatermarkSG.waiting_text)
    await call.message.answer("Введите текст watermark:", reply_markup=kb.cancel_kb("menu:watermark"))
    await call.answer()


@router.message(WatermarkSG.waiting_text)
async def watermark_text(message: Message, state: FSMContext, config: Config) -> None:
    text = (message.text or "").strip()
    if text == "/cancel":
        await state.clear()
        await message.answer("Отменено.", reply_markup=kb.main_menu())
        return
    config.watermark_text = text
    config.save()
    await state.clear()
    await message.answer("Watermark обновлён.", reply_markup=kb.watermark_kb(config))


@router.callback_query(F.data == "tg:tz_edit")
async def cb_tg_tz_edit(call: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(TimezoneSG.waiting_value)
    await call.message.answer("Введите таймзону (например, Europe/Moscow):", reply_markup=kb.cancel_kb("menu:toggles"))
    await call.answer()


@router.message(TimezoneSG.waiting_value)
async def tz_value(
    message: Message,
    state: FSMContext,
    config: Config,
    worker: Worker,
) -> None:
    text = (message.text or "").strip()
    if text == "/cancel":
        await state.clear()
        await message.answer("Отменено.", reply_markup=kb.main_menu())
        return
    config.timezone = text
    config.save()
    worker.reload_settings()
    await state.clear()
    await message.answer("Таймзона обновлена.", reply_markup=kb.toggles_kb(config))


@router.callback_query(F.data.startswith("order:done:"))
async def cb_order_done(call: CallbackQuery, account: Account) -> None:
    order_id = call.data.split(":", 2)[2]
    try:
        await account.mark_order_completed(order_id)
        await call.answer("Подтверждено", show_alert=True)
    except StarvellAPIError as e:
        await call.answer(f"Ошибка: {e}", show_alert=True)


@router.callback_query(F.data.startswith("order:refund:"))
async def cb_order_refund(call: CallbackQuery, account: Account) -> None:
    order_id = call.data.split(":", 2)[2]
    try:
        await account.refund_order(order_id)
        await call.answer("Возврат оформлен", show_alert=True)
    except StarvellAPIError as e:
        await call.answer(f"Ошибка: {e}", show_alert=True)


@router.callback_query(F.data == "menu:plugins")
async def cb_plugins(call: CallbackQuery, app=None) -> None:
    if app is None or not getattr(app, "plugins", None):
        text = (
            "<b>Плагины</b>\n"
            "Положи .py-файл сюда через кнопку ниже или в папку <code>plugins/</code> и сделай /restart."
        )
        await _safe_edit(call, text, kb.empty_plugins_kb())
        await call.answer()
        return
    text = (
        "<b>Плагины</b>\n"
        f"Загружено: {len(app.plugins)}. Тапни по плагину, чтобы управлять."
    )
    await _safe_edit(call, text, kb.plugins_kb(app.plugins))
    await call.answer()


def _plugin_card_text(plugin) -> str:
    lines = [
        f"<b>{plugin.name}</b> v{plugin.version}",
        f"Автор: {plugin.credits}",
        f"UUID: <code>{plugin.uuid}</code>",
        f"Файл: <code>{plugin.path}</code>",
        f"Статус: {'🟢 включён' if plugin.enabled else '🔴 выключен'}",
    ]
    if plugin.error:
        lines.append(f"⚠ Ошибок: {plugin.error_count}")
        lines.append(f"Последняя: <code>{html.escape(str(plugin.error)[:300])}</code>")
    lines.append("")
    lines.append(plugin.description)
    return "\n".join(lines)


@router.callback_query(F.data.startswith("pl:open:"))
async def cb_plugin_open(call: CallbackQuery, app=None) -> None:
    uuid = call.data.split(":", 2)[2]
    if app is None or uuid not in app.plugins:
        await call.answer("Плагин не найден", show_alert=True)
        return
    plugin = app.plugins[uuid]
    await _safe_edit(call, _plugin_card_text(plugin), kb.plugin_card_kb(uuid, plugin.enabled, has_error=bool(plugin.error)))
    await call.answer()


@router.callback_query(F.data.startswith("pl:toggle:"))
async def cb_plugin_toggle(call: CallbackQuery, config: Config, app=None) -> None:
    uuid = call.data.split(":", 2)[2]
    if app is None or uuid not in app.plugins:
        await call.answer("Плагин не найден", show_alert=True)
        return
    enabled = config.toggle_plugin(uuid)
    app.plugins[uuid].enabled = enabled
    await call.answer("Включён" if enabled else "Выключен")
    plugin = app.plugins[uuid]
    await _safe_edit(call, _plugin_card_text(plugin), kb.plugin_card_kb(uuid, plugin.enabled, has_error=bool(plugin.error)))


@router.callback_query(F.data.startswith("pl:reset_err:"))
async def cb_plugin_reset_err(call: CallbackQuery, app=None) -> None:
    uuid = call.data.split(":", 2)[2]
    if app is None or uuid not in app.plugins:
        await call.answer("Плагин не найден", show_alert=True)
        return
    plugin = app.plugins[uuid]
    plugin.error = None
    plugin.error_count = 0
    await call.answer("Ошибка сброшена")
    await _safe_edit(call, _plugin_card_text(plugin), kb.plugin_card_kb(uuid, plugin.enabled, has_error=False))


@router.callback_query(F.data == "pl:upload")
async def cb_plugin_upload(call: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(PluginUploadSG.waiting_file)
    await call.message.answer(
        "Пришли .py-файл плагина следующим сообщением.",
        reply_markup=kb.cancel_kb("menu:plugins"),
    )
    await call.answer()


@router.message(PluginUploadSG.waiting_file)
async def plugin_upload_file(
    message: Message,
    state: FSMContext,
    config: Config,
    app=None,
) -> None:
    text = (message.text or "").strip()
    if text == "/cancel":
        await state.clear()
        await message.answer("Отменено.")
        return
    if message.document is None:
        await message.answer("Жду файл .py. Пришли как документ.")
        return
    name = message.document.file_name or ""
    if not name.endswith(".py"):
        await message.answer("Это не .py файл.")
        return

    plugins_dir = Path("plugins")
    plugins_dir.mkdir(parents=True, exist_ok=True)
    safe_name = Path(name).name
    target = plugins_dir / safe_name
    if target.exists():
        target = plugins_dir / f"{target.stem}_{int(asyncio.get_running_loop().time())}.py"

    try:
        bot = message.bot
        file = await bot.get_file(message.document.file_id)
        await bot.download_file(file.file_path, destination=target)
    except Exception as e:
        log.exception("плагин не скачался")
        await state.clear()
        await message.answer(f"не скачался: {e}")
        return

    await state.clear()
    await message.answer(
        f"Плагин сохранён как <code>{target}</code>.\n"
        "Для активации нажми /restart."
    )


@router.callback_query(F.data.startswith("pl:delete:"))
async def cb_plugin_delete(
    call: CallbackQuery,
    config: Config,
    confirm_store: ConfirmStore,
    app=None,
) -> None:
    uuid = call.data.split(":", 2)[2]
    if app is None or uuid not in app.plugins:
        await call.answer("Плагин не найден", show_alert=True)
        return
    plugin = app.plugins[uuid]
    token = await confirm_store.create({"action": "plugin_delete", "uuid": uuid})
    text = (
        f"Удалить файл плагина <b>{plugin.name}</b>?\n"
        f"<code>{plugin.path}</code>"
    )
    try:
        await call.message.edit_text(text, reply_markup=confirm_kb(token))
    except Exception:
        await call.message.answer(text, reply_markup=confirm_kb(token))
    await call.answer()


@router.callback_query(F.data.startswith("qr:"))
async def cb_quick_reply(call: CallbackQuery, config: Config, worker: Worker) -> None:
    parts = call.data.split(":", 2)
    if len(parts) != 3:
        await call.answer("Некорректные данные", show_alert=True)
        return
    try:
        idx = int(parts[1])
    except ValueError:
        await call.answer("Некорректный индекс", show_alert=True)
        return
    chat_id = parts[2]
    if idx < 0 or idx >= len(config.quick_replies):
        await call.answer("Шаблон удалён", show_alert=True)
        return
    sent = await worker.safe_send_message(chat_id, config.quick_replies[idx])
    await call.answer("Отправлено" if sent else "Не получилось", show_alert=not sent)
    try:
        await call.message.edit_reply_markup(
            reply_markup=kb.message_actions_kb(chat_id, bool(config.quick_replies))
        )
    except Exception:
        pass


@router.callback_query(F.data.startswith("qrlist:"))
async def cb_quick_reply_list(call: CallbackQuery, config: Config) -> None:
    chat_id = call.data.split(":", 1)[1]
    if not config.quick_replies:
        await call.answer("Шаблоны не заданы", show_alert=True)
        return
    try:
        await call.message.edit_reply_markup(
            reply_markup=kb.quick_replies_for_chat_kb(chat_id, config.quick_replies)
        )
    except Exception:
        pass
    await call.answer()


@router.callback_query(F.data.startswith("qrback:"))
async def cb_quick_reply_back(call: CallbackQuery, config: Config) -> None:
    chat_id = call.data.split(":", 1)[1]
    try:
        await call.message.edit_reply_markup(
            reply_markup=kb.message_actions_kb(chat_id, bool(config.quick_replies))
        )
    except Exception:
        pass
    await call.answer()


@router.callback_query(F.data == "menu:quickreplies")
async def cb_quickreplies(call: CallbackQuery, config: Config) -> None:
    text = (
        "<b>Шаблоны ответов</b>\n"
        "Появляются под уведомлением о новом сообщении в TG."
    )
    if config.quick_replies:
        text += "\n\n" + "\n".join(f"• {_mono(t)}" for t in config.quick_replies)
    await _safe_edit(call, text, kb.quick_replies_kb(config.quick_replies))
    await call.answer()


@router.callback_query(F.data == "qrcfg:add")
async def cb_qrcfg_add(call: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(QuickReplySG.waiting_text)
    await call.message.answer("Введите текст шаблона:", reply_markup=kb.cancel_kb("menu:quickreplies"))
    await call.answer()


@router.message(QuickReplySG.waiting_text)
async def qrcfg_text(message: Message, state: FSMContext, config: Config) -> None:
    text = (message.text or "").strip()
    if text == "/cancel" or not text:
        await state.clear()
        await message.answer("Отменено.", reply_markup=kb.main_menu())
        return
    config.add_quick_reply(text)
    await state.clear()
    await message.answer("Шаблон добавлен.", reply_markup=kb.quick_replies_kb(config.quick_replies))


@router.callback_query(F.data.startswith("qrcfg:rm:"))
async def cb_qrcfg_rm(call: CallbackQuery, config: Config) -> None:
    try:
        idx = int(call.data.split(":", 2)[2])
    except ValueError:
        await call.answer("Некорректные данные", show_alert=True)
        return
    config.remove_quick_reply(idx)
    text = "<b>Шаблоны ответов</b>"
    if config.quick_replies:
        text += "\n\n" + "\n".join(f"• {_mono(t)}" for t in config.quick_replies)
    await _safe_edit(call, text, kb.quick_replies_kb(config.quick_replies))
    await call.answer("Удалено")


@router.callback_query(F.data == "tg:thanks")
async def cb_tg_thanks(call: CallbackQuery, config: Config) -> None:
    config.thanks_after_complete_enabled = not config.thanks_after_complete_enabled
    config.save()
    await cb_thanks(call, config)


@router.callback_query(F.data == "tg:thanks_edit")
async def cb_tg_thanks_edit(call: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(ThanksSG.waiting_text)
    await call.message.answer("Введите текст благодарности:", reply_markup=kb.cancel_kb("menu:thanks"))
    await call.answer()


@router.message(ThanksSG.waiting_text)
async def thanks_text(message: Message, state: FSMContext, config: Config) -> None:
    text = (message.text or "").strip()
    if text == "/cancel" or not text:
        await state.clear()
        await message.answer("Отменено.")
        return
    config.thanks_text = text
    config.save()
    await state.clear()
    await message.answer("Текст обновлён.", reply_markup=kb.thanks_kb(config))
