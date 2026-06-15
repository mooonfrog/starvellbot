import asyncio
import html
import io
import logging
import os
import shutil
import zipfile
from pathlib import Path
import httpx
from aiogram import F, Router
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import BufferedInputFile, CallbackQuery, FSInputFile, Message
from aiogram.enums import ParseMode
from src.configs.config import Config
from src.starvellapi import Account
from src.starvellapi.exceptions import StarvellAPIError
from src.tgbot import keyboards as kb
from src.tgbot.confirm import ConfirmStore, confirm_kb
from src.tgbot.states import AuthSG, BlacklistSG, GreetingSG, PluginUploadSG, QuickReplySG, ReplySG, ReviewReplySG, ThanksSG, TimezoneSG, TriggerEditSG, TriggerSG, WatermarkSG
from src.utils.worker import Worker
from version import VERSION
log = logging.getLogger('telegrambot.handlers')
router = Router()
LOG_FILE = Path('logs/log.log')

@router.message(F.text, lambda m: not Config.load().ddg5 and not m.text.startswith('/'))
async def prompt_ddg(message: Message, config: Config) -> None:
    if not config.is_authorized(message.from_user.id):
        return
    text = (message.text or '').strip()
    if len(text) > 5 and ' ' not in text:
        config.ddg5 = text
        config.save()
        await message.answer('✅ Cookie <b>__ddg5_</b> сохранена! Теперь нажми /restart для полного запуска бота.', parse_mode=ParseMode.HTML)
        return
    await message.answer('⚠️ Бот не запущен, так как отсутствует Cookie <code>__ddg5_</code> (DDoS-Guard bypass).\n\nПожалуйста, <b>пришлите значение этой Cookie</b> следующим сообщением.\n\n<i>Где взять: в браузере (F12 -> Application -> Cookies) после авторизации на starvell.com.</i>', parse_mode=ParseMode.HTML)

@router.callback_query(lambda c: not Config.load().ddg5 and not c.data.startswith('cf:'))
async def prompt_ddg_callback(call: CallbackQuery, config: Config) -> None:
    if not config.is_authorized(call.from_user.id):
        await call.answer('Нет доступа', show_alert=True)
        return
    await call.answer('⚠️ Бот ожидает настройки Cookie __ddg5_. Пришлите её в чат.', show_alert=True)
    await call.message.answer('⚠️ Бот ожидает настройки Cookie <code>__ddg5_</code>.\n\nПожалуйста, <b>пришлите значение этой Cookie</b> сообщением.', parse_mode=ParseMode.HTML)

async def _safe_edit(call: CallbackQuery, text: str, markup) -> None:
    try:
        await call.message.edit_text(text, reply_markup=markup)
    except Exception:
        await call.message.answer(text, reply_markup=markup)

def _mono(value: str) -> str:
    if not value:
        return '-'
    return f'<code>{html.escape(str(value))}</code>'
_AUTODELETE_HINT = '  (удалится через 5 сек)'

async def _delete_later(messages: list, delay: float=5.0) -> None:
    try:
        await asyncio.sleep(delay)
    except asyncio.CancelledError:
        return
    for msg in messages:
        try:
            await msg.delete()
        except Exception:
            pass

def _schedule_delete(*messages, delay: float=5.0) -> None:
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
        await message.answer(f'🏠 Главное меню\n\n🌟 <b>sᴛᴀʀᴠᴇʟʟʙᴏᴛ</b> - {VERSION}\n\n┏ <b>Разработчик</b>: @yusxe\n┗ <b>Плагины</b>: \n\nСнизу кнопки для управления ботом, воспользуйся ими. ↓', reply_markup=kb.main_menu(), parse_mode=ParseMode.HTML)
        return
    await state.set_state(AuthSG.waiting_password)
    await message.answer('Введите пароль:')

@router.message(AuthSG.waiting_password)
async def auth_password(message: Message, state: FSMContext, config: Config) -> None:
    text = (message.text or '').strip()
    if not config.telegram_password_hash or not config.telegram_password_hash.get('hash'):
        await message.answer('Пароль не задан. Установите его в конфиге через telegram_password_hash.')
        return
    ok, error = config.verify_password(message.from_user.id, text)
    if ok:
        config.authorize_user(message.from_user.id)
        await state.clear()
        await message.answer(f'🏠 Главное меню\n\n🌟 <b>sᴛᴀʀᴠᴇʟʟʙᴏᴛ</b> - {VERSION}\n\n┏ <b>Разработчик</b>: @yusxe\n┗ <b>Плагины</b>: @starvellplug \n\nСнизу кнопки для управления ботом, воспользуйся ими. ↓', reply_markup=kb.main_menu(), parse_mode=ParseMode.HTML)
        return
    await message.answer(error or 'Неверный пароль.')

@router.message(Command('logs'))
async def cmd_logs(message: Message, config: Config) -> None:
    if not config.is_authorized(message.from_user.id):
        return
    if not LOG_FILE.exists():
        await message.answer('Лог-файл пока не создан.')
        return
    try:
        await message.answer_document(FSInputFile(LOG_FILE), caption='Текущий лог StarvellBot')
    except Exception as e:
        log.exception('лог отдать не получилось')
        await message.answer(f'не отдалось: {e}')

@router.message(Command('restart'))
async def cmd_restart(message: Message, config: Config, confirm_store: ConfirmStore) -> None:
    if not config.is_authorized(message.from_user.id):
        return
    token = await confirm_store.create({'action': 'restart'})
    await message.answer('Уверены, что хотите перезапустить бота?', reply_markup=confirm_kb(token))

_UPDATE_ZIP_URL = 'https://github.com/mooonfrog/starvellbot/archive/refs/heads/main.zip'
_UPDATE_PROTECTED = {'configs', 'plugins', 'logs', 'data', '.venv', '.git', '__pycache__'}


def _project_root() -> Path:
    return Path(__file__).resolve().parents[2]


async def _download_update_zip() -> bytes:
    async with httpx.AsyncClient(follow_redirects=True, timeout=120.0) as client:
        resp = await client.get(_UPDATE_ZIP_URL)
        resp.raise_for_status()
        return resp.content


def _apply_update_zip(data: bytes) -> list[str]:
    root = _project_root()
    updated: list[str] = []
    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        for member in zf.infolist():
            if member.is_dir():
                continue
            parts = member.filename.split('/')[1:]
            if not parts or not parts[-1]:
                continue
            if parts[0] in _UPDATE_PROTECTED or '__pycache__' in parts:
                continue
            rel = Path(*parts)
            dest = root / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            with zf.open(member) as src, open(dest, 'wb') as out:
                shutil.copyfileobj(src, out)
            updated.append(str(rel))
    return updated


@router.message(Command('update'))
async def cmd_update(message: Message, config: Config) -> None:
    if not config.is_authorized(message.from_user.id):
        return
    status_msg = await message.answer('🔄 Скачиваю свежую версию с GitHub...')
    try:
        data = await _download_update_zip()
        updated = await asyncio.to_thread(_apply_update_zip, data)
    except Exception as e:
        log.exception('обновление не удалось')
        await status_msg.edit_text(f'❌ Ошибка обновления: <code>{html.escape(str(e))}</code>')
        return
    if not updated:
        await status_msg.edit_text('✅ Архив скачан, но обновлять было нечего.')
        return
    preview = '\n'.join(f'• <code>{html.escape(f)}</code>' for f in updated[:15])
    more = f'\n…и ещё {len(updated) - 15} файл(ов)' if len(updated) > 15 else ''
    await status_msg.edit_text(
        f'✅ Обновлено файлов: <b>{len(updated)}</b>\n\n{preview}{more}\n\n'
        'configs / plugins / data / logs сохранены.\n'
        'Нажми /restart, чтобы применить изменения.'
    )

@router.callback_query(F.data.startswith('cf:n:'))
async def cb_confirm_no(call: CallbackQuery, confirm_store: ConfirmStore) -> None:
    token = call.data.split(':', 2)[2]
    await confirm_store.pop(token)
    try:
        await call.message.edit_text('Действие отменено.')
    except Exception:
        pass
    await call.answer()

@router.callback_query(F.data.startswith('cf:y:'))
async def cb_confirm_yes(call: CallbackQuery, confirm_store: ConfirmStore, config: Config, app=None) -> None:
    token = call.data.split(':', 2)[2]
    payload = await confirm_store.pop(token)
    if payload is None:
        await call.answer('Запрос истёк или уже выполнен', show_alert=True)
        try:
            await call.message.edit_text('Запрос подтверждения истёк.')
        except Exception:
            pass
        return
    action = payload.get('action')
    if action == 'restart':
        try:
            await call.message.edit_text('Перезапускаю бота...')
        except Exception:
            pass
        log.warning('/restart подтверждён, user_id=%s', call.from_user.id)
        os.environ['STARVELLBOT_RESTART'] = '1'
        loop = asyncio.get_running_loop()
        loop.call_later(0.5, lambda: loop.stop())
        await call.answer()
        return
    if action == 'plugin_delete':
        uuid = payload.get('uuid')
        if app is None or uuid not in getattr(app, 'plugins', {}):
            await call.answer('Плагин не найден', show_alert=True)
            return
        plugin = app.plugins[uuid]
        try:
            Path(plugin.path).unlink(missing_ok=True)
        except Exception as e:
            await call.answer(f'Ошибка удаления: {e}', show_alert=True)
            return
        try:
            await call.message.edit_text(f'<b>{plugin.name}</b>\nФайл удалён. Нажми /restart, чтобы перечитать плагины.', reply_markup=kb.back_kb('menu:plugins'))
        except Exception:
            pass
        await call.answer('Удалено')
        return
    await call.answer('Неизвестное действие', show_alert=True)

@router.callback_query(F.data.startswith('menu:main'))
async def cb_main(call: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    page = 1
    parts = call.data.split(':')
    if len(parts) == 3:
        try:
            page = int(parts[2])
        except ValueError:
            page = 1
    await _safe_edit(call, f'🏠 Главное меню\n\n🌟 <b>sᴛᴀʀᴠᴇʟʟʙᴏᴛ</b> - {VERSION}\n\n┏ <b>Разработчик</b>: @yusxe\n┗ <b>Плагины</b>: \n\nСнизу кнопки для управления ботом, воспользуйся ими. ↓', kb.main_menu(page))
    await call.answer()

@router.callback_query(F.data.startswith('cancel:'))
async def cb_cancel(call: CallbackQuery, state: FSMContext) -> None:
    target = call.data.split(':', 1)[1] or 'menu:main'
    await state.clear()
    try:
        await call.message.delete()
    except Exception:
        pass
    if target == 'menu:main':
        try:
            await call.bot.send_message(call.message.chat.id, '🩵 starvellbot\n👇 Воспользуйтесь кнопками ниже', reply_markup=kb.main_menu())
        except Exception:
            pass
    await call.answer('Отменено')

@router.callback_query(F.data == 'menu:status')
async def cb_status(call: CallbackQuery, account: Account) -> None:
    try:
        profile = await account.get_profile()
        status_online = "🟢 В сети" if profile.user.is_online else "🔴 Офлайн"
        selling_status = "✅ Да" if profile.is_selling_enabled else "❌ Нет"
        rating_str = f"{profile.user.rating}★" if profile.user.rating else "Нет оценок"
        text = f'<b>📊 Статистика профиля</b>\n\n<b>Пользователь:</b> {profile.user.username} (<code>{profile.user.id}</code>)\n<b>Статус:</b> {status_online}\n<b>Продажи разрешены:</b> {selling_status}\n\n<b>💰 Финансы</b>\nБаланс: <code>{profile.balance:.2f}₽</code>\nНа удержании: <code>{profile.held:.2f}₽</code>\n\n<b>📈 Активность</b>\nПродажи: <code>{profile.sales_orders}</code>\nПокупки: <code>{profile.purchase_orders}</code>\nОтзывы: <code>{profile.user.reviews_count}</code> ({rating_str})\n\n<b>💬 Сообщения</b>\nНепрочитанных чатов: <code>{len(profile.unread_chat_ids)}</code>'
    except StarvellAPIError as e:
        text = f'Ошибка: {e}'
    await _safe_edit(call, text, kb.back_kb())
    await call.answer()

def _triggers_text(config: Config) -> str:
    text = '<b>💬 Авто-ответы</b>\nЕсли в сообщении встретится ключ - отправлю ответ.\n\n<b>Доступные теги:</b>\n• <code>{username}</code> — ник покупателя'
    if config.triggers:
        lines = [f'• {_mono(k)} → {_mono(v)}' for k, v in config.triggers.items()]
        text = text + '\n\n' + '\n'.join(lines)
    return text

async def _show_triggers(call: CallbackQuery, config: Config) -> None:
    await _safe_edit(call, _triggers_text(config), kb.triggers_kb(config))

@router.callback_query(F.data == 'menu:triggers')
async def cb_triggers(call: CallbackQuery, config: Config) -> None:
    await _show_triggers(call, config)
    await call.answer()

@router.callback_query(F.data.startswith('trig:open:'))
async def cb_trig_open(call: CallbackQuery, config: Config) -> None:
    key = call.data.split(':', 2)[2]
    response = config.triggers.get(key)
    if response is None:
        await call.answer('Авто-ответ уже удалён', show_alert=True)
        await _show_triggers(call, config)
        return
    text = f'<b>💬 Авто-ответ</b>\n\n<b>Ключ:</b> {_mono(key)}\n<b>Ответ:</b> {_mono(response)}'
    await _safe_edit(call, text, kb.trigger_card_kb(key))
    await call.answer()

@router.callback_query(F.data.startswith('trig:edit:'))
async def cb_trig_edit(call: CallbackQuery, state: FSMContext) -> None:
    key = call.data.split(':', 2)[2]
    await state.set_state(TriggerEditSG.waiting_response)
    await state.update_data(key=key)
    await call.message.answer(f'Введите новый ответ для <code>{key}</code>:', reply_markup=kb.cancel_kb('menu:triggers'))
    await call.answer()

@router.message(TriggerEditSG.waiting_response)
async def trig_edit_response(message: Message, state: FSMContext, config: Config) -> None:
    text = (message.text or '').strip()
    data = await state.get_data()
    key = data.get('key', '')
    if text == '/cancel' or not text or (not key):
        await state.clear()
        await message.answer('Отменено.', reply_markup=kb.main_menu())
        return
    config.set_trigger(key, text)
    await state.clear()
    await message.answer(f'Ответ для <code>{key}</code> обновлён.', reply_markup=kb.triggers_kb(config))

@router.callback_query(F.data == 'trig:add')
async def cb_trig_add(call: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(TriggerSG.waiting_key)
    await call.message.answer('Введите ключевое слово:', reply_markup=kb.cancel_kb('menu:triggers'))
    await call.answer()

@router.message(TriggerSG.waiting_key)
async def trig_key(message: Message, state: FSMContext) -> None:
    text = (message.text or '').strip()
    if text == '/cancel':
        await state.clear()
        await message.answer('Отменено.', reply_markup=kb.main_menu())
        return
    await state.update_data(key=text)
    await state.set_state(TriggerSG.waiting_response)
    await message.answer('Теперь введите ответ:', reply_markup=kb.cancel_kb('menu:triggers'))

@router.message(TriggerSG.waiting_response)
async def trig_response(message: Message, state: FSMContext, config: Config) -> None:
    data = await state.get_data()
    key = data.get('key', '')
    response = (message.text or '').strip()
    if not key or not response:
        await state.clear()
        await message.answer('Пустые значения, отмена.', reply_markup=kb.main_menu())
        return
    config.set_trigger(key, response)
    await state.clear()
    await message.answer(f'Авто-ответ <code>{key}</code> сохранён.', reply_markup=kb.triggers_kb(config))

@router.callback_query(F.data.startswith('trig:rm:'))
async def cb_trig_rm(call: CallbackQuery, config: Config) -> None:
    key = call.data.split(':', 2)[2]
    config.remove_trigger(key)
    await _show_triggers(call, config)
    await call.answer('Удалено')

@router.callback_query(F.data.startswith('msg:reply:'))
async def cb_msg_reply(call: CallbackQuery, state: FSMContext) -> None:
    chat_id = call.data.split(':', 2)[2]
    await state.set_state(ReplySG.waiting_text)
    prompt = await call.message.answer(f'Введите ответ в чат {_mono(chat_id)}:{_AUTODELETE_HINT}', parse_mode='HTML', reply_markup=kb.cancel_kb())
    await state.update_data(chat_id=chat_id, prompt_chat_id=prompt.chat.id, prompt_message_id=prompt.message_id)
    await call.answer()

async def _delete_by_id(bot, chat_id: int, message_id: int) -> None:
    try:
        await bot.delete_message(chat_id, message_id)
    except Exception:
        pass

async def _delete_prompt_later(bot, chat_id: int, message_id: int, delay: float=5.0) -> None:
    try:
        await asyncio.sleep(delay)
    except asyncio.CancelledError:
        return
    await _delete_by_id(bot, chat_id, message_id)

@router.message(ReplySG.waiting_text)
async def msg_reply_text(message: Message, state: FSMContext, worker: Worker) -> None:
    data = await state.get_data()
    chat_id = data.get('chat_id')
    prompt_chat_id = data.get('prompt_chat_id')
    prompt_message_id = data.get('prompt_message_id')
    if not chat_id:
        await state.clear()
        return
    if message.text:
        text = message.text.strip()
        if text == '/cancel':
            await state.clear()
            cancel_msg = await message.answer(f'Отменено.{_AUTODELETE_HINT}')
            _schedule_delete(message, cancel_msg)
            if prompt_chat_id and prompt_message_id:
                asyncio.create_task(_delete_prompt_later(message.bot, prompt_chat_id, prompt_message_id))
            return
        sent = await worker.safe_send_message(chat_id, text)
    elif message.photo:
        photo = message.photo[-1]
        try:
            file = await message.bot.get_file(photo.file_id)
            obj = await message.bot.download_file(file.file_path)
            image_bytes = obj.read()
            sent = await worker.safe_send_image(chat_id, image_bytes)
        except Exception as e:
            log.error('не удалось обработать фото: %s', e)
            sent = False
    else:
        await message.answer('Пришлите текст или фото для ответа.')
        return
    await state.clear()
    if sent:
        confirm = await message.answer(f'Отправлено.{_AUTODELETE_HINT}')
    else:
        confirm = await message.answer(f'Не удалось отправить.{_AUTODELETE_HINT}')
    _schedule_delete(message, confirm)
    if prompt_chat_id and prompt_message_id:
        asyncio.create_task(_delete_prompt_later(message.bot, prompt_chat_id, prompt_message_id))

@router.callback_query(F.data == 'msg:hide')
async def cb_msg_hide(call: CallbackQuery) -> None:
    try:
        await call.message.delete()
    except Exception:
        try:
            await call.message.edit_reply_markup(reply_markup=None)
        except Exception:
            pass
    await call.answer()

@router.callback_query(F.data == 'menu:blacklist')
async def cb_blacklist(call: CallbackQuery, config: Config) -> None:
    text = '<b>🚫 Чёрный список</b>\n\nНики (без @). Тапни по нику в меню ниже, чтобы удалить его.'
    if config.blacklist_usernames:
        text += '\n\n' + '\n'.join((f'• {_mono(u)}' for u in config.blacklist_usernames))
    await _safe_edit(call, text, kb.blacklist_kb(config))
    await call.answer()

@router.callback_query(F.data == 'bl:add')
async def cb_bl_add(call: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(BlacklistSG.waiting_add)
    await call.message.answer('Введите ник для блокировки:', reply_markup=kb.cancel_kb('menu:blacklist'))
    await call.answer()

@router.message(BlacklistSG.waiting_add)
async def bl_add(message: Message, state: FSMContext, config: Config) -> None:
    username = (message.text or '').strip()
    if not username or username == '/cancel':
        await state.clear()
        await message.answer('Отменено.', reply_markup=kb.main_menu())
        return
    config.add_blacklist(username)
    await state.clear()
    await message.answer(f"Ник {username.lstrip('@').lower()} добавлен в ЧС.", reply_markup=kb.blacklist_kb(config))

@router.callback_query(F.data.startswith('bl:rm:'))
async def cb_bl_rm(call: CallbackQuery, config: Config) -> None:
    username = call.data.split(':', 2)[2]
    config.remove_blacklist(username)
    await _safe_edit(call, 'Ник удалён из ЧС.', kb.blacklist_kb(config))
    await call.answer()

@router.callback_query(F.data == 'menu:reviews')
async def cb_reviews(call: CallbackQuery, config: Config) -> None:
    text = '<b>⭐ Авто-ответ на отзывы</b>\n\nЗдесь ты можешь настроить автоматические ответы на отзывы.\n\n<b>Доступные теги:</b>\n• <code>{username}</code> — ник покупателя\n• <code>{rating}</code> — оценка (число)'
    await _safe_edit(call, text, kb.reviews_kb(config))
    await call.answer()

@router.callback_query(F.data.startswith('rev:open:'))
async def cb_rev_open(call: CallbackQuery, config: Config) -> None:
    rating = call.data.split(':')[2]
    reply = config.review_replies.get(str(rating))
    stars = '⭐' * int(rating)
    if not reply:
        await call.answer(f'Ответ для {rating}★ не настроен', show_alert=True)
        return
    text = f'<b>⭐ Ответ на {rating}★</b>\n\n<b>Текст:</b>\n{_mono(reply)}'
    await _safe_edit(call, text, kb.reviews_kb(config))
    await call.answer()

@router.callback_query(F.data.startswith('rev:toggle_rating:'))
async def cb_rev_toggle_rating(call: CallbackQuery, config: Config) -> None:
    rating = call.data.split(':')[2]
    if not config.review_replies.get(str(rating)):
        await call.answer(f'Сначала настройте текст ответа для {rating}★', show_alert=True)
        return
    config.toggle_review_rating(int(rating))
    await _safe_edit(call, call.message.text, kb.reviews_kb(config))
    await call.answer()

@router.callback_query(F.data.startswith('rev:edit:'))
async def cb_rev_edit(call: CallbackQuery, state: FSMContext) -> None:
    rating = call.data.split(':')[2]
    await state.set_state(ReviewReplySG.waiting_text)
    await state.update_data(rating=rating)
    await call.message.answer(f'Введите текст ответа для {rating}★:', reply_markup=kb.cancel_kb('menu:reviews'))
    await call.answer()

@router.message(ReviewReplySG.waiting_text)
async def rev_text(message: Message, state: FSMContext, config: Config) -> None:
    text = (message.text or '').strip()
    data = await state.get_data()
    rating = data.get('rating')
    if not text or text == '/cancel' or (not rating):
        await state.clear()
        await message.answer('Отменено.', reply_markup=kb.main_menu())
        return
    config.review_replies[str(rating)] = text
    config.save()
    await state.clear()
    await message.answer('Сохранено.', reply_markup=kb.reviews_kb(config))
_TOGGLES_TEXT = '<b>Переключатели</b>\nГлобальные настройки бота. Тапни по пункту, чтобы переключить.'

async def _show_toggles(call: CallbackQuery, config: Config) -> None:
    await _safe_edit(call, _TOGGLES_TEXT, kb.toggles_kb(config))

@router.callback_query(F.data == 'menu:toggles')
async def cb_toggles(call: CallbackQuery, state: FSMContext, config: Config) -> None:
    await state.clear()
    await _show_toggles(call, config)
    await call.answer()

@router.callback_query(F.data == 'menu:notify')
async def cb_notify(call: CallbackQuery, config: Config) -> None:
    text = '<b>Уведомления в Telegram</b>\nКакие события присылать в чат с ботом.'
    await _safe_edit(call, text, kb.notify_kb(config))
    await call.answer()

@router.callback_query(F.data.startswith('ntf:'))
async def cb_notify_toggle(call: CallbackQuery, config: Config) -> None:
    key = call.data.split(':', 1)[1]
    attr_map = {
        'messages': 'notify_messages',
        'orders': 'notify_orders',
        'reviews': 'notify_reviews',
    }
    attr = attr_map.get(key)
    if attr is None:
        await call.answer('Неизвестная настройка', show_alert=True)
        return
    setattr(config, attr, not getattr(config, attr))
    config.save()
    await cb_notify(call, config)

@router.callback_query(F.data == 'menu:thanks')
async def cb_thanks(call: CallbackQuery, config: Config) -> None:
    text = f'<b>🙏 Авто-благодарность</b>\nОтправляется покупателю в чат, когда заказ завершается.\n\n<b>Доступные теги:</b>\n• <code>{{username}}</code> — ник покупателя\n• <code>{{order_id}}</code> — ID заказа\n\n<b>Текст:</b> {_mono(config.thanks_text)}'
    await _safe_edit(call, text, kb.thanks_kb(config))
    await call.answer()

@router.callback_query(F.data == 'menu:watermark')
async def cb_watermark(call: CallbackQuery, config: Config) -> None:
    text = f'<b>Watermark</b>\nДописывается ко всем исходящим сообщениям бота в Starvell.\n\nТекст: {_mono(config.watermark_text)}'
    await _safe_edit(call, text, kb.watermark_kb(config))
    await call.answer()

@router.callback_query(F.data == 'menu:greeting')
async def cb_greeting(call: CallbackQuery, config: Config) -> None:
    text = f'<b>👋 Приветствие новых чатов</b>\nОтправляется один раз при первом сообщении от покупателя.\n\n<b>Доступные теги:</b>\n• <code>{{username}}</code> — ник покупателя\n\n<b>Текст:</b> {_mono(config.greeting_text)}'
    await _safe_edit(call, text, kb.greeting_kb(config))
    await call.answer()

@router.callback_query(F.data == 'tg:greeting')
async def cb_tg_greeting(call: CallbackQuery, config: Config) -> None:
    config.greeting_enabled = not config.greeting_enabled
    config.save()
    await cb_greeting(call, config)

@router.callback_query(F.data == 'tg:greeting_edit')
async def cb_tg_greeting_edit(call: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(GreetingSG.waiting_text)
    await call.message.answer('Введите текст приветствия:', reply_markup=kb.cancel_kb('menu:greeting'))
    await call.answer()

@router.message(GreetingSG.waiting_text)
async def greeting_text(message: Message, state: FSMContext, config: Config) -> None:
    text = (message.text or '').strip()
    if text == '/cancel' or not text:
        await state.clear()
        await message.answer('Отменено.', reply_markup=kb.main_menu())
        return
    config.greeting_text = text
    config.save()
    await state.clear()
    await message.answer('Текст обновлён.', reply_markup=kb.greeting_kb(config))

@router.callback_query(F.data == 'tg:wm')
async def cb_tg_wm(call: CallbackQuery, config: Config) -> None:
    config.watermark_enabled = not config.watermark_enabled
    config.save()
    await cb_watermark(call, config)

@router.callback_query(F.data == 'tg:ok')
async def cb_tg_ok(call: CallbackQuery, config: Config) -> None:
    config.online_keeper = not config.online_keeper
    config.save()
    await _show_toggles(call, config)
    await call.answer('Изменение применится после перезапуска бота')

@router.callback_query(F.data == 'tg:autoread')
async def cb_tg_autoread(call: CallbackQuery, config: Config) -> None:
    config.auto_read_chats = not config.auto_read_chats
    config.save()
    await _show_toggles(call, config)
    await call.answer()

@router.callback_query(F.data == 'tg:wm_edit')
async def cb_tg_wm_edit(call: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(WatermarkSG.waiting_text)
    await call.message.answer('Введите текст watermark:', reply_markup=kb.cancel_kb('menu:watermark'))
    await call.answer()

@router.message(WatermarkSG.waiting_text)
async def watermark_text(message: Message, state: FSMContext, config: Config) -> None:
    text = (message.text or '').strip()
    if text == '/cancel':
        await state.clear()
        await message.answer('Отменено.', reply_markup=kb.main_menu())
        return
    config.watermark_text = text
    config.save()
    await state.clear()
    await message.answer('Watermark обновлён.', reply_markup=kb.watermark_kb(config))

@router.callback_query(F.data == 'tg:tz_edit')
async def cb_tg_tz_edit(call: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(TimezoneSG.waiting_value)
    await call.message.answer('Введите таймзону (например, Europe/Moscow):', reply_markup=kb.cancel_kb('menu:toggles'))
    await call.answer()

@router.message(TimezoneSG.waiting_value)
async def tz_value(message: Message, state: FSMContext, config: Config, worker: Worker) -> None:
    text = (message.text or '').strip()
    if text == '/cancel':
        await state.clear()
        await message.answer('Отменено.', reply_markup=kb.main_menu())
        return
    config.timezone = text
    config.save()
    worker.reload_settings()
    await state.clear()
    await message.answer('Таймзона обновлена.', reply_markup=kb.toggles_kb(config))

@router.callback_query(F.data.startswith('order:done:'))
async def cb_order_done(call: CallbackQuery, account: Account) -> None:
    order_id = call.data.split(':', 2)[2]
    try:
        await account.mark_order_completed(order_id)
        await call.answer('Подтверждено', show_alert=True)
    except StarvellAPIError as e:
        await call.answer(f'Ошибка: {e}', show_alert=True)

@router.callback_query(F.data.startswith('order:refund:'))
async def cb_order_refund(call: CallbackQuery, account: Account) -> None:
    order_id = call.data.split(':', 2)[2]
    try:
        await account.refund_order(order_id)
        await call.answer('Возврат оформлен', show_alert=True)
    except StarvellAPIError as e:
        await call.answer(f'Ошибка: {e}', show_alert=True)

@router.callback_query(F.data == 'menu:plugins')
async def cb_plugins(call: CallbackQuery, app=None) -> None:
    if app is None or not getattr(app, 'plugins', None):
        text = '<b>Плагины</b>\nПоложи .py-файл сюда через кнопку ниже или в папку <code>plugins/</code> и сделай /restart.'
        await _safe_edit(call, text, kb.empty_plugins_kb())
        await call.answer()
        return
    text = f'<b>Плагины</b>\nЗагружено: {len(app.plugins)}. Тапни по плагину, чтобы управлять.'
    await _safe_edit(call, text, kb.plugins_kb(app.plugins))
    await call.answer()

def _plugin_card_text(plugin) -> str:
    status = '🟢 Включён' if plugin.enabled else '🔴 Выключен'
    lines = [f'<b>🧩 {plugin.name}</b> v{plugin.version}\n', f'<b>Статус:</b> {status}', f'<b>Автор:</b> {plugin.credits}', f'<b>UUID:</b> <code>{plugin.uuid}</code>', f'<b>Файл:</b> <code>{plugin.path}</code>']
    if plugin.error:
        lines.append(f'\n<b>⚠️ Ошибки:</b> {plugin.error_count}')
        lines.append(f'<b>Последняя:</b> <code>{html.escape(str(plugin.error)[:300])}</code>')
    lines.append(f'\n<b>Описание:</b>\n{plugin.description}')
    return '\n'.join(lines)

@router.callback_query(F.data.startswith('pl:open:'))
async def cb_plugin_open(call: CallbackQuery, app=None) -> None:
    uuid = call.data.split(':', 2)[2]
    if app is None or uuid not in app.plugins:
        await call.answer('Плагин не найден', show_alert=True)
        return
    plugin = app.plugins[uuid]
    await _safe_edit(call, _plugin_card_text(plugin), kb.plugin_card_kb(uuid, plugin.enabled, has_error=bool(plugin.error)))
    await call.answer()

@router.callback_query(F.data.startswith('pl:toggle:'))
async def cb_plugin_toggle(call: CallbackQuery, config: Config, app=None) -> None:
    uuid = call.data.split(':', 2)[2]
    if app is None or uuid not in app.plugins:
        await call.answer('Плагин не найден', show_alert=True)
        return
    enabled = config.toggle_plugin(uuid)
    app.plugins[uuid].enabled = enabled
    await call.answer('Включён' if enabled else 'Выключен')
    plugin = app.plugins[uuid]
    await _safe_edit(call, _plugin_card_text(plugin), kb.plugin_card_kb(uuid, plugin.enabled, has_error=bool(plugin.error)))

@router.callback_query(F.data.startswith('pl:reset_err:'))
async def cb_plugin_reset_err(call: CallbackQuery, app=None) -> None:
    uuid = call.data.split(':', 2)[2]
    if app is None or uuid not in app.plugins:
        await call.answer('Плагин не найден', show_alert=True)
        return
    plugin = app.plugins[uuid]
    plugin.error = None
    plugin.error_count = 0
    await call.answer('Ошибка сброшена')
    await _safe_edit(call, _plugin_card_text(plugin), kb.plugin_card_kb(uuid, plugin.enabled, has_error=False))

@router.callback_query(F.data == 'pl:upload')
async def cb_plugin_upload(call: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(PluginUploadSG.waiting_file)
    await call.message.answer('Пришли .py-файл плагина следующим сообщением.', reply_markup=kb.cancel_kb('menu:plugins'))
    await call.answer()

@router.message(PluginUploadSG.waiting_file)
async def plugin_upload_file(message: Message, state: FSMContext, config: Config, app=None) -> None:
    text = (message.text or '').strip()
    if text == '/cancel':
        await state.clear()
        await message.answer('Отменено.')
        return
    if message.document is None:
        await message.answer('Жду файл .py. Пришли как документ.')
        return
    name = message.document.file_name or ''
    if not name.endswith('.py'):
        await message.answer('Это не .py файл.')
        return
    plugins_dir = Path('plugins')
    plugins_dir.mkdir(parents=True, exist_ok=True)
    safe_name = Path(name).name
    target = plugins_dir / safe_name
    if target.exists():
        target = plugins_dir / f'{target.stem}_{int(asyncio.get_running_loop().time())}.py'
    try:
        bot = message.bot
        file = await bot.get_file(message.document.file_id)
        await bot.download_file(file.file_path, destination=target)
    except Exception as e:
        log.exception('плагин не скачался')
        await state.clear()
        await message.answer(f'не скачался: {e}')
        return
    await state.clear()
    await message.answer(f'Плагин сохранён как <code>{target}</code>.\nДля активации нажми /restart.')

@router.callback_query(F.data.startswith('pl:delete:'))
async def cb_plugin_delete(call: CallbackQuery, config: Config, confirm_store: ConfirmStore, app=None) -> None:
    uuid = call.data.split(':', 2)[2]
    if app is None or uuid not in app.plugins:
        await call.answer('Плагин не найден', show_alert=True)
        return
    plugin = app.plugins[uuid]
    token = await confirm_store.create({'action': 'plugin_delete', 'uuid': uuid})
    text = f'Удалить файл плагина <b>{plugin.name}</b>?\n<code>{plugin.path}</code>'
    try:
        await call.message.edit_text(text, reply_markup=confirm_kb(token))
    except Exception:
        await call.message.answer(text, reply_markup=confirm_kb(token))
    await call.answer()

@router.callback_query(F.data.startswith('qr:'))
async def cb_quick_reply(call: CallbackQuery, config: Config, worker: Worker) -> None:
    parts = call.data.split(':', 2)
    if len(parts) != 3:
        await call.answer('Некорректные данные', show_alert=True)
        return
    try:
        idx = int(parts[1])
    except ValueError:
        await call.answer('Некорректный индекс', show_alert=True)
        return
    chat_id = parts[2]
    if idx < 0 or idx >= len(config.quick_replies):
        await call.answer('Шаблон удалён', show_alert=True)
        return
    sent = await worker.safe_send_message(chat_id, config.quick_replies[idx])
    await call.answer('Отправлено' if sent else 'Не получилось', show_alert=not sent)
    try:
        await call.message.edit_reply_markup(reply_markup=kb.message_actions_kb(chat_id, bool(config.quick_replies)))
    except Exception:
        pass

@router.callback_query(F.data.startswith('qrlist:'))
async def cb_quick_reply_list(call: CallbackQuery, config: Config) -> None:
    chat_id = call.data.split(':', 1)[1]
    if not config.quick_replies:
        await call.answer('Шаблоны не заданы', show_alert=True)
        return
    try:
        await call.message.edit_reply_markup(reply_markup=kb.quick_replies_for_chat_kb(chat_id, config.quick_replies))
    except Exception:
        pass
    await call.answer()

@router.callback_query(F.data.startswith('qrback:'))
async def cb_quick_reply_back(call: CallbackQuery, config: Config) -> None:
    chat_id = call.data.split(':', 1)[1]
    try:
        await call.message.edit_reply_markup(reply_markup=kb.message_actions_kb(chat_id, bool(config.quick_replies)))
    except Exception:
        pass
    await call.answer()

@router.callback_query(F.data == 'menu:quickreplies')
async def cb_quickreplies(call: CallbackQuery, config: Config) -> None:
    text = '<b>Шаблоны ответов</b>\nПоявляются под уведомлением о новом сообщении в TG.'
    if config.quick_replies:
        text += '\n\n' + '\n'.join((f'• {_mono(t)}' for t in config.quick_replies))
    await _safe_edit(call, text, kb.quick_replies_kb(config.quick_replies))
    await call.answer()

@router.callback_query(F.data == 'qrcfg:add')
async def cb_qrcfg_add(call: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(QuickReplySG.waiting_text)
    await call.message.answer('Введите текст шаблона:', reply_markup=kb.cancel_kb('menu:quickreplies'))
    await call.answer()

@router.message(QuickReplySG.waiting_text)
async def qrcfg_text(message: Message, state: FSMContext, config: Config) -> None:
    text = (message.text or '').strip()
    if text == '/cancel' or not text:
        await state.clear()
        await message.answer('Отменено.', reply_markup=kb.main_menu())
        return
    config.add_quick_reply(text)
    await state.clear()
    await message.answer('Шаблон добавлен.', reply_markup=kb.quick_replies_kb(config.quick_replies))

@router.callback_query(F.data.startswith('qrcfg:rm:'))
async def cb_qrcfg_rm(call: CallbackQuery, config: Config) -> None:
    try:
        idx = int(call.data.split(':', 2)[2])
    except ValueError:
        await call.answer('Некорректные данные', show_alert=True)
        return
    config.remove_quick_reply(idx)
    text = '<b>Шаблоны ответов</b>'
    if config.quick_replies:
        text += '\n\n' + '\n'.join((f'• {_mono(t)}' for t in config.quick_replies))
    await _safe_edit(call, text, kb.quick_replies_kb(config.quick_replies))
    await call.answer('Удалено')

@router.callback_query(F.data == 'tg:thanks')
async def cb_tg_thanks(call: CallbackQuery, config: Config) -> None:
    config.thanks_after_complete_enabled = not config.thanks_after_complete_enabled
    config.save()
    await cb_thanks(call, config)

@router.callback_query(F.data == 'tg:thanks_edit')
async def cb_tg_thanks_edit(call: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(ThanksSG.waiting_text)
    await call.message.answer('Введите текст благодарности:', reply_markup=kb.cancel_kb('menu:thanks'))
    await call.answer()

@router.message(ThanksSG.waiting_text)
async def thanks_text(message: Message, state: FSMContext, config: Config) -> None:
    text = (message.text or '').strip()
    if text == '/cancel' or not text:
        await state.clear()
        await message.answer('Отменено.')
        return
    config.thanks_text = text
    config.save()
    await state.clear()
    await message.answer('Текст обновлён.', reply_markup=kb.thanks_kb(config))
