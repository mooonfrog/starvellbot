from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from src.configs.config import Config

def _row(*buttons: InlineKeyboardButton) -> list[InlineKeyboardButton]:
    return list(buttons)

def back_button(target: str='menu:main') -> InlineKeyboardButton:
    return InlineKeyboardButton(text='👉 Назад', callback_data=target)

def cancel_kb(target: str='menu:main') -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text='❌ Отмена', callback_data=f'cancel:{target}')]])

def back_kb(target: str='menu:main') -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[back_button(target)]])

def main_menu(page: int=1) -> InlineKeyboardMarkup:
    if page == 1:
        return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text='📊 Статистика', callback_data='menu:status')], [InlineKeyboardButton(text='🧩 Плагины', callback_data='menu:plugins')], [InlineKeyboardButton(text='💬 Авто-ответы', callback_data='menu:triggers')], [InlineKeyboardButton(text='➡️ Вперёд', callback_data='menu:main:2')]])
    return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text='🚫 Чёрный список', callback_data='menu:blacklist')], [InlineKeyboardButton(text='⭐ Авто-ответ на отзывы', callback_data='menu:reviews')], [InlineKeyboardButton(text='🔔 Уведомления', callback_data='menu:notify')], [InlineKeyboardButton(text='🔧 Переключатели', callback_data='menu:toggles')], [InlineKeyboardButton(text='⬅️ Назад', callback_data='menu:main:1')]])

def _toggle_label(name: str, on: bool) -> str:
    mark = '🟢' if on else '🔴'
    return f'{mark} {name}'

def toggles_kb(config: Config) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text='📋 Шаблоны ответов', callback_data='menu:quickreplies')], [InlineKeyboardButton(text='👋 Приветствие новых чатов', callback_data='menu:greeting')], [InlineKeyboardButton(text='🙏 Авто-благодарность', callback_data='menu:thanks')], [InlineKeyboardButton(text='✏️ Watermark', callback_data='menu:watermark')], [InlineKeyboardButton(text=_toggle_label('OnlineKeeper', config.online_keeper), callback_data='tg:ok')], [InlineKeyboardButton(text=_toggle_label('Авто-чтение чатов', config.auto_read_chats), callback_data='tg:autoread')], [InlineKeyboardButton(text=f'🌍 Таймзона: {config.timezone}', callback_data='tg:tz_edit')], [back_button('menu:main:2')]])

def greeting_kb(config: Config) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text=_toggle_label('Включено', config.greeting_enabled), callback_data='tg:greeting')], [InlineKeyboardButton(text='✏️ Изменить текст', callback_data='tg:greeting_edit')], [back_button('menu:toggles')]])

def thanks_kb(config: Config) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text=_toggle_label('Включена', config.thanks_after_complete_enabled), callback_data='tg:thanks')], [InlineKeyboardButton(text='✏️ Изменить текст', callback_data='tg:thanks_edit')], [back_button('menu:toggles')]])

def watermark_kb(config: Config) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text=_toggle_label('Включён', config.watermark_enabled), callback_data='tg:wm')], [InlineKeyboardButton(text='✏️ Изменить текст', callback_data='tg:wm_edit')], [back_button('menu:toggles')]])

def _notify_label(name: str, on: bool) -> str:
    mark = '🔔' if on else '🔕'
    return f'{mark} {name}'

def notify_kb(config: Config) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=_notify_label('Новое сообщение', config.notify_messages), callback_data='ntf:messages'), InlineKeyboardButton(text=_notify_label('Новый заказ', config.notify_orders), callback_data='ntf:orders')],
        [InlineKeyboardButton(text=_notify_label('Новый отзыв', config.notify_reviews), callback_data='ntf:reviews')],
        [back_button('menu:main:2')]
    ])

def message_actions_kb(chat_id: str, has_quick_replies: bool=False) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    if has_quick_replies:
        rows.append([InlineKeyboardButton(text='📋 Шаблоны ответов', callback_data=f'qrlist:{chat_id}')])
    rows.append([InlineKeyboardButton(text='💬 Ответить', callback_data=f'msg:reply:{chat_id}')])
    rows.append([InlineKeyboardButton(text='🌐 Открыть чат', url=f'https://starvell.com/chat/{chat_id}')])
    return InlineKeyboardMarkup(inline_keyboard=rows)

def quick_replies_for_chat_kb(chat_id: str, quick_replies: list[str]) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    for idx, text in enumerate(quick_replies[:25]):
        rows.append([InlineKeyboardButton(text=f'🔁 {text[:40]}', callback_data=f'qr:{idx}:{chat_id}')])
    rows.append([InlineKeyboardButton(text='🔙 Назад', callback_data=f'qrback:{chat_id}')])
    return InlineKeyboardMarkup(inline_keyboard=rows)

def quick_replies_kb(quick_replies: list[str]) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    for idx, text in enumerate(quick_replies[:25]):
        rows.append([InlineKeyboardButton(text=f'❌ {text[:30]}', callback_data=f'qrcfg:rm:{idx}')])
    rows.append([InlineKeyboardButton(text='➕ Добавить', callback_data='qrcfg:add')])
    rows.append([back_button('menu:toggles')])
    return InlineKeyboardMarkup(inline_keyboard=rows)

def triggers_kb(config: Config) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    trigger_keys = list(config.triggers.keys())[:24]
    for i in range(0, len(trigger_keys), 2):
        row = [InlineKeyboardButton(text=f'💬 {trigger_keys[i]}', callback_data=f'trig:open:{trigger_keys[i]}')]
        if i + 1 < len(trigger_keys):
            row.append(InlineKeyboardButton(text=f'💬 {trigger_keys[i + 1]}', callback_data=f'trig:open:{trigger_keys[i + 1]}'))
        rows.append(row)
    rows.append([InlineKeyboardButton(text='➕ Добавить', callback_data='trig:add')])
    rows.append([back_button('menu:main:1')])
    return InlineKeyboardMarkup(inline_keyboard=rows)

def trigger_card_kb(key: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text='✏️ Изменить', callback_data=f'trig:edit:{key}'), InlineKeyboardButton(text='🗑️ Удалить', callback_data=f'trig:rm:{key}')], [back_button('menu:triggers')]])

def blacklist_kb(config: Config) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    usernames = config.blacklist_usernames[:24]
    for i in range(0, len(usernames), 2):
        row = [InlineKeyboardButton(text=f'👤 {usernames[i]}', callback_data=f'bl:rm:{usernames[i]}')]
        if i + 1 < len(usernames):
            row.append(InlineKeyboardButton(text=f'👤 {usernames[i + 1]}', callback_data=f'bl:rm:{usernames[i + 1]}'))
        rows.append(row)
    rows.append([InlineKeyboardButton(text='➕ Добавить', callback_data='bl:add')])
    rows.append([back_button('menu:main:2')])
    return InlineKeyboardMarkup(inline_keyboard=rows)

def reviews_kb(config: Config) -> InlineKeyboardMarkup:
    global_status = '🟢 Авто-ответ: Включен' if config.review_auto_reply_enabled else '🔴 Авто-ответ: Выключен'
    rows: list[list[InlineKeyboardButton]] = [[InlineKeyboardButton(text=global_status, callback_data='rev:toggle')]]
    for rating in (1, 2, 3, 4, 5):
        stars = '⭐' * rating
        has_reply = bool(config.review_replies.get(str(rating)))
        is_disabled = str(rating) in config.disabled_reviews
        status_emoji = '🔴' if is_disabled or not has_reply else '🟢'
        rows.append([InlineKeyboardButton(text=stars, callback_data=f'rev:open:{rating}'), InlineKeyboardButton(text=status_emoji, callback_data=f'rev:toggle_rating:{rating}'), InlineKeyboardButton(text='✏️', callback_data=f'rev:edit:{rating}')])
    rows.append([back_button('menu:main:2')])
    return InlineKeyboardMarkup(inline_keyboard=rows)

def plugins_kb(plugins: dict) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    for uuid, plugin in list(plugins.items())[:30]:
        mark = '🟢' if plugin.enabled else '🔴'
        rows.append([InlineKeyboardButton(text=f'{mark} {plugin.name} v{plugin.version}', callback_data=f'pl:open:{uuid}')])
    rows.append([InlineKeyboardButton(text='📤 Загрузить плагин', callback_data='pl:upload')])
    rows.append([back_button('menu:main:1')])
    return InlineKeyboardMarkup(inline_keyboard=rows)

def empty_plugins_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text='📤 Загрузить плагин', callback_data='pl:upload')], [back_button('menu:main:1')]])

def plugin_card_kb(uuid: str, enabled: bool, has_error: bool=False) -> InlineKeyboardMarkup:
    label = '🔴 Выключить' if enabled else '🟢 Включить'
    rows: list[list[InlineKeyboardButton]] = [[InlineKeyboardButton(text=label, callback_data=f'pl:toggle:{uuid}'), InlineKeyboardButton(text='🗑️ Удалить', callback_data=f'pl:delete:{uuid}')]]
    if has_error:
        rows.append([InlineKeyboardButton(text='🧹 Сбросить ошибку', callback_data=f'pl:reset_err:{uuid}')])
    rows.append([back_button('menu:plugins')])
    return InlineKeyboardMarkup(inline_keyboard=rows)

def order_actions_kb(order_id: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text='✅ Подтвердить', callback_data=f'order:done:{order_id}')], [InlineKeyboardButton(text='🔙 Возврат', callback_data=f'order:refund:{order_id}')]])

def review_actions_kb() -> None:
    return None