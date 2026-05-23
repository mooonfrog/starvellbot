from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from src.configs.config import Config


def _row(*buttons: InlineKeyboardButton) -> list[InlineKeyboardButton]:
    return list(buttons)


def back_button(target: str = "menu:main") -> InlineKeyboardButton:
    return InlineKeyboardButton(text="⬅ Назад", callback_data=target)


def cancel_kb(target: str = "menu:main") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="❌ Отмена", callback_data=f"cancel:{target}")]]
    )


def back_kb(target: str = "menu:main") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[back_button(target)]])


def main_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            _row(
                InlineKeyboardButton(text="📊 Статус", callback_data="menu:status"),
                InlineKeyboardButton(text="💬 Триггеры", callback_data="menu:triggers"),
            ),
            _row(
                InlineKeyboardButton(text="✨ Команды", callback_data="menu:commands"),
                InlineKeyboardButton(text="🚫 Чёрный список", callback_data="menu:blacklist"),
            ),
            _row(
                InlineKeyboardButton(text="⭐ Авто-ответ на отзывы", callback_data="menu:reviews"),
            ),
            _row(
                InlineKeyboardButton(text="⚙️ Переключатели", callback_data="menu:toggles"),
                InlineKeyboardButton(text="🧩 Плагины", callback_data="menu:plugins"),
            ),
        ]
    )

def main_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            _row(
                InlineKeyboardButton(text="📊 Статус", callback_data="menu:status"),
                InlineKeyboardButton(text="💬 Триггеры", callback_data="menu:triggers"),
            ),
            _row(
                InlineKeyboardButton(text="✨ Команды", callback_data="menu:commands"),
                InlineKeyboardButton(text="🚫 Чёрный список", callback_data="menu:blacklist"),
            ),
            _row(
                InlineKeyboardButton(text="⚙️ Переключатели", callback_data="menu:toggles"),
                InlineKeyboardButton(text="🧩 Плагины", callback_data="menu:plugins"),
            ),
        ]
    )

def _toggle_label(name: str, on: bool) -> str:
    mark = "🟢" if on else "🔴"
    return f"{mark} {name}"


def toggles_kb(config: Config) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🔔 Уведомления", callback_data="menu:notify")],
            [InlineKeyboardButton(text="📋 Шаблоны ответов", callback_data="menu:quickreplies")],
            [InlineKeyboardButton(text="👋 Приветствие новых чатов", callback_data="menu:greeting")],
            [InlineKeyboardButton(text="🙏 Авто-благодарность", callback_data="menu:thanks")],
            [InlineKeyboardButton(text="✏️ Watermark", callback_data="menu:watermark")],
            [InlineKeyboardButton(text="⭐ Авто-ответ на отзывы", callback_data="menu:reviews")],
            [InlineKeyboardButton(text=_toggle_label("OnlineKeeper", config.online_keeper), callback_data="tg:ok")],
            [InlineKeyboardButton(text=_toggle_label("Авто-чтение чатов", config.auto_read_chats), callback_data="tg:autoread")],
            [InlineKeyboardButton(text=f"🌍 Таймзона: {config.timezone}", callback_data="tg:tz_edit")],
            [back_button()],
        ]
    )


def greeting_kb(config: Config) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=_toggle_label("Включено", config.greeting_enabled), callback_data="tg:greeting")],
            [InlineKeyboardButton(text="✏️ Изменить текст", callback_data="tg:greeting_edit")],
            [back_button("menu:toggles")],
        ]
    )


def thanks_kb(config: Config) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=_toggle_label("Включена", config.thanks_after_complete_enabled), callback_data="tg:thanks")],
            [InlineKeyboardButton(text="✏️ Изменить текст", callback_data="tg:thanks_edit")],
            [back_button("menu:toggles")],
        ]
    )


def watermark_kb(config: Config) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=_toggle_label("Включён", config.watermark_enabled), callback_data="tg:wm")],
            [InlineKeyboardButton(text="✏️ Изменить текст", callback_data="tg:wm_edit")],
            [back_button("menu:toggles")],
        ]
    )


def notify_kb(config: Config) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=_toggle_label("Сообщения", config.notify_messages), callback_data="ntf:messages")],
            [InlineKeyboardButton(text=_toggle_label("Заказы", config.notify_orders), callback_data="ntf:orders")],
            [InlineKeyboardButton(text=_toggle_label("Смена статуса заказа", config.notify_order_status), callback_data="ntf:order_status")],
            [InlineKeyboardButton(text=_toggle_label("Отзывы", config.notify_reviews), callback_data="ntf:reviews")],
            [InlineKeyboardButton(text=_toggle_label("Команды", config.notify_commands), callback_data="ntf:commands")],
            [back_button("menu:toggles")],
        ]
    )


def message_actions_kb(chat_id: str, has_quick_replies: bool = False) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    first: list[InlineKeyboardButton] = []
    if has_quick_replies:
        first.append(InlineKeyboardButton(text="📋 Шаблоны ответов", callback_data=f"qrlist:{chat_id}"))
    first.append(InlineKeyboardButton(text="💬 Ответить", callback_data=f"msg:reply:{chat_id}"))
    rows.append(first)
    rows.append([
        InlineKeyboardButton(text="🌐 Открыть чат", url=f"https://starvell.com/chat/{chat_id}"),
    ])
    rows.append([
        InlineKeyboardButton(text="🙈 Скрыть", callback_data="msg:hide"),
    ])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def quick_replies_for_chat_kb(chat_id: str, quick_replies: list[str]) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    for idx, text in enumerate(quick_replies[:25]):
        rows.append([
            InlineKeyboardButton(
                text=f"🔁 {text[:40]}",
                callback_data=f"qr:{idx}:{chat_id}",
            )
        ])
    rows.append([InlineKeyboardButton(text="🔙 Назад", callback_data=f"qrback:{chat_id}")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def quick_replies_kb(quick_replies: list[str]) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    for idx, text in enumerate(quick_replies[:25]):
        rows.append([
            InlineKeyboardButton(text=f"❌ {text[:30]}", callback_data=f"qrcfg:rm:{idx}")
        ])
    rows.append([
        InlineKeyboardButton(text="➕ Добавить", callback_data="qrcfg:add"),
        back_button("menu:toggles"),
    ])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def triggers_kb(config: Config) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    for key in list(config.triggers.keys())[:25]:
        rows.append([
            InlineKeyboardButton(text=f"💬 {key}", callback_data=f"trig:open:{key}")
        ])
    rows.append([
        InlineKeyboardButton(text="➕ Добавить", callback_data="trig:add"),
        back_button(),
    ])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def trigger_card_kb(key: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="✏️ Изменить ответ", callback_data=f"trig:edit:{key}")],
            [InlineKeyboardButton(text="❌ Удалить", callback_data=f"trig:rm:{key}")],
            [back_button("menu:triggers")],
        ]
    )


def commands_kb(config: Config) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    for key in list(config.starvell_commands.keys())[:25]:
        rows.append([
            InlineKeyboardButton(text=f"⚙️ {key}", callback_data=f"cmd:open:{key}")
        ])
    rows.append([
        InlineKeyboardButton(text="➕ Добавить", callback_data="cmd:add"),
        back_button(),
    ])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def command_card_kb(key: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="✏️ Изменить ответ", callback_data=f"cmd:edit:{key}")],
            [InlineKeyboardButton(text="❌ Удалить", callback_data=f"cmd:rm:{key}")],
            [back_button("menu:commands")],
        ]
    )


def blacklist_kb(config: Config) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    for username in config.blacklist_usernames[:25]:
        rows.append([
            InlineKeyboardButton(text=f"❌ {username}", callback_data=f"bl:rm:{username}")
        ])
    rows.append([
        InlineKeyboardButton(text="➕ Добавить", callback_data="bl:add"),
        back_button(),
    ])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def reviews_kb(config: Config) -> InlineKeyboardMarkup:
    label = "🟢 Включено" if config.review_auto_reply_enabled else "🔴 Выключено"
    rows: list[list[InlineKeyboardButton]] = [
        [InlineKeyboardButton(text=label, callback_data="rev:toggle")],
    ]
    for rating in (5, 4, 3, 2, 1):
        rows.append([
            InlineKeyboardButton(
                text=f"✏️ {rating} звезд(-а) ⭐",
                callback_data=f"rev:edit:{rating}",
            )
        ])
    rows.append([back_button("menu:toggles")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def plugins_kb(plugins: dict) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    for uuid, plugin in list(plugins.items())[:30]:
        mark = "🟢" if plugin.enabled else "🔴"
        rows.append([
            InlineKeyboardButton(
                text=f"{mark} {plugin.name} v{plugin.version}",
                callback_data=f"pl:open:{uuid}",
            )
        ])
    rows.append([InlineKeyboardButton(text="📤 Загрузить плагин", callback_data="pl:upload")])
    rows.append([back_button()])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def empty_plugins_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📤 Загрузить плагин", callback_data="pl:upload")],
            [back_button()],
        ]
    )


def plugin_card_kb(uuid: str, enabled: bool, has_error: bool = False) -> InlineKeyboardMarkup:
    label = "🔴 Выключить" if enabled else "🟢 Включить"
    rows: list[list[InlineKeyboardButton]] = [
        [InlineKeyboardButton(text=label, callback_data=f"pl:toggle:{uuid}")],
    ]
    if has_error:
        rows.append([InlineKeyboardButton(text="🧹 Сбросить ошибку", callback_data=f"pl:reset_err:{uuid}")])
    rows.append([InlineKeyboardButton(text="🧼 Удалить файл", callback_data=f"pl:delete:{uuid}")])
    rows.append([back_button("menu:plugins")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def order_actions_kb(order_id: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ Подтвердить", callback_data=f"order:done:{order_id}"),
            ],
            [
                InlineKeyboardButton(text="🔙 Возврат", callback_data=f"order:refund:{order_id}"),
            ],
            [
                InlineKeyboardButton(text="🙈 Скрыть", callback_data="msg:hide"),
            ]
        ]
    )


def review_actions_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🙈 Скрыть", callback_data="msg:hide")],
        ]
    )
