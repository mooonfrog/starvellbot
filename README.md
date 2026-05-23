<div align="center">

```
   ┌─┐┌┬┐┌─┐┬─┐┬  ┬┌─┐┬  ┬  ┌┐ ┌─┐┌┬┐
   └─┐ │ ├─┤├┬┘└┐┌┘├┤ │  │  ├┴┐│ │ │ 
   └─┘ ┴ ┴ ┴┴└─ └┘ └─┘┴─┘┴─┘└─┘└─┘ ┴ 
```

# StarvellBot

ʕっ•ᴥ•ʔっ &nbsp; бот-помощник для [starvell.com](https://starvell.com) с управлением через Telegram

[![Python](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![aiogram](https://img.shields.io/badge/aiogram-3.7+-2CA5E0.svg)](https://docs.aiogram.dev/)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](#лицензия)

</div>

---

## Что это

StarvellBot слушает события вашего аккаунта на Starvell (новые сообщения, заказы, отзывы, команды) и отвечает на них автоматически. Управление и уведомления — через Telegram-бота. Всё расширяется плагинами.

## Возможности

- **Авто-ответы**: триггеры по тексту, быстрые ответы, команды от покупателей.
- **Заказы**: уведомления о новых заказах и смене статуса, благодарность после завершения, авто-приветствие в новом чате.
- **Отзывы**: авто-ответы на отзывы по рейтингу.
- **Telegram-управление**: вход по паролю, чтение и отправка сообщений, управление настройками, уведомления о событиях, критические логи в чат.
- **OnlineKeeper**: держит ваш статус «онлайн» на Starvell.
- **Чёрный список** пользователей, **rate limit** отправки, **watermark** в исходящих.
- **Плагины**: подкидываете `.py` в `plugins/` — он сам подхватит и зарегистрирует хендлеры.
- **Прокси**, **таймзоны**, авто-ротация логов.

## Требования

- Python **3.10+**
- Аккаунт на [starvell.com](https://starvell.com) (нужна `session` cookie)
- Telegram Bot Token от [@BotFather](https://t.me/BotFather)

## Установка

### Linux (systemd нужен) — одной командой

```bash
curl -fsSL https://raw.githubusercontent.com/mooonfrog/starvellbot/main/setup.sh | bash
```

### Управление сервисом

```bash
systemctl status starvellbot       # статус
journalctl -u starvellbot -f       # логи в реалтайме
systemctl restart starvellbot      # перезапуск
systemctl stop starvellbot         # остановить
systemctl disable starvellbot      # выключить автозапуск
```

Конфиги и данные живут в `/opt/starvellbot/configs/` и `/opt/starvellbot/data/`. Менять их можно либо руками, либо через TG-бота — после правки файлов перезапусти сервис.

### Windows

```bat
git clone https://github.com/mooonfrog/starvellbot.git
cd starvellbot
start.bat
```

При первом запуске бот сам спросит `session` cookie, прокси (опционально), Telegram Bot Token и пароль для входа в TG-бота.

### Ручная установка (без systemd)

```bash
git clone https://github.com/mooonfrog/starvellbot.git
cd starvellbot
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python app.py
```

## Запуск

- **Linux (systemd):** `systemctl start starvellbot` (если ставил через `setup.sh`)
- **Linux (вручную, без сервиса):** `./.venv/bin/python app.py`
- **Windows:** двойной клик по `start.bat` или из консоли

Первый запуск — это визард настройки. Дальше пиши `/start` своему телеграм-боту.

## Структура проекта

```
starvellbot/
├── app.py                  # точка входа
├── starvellbot.py          # ядро: загрузка плагинов, диспатч событий
├── version.py
├── requirements.txt
├── configs/                # конфиги (создаются визардом)
│   ├── _main.cfg           # session cookie, прокси, online keeper
│   ├── _settings.cfg       # триггеры, уведомления, watermark и т.д.
│   └── _tg.cfg             # tg-токен, пароль, авторизованные user_id
├── data/                   # состояние runner-а
├── logs/                   # логи (ротация 2MB x 5)
├── plugins/                # сюда кидать .py-плагины
└── src/
    ├── configs/            # модель Config
    ├── starvellapi/        # клиент Starvell API + updater
    ├── tgbot/              # aiogram-бот: handlers, keyboards, states
    └── utils/              # очередь сообщений, rate limit, state, лог-хендлер
```

## Где что настраивается

| Файл | Что внутри |
|------|------------|
| `configs/_main.cfg` | `session_cookie`, `user_agent`, `online_keeper`, `proxy` |
| `configs/_tg.cfg` | tg-токен, хеш пароля, авторизованные `user_id`, лимиты попыток входа |
| `configs/_settings.cfg` | таймзона, авто-чтение чатов, триггеры, команды, быстрые ответы, уведомления, авто-ответы на отзывы, благодарности, приветствие, watermark, rate limit, отключённые плагины |

Файлы можно править руками — конфиг переживает рестарт. Большинство опций также меняется из TG-бота.

## Плагины

Минимальный плагин — `plugins/hello.py`:

```python
NAME = "Hello"
VERSION = "1.0.0"
DESCRIPTION = "пример плагина"
CREDITS = "@you"
UUID = "00000000-0000-4000-8000-000000000001"   # любой валидный UUID4

async def on_new_message(app, event):
    if event.message.text == "ping":
        await app.worker.send_message(event.chat_id, "pong")

BIND_TO_NEW_MESSAGE = [on_new_message]
```

Доступные хуки: `BIND_TO_PRE_INIT`, `BIND_TO_POST_INIT`, `BIND_TO_PRE_START`, `BIND_TO_POST_START`, `BIND_TO_PRE_STOP`, `BIND_TO_POST_STOP`, `BIND_TO_NEW_MESSAGE`, `BIND_TO_NEW_ORDER`, `BIND_TO_ORDER_STATUS_CHANGED`, `BIND_TO_NEW_REVIEW`, `BIND_TO_COMMAND`.

Плагин с пятью ошибками подряд автоматически отключается. Включить обратно можно из TG-бота или удалив `uuid` из `disabled_plugins` в `_settings.cfg`.

Чтобы файл не подхватывался — в первой строке поставь `# noplug`.

Готовые плагины: [t.me/excplugins](https://t.me/excplugins).

## starvellapi — асинхронная либа для starvell.com

В состав проекта входит `src/starvellapi` — самописный async-клиент Starvell API. Его можно вытащить и юзать в своих скриптах независимо от бота: получение профиля, работа с офферами / заказами / чатами / отзывами / тикетами, плюс `Runner` для polling-событий и `OnlineKeeper` для статуса «онлайн».

**Установка:** скопируй папку `src/starvellapi/` в свой проект и поставь зависимости: `httpx`, `certifi`, `websockets`.

**Минимальный пример:**

```python
import asyncio
from starvellapi import Account

async def main():
    async with Account(session_cookie="...") as acc:
        me = await acc.get_profile()
        print(me.user.username, me.user.id)

        chats = await acc.get_chats(limit=10)
        for chat in chats:
            print(chat.id, chat.last_message.content if chat.last_message else "")

        await acc.send_message(chats[0].id, "привет!")

asyncio.run(main())
```

**Слушать события:**

```python
import asyncio
from starvellapi import Account, Runner
from starvellapi import NewMessageEvent, NewOrderEvent, NewReviewEvent

async def main():
    async with Account(session_cookie="...") as acc:
        runner = Runner(acc, poll_interval=3.0)
        async for event in runner.listen():
            if isinstance(event, NewMessageEvent):
                print("msg:", event.chat_id, event.message.content)
            elif isinstance(event, NewOrderEvent):
                print("order:", event.order.id, event.order.status)
            elif isinstance(event, NewReviewEvent):
                print("review:", event.review.rating, event.review.content)

asyncio.run(main())
```

**Держать онлайн-статус (websocket):**

```python
from starvellapi import Account, OnlineKeeper

async def main():
    async with Account(session_cookie="...") as acc:
        online = OnlineKeeper(acc)
        await online.start()
        try:
            await asyncio.sleep(3600)
        finally:
            await online.stop()
```

Что доступно из `starvellapi`:

- `Account` — HTTP-клиент: `get_profile`, `update_description`, `get_offers_by_category`, `update_offer`, `get_orders`, `refund_order`, `mark_order_completed`, `get_chats`, `get_chat_messages`, `send_typing`, `read_chat`, `send_message`, `get_reviews`, `create_review_response`, `update_review_response`, `delete_review_response`, `reply_ticket`, `close_ticket`.
- `Runner` — long-polling событий: новые сообщения, заказы, смена статусов, отзывы. Опционально принимает `state_store` для персистентности.
- `OnlineKeeper` — websocket-keepalive статуса «онлайн».
- Типы: `User`, `Profile`, `Offer`, `Order`, `OrderDetails`, `Chat`, `ChatMessage`, `Review`, `ReviewResponse`, `TicketReply`, `SubCategory`.
- Енумы: `OrderStatus`, `OrderUserType`, `OfferType`, `OfferSortBy`, `SortDirection`, `MessageType`, `EventType`.
- Исключения: `StarvellAPIError`, `AuthExpiredError`, `TransientError`, `RequestFailedError`, `MessageNotDeliveredError`.

Лицензия совпадает с проектом — MIT, юзайте как хотите.

## Проблемы

- **`session_cookie пустой`** — открой starvell.com, скопируй значение cookie `session` и впиши в `configs/_main.cfg` или прогони визард (удалить `configs/`).
- **`сессии плохо, обнови session_cookie`** — куки протухли, нужна свежая.
- **TG-бот не запускается** — проверь токен в `_tg.cfg` и что бот не используется в другой копии.
- **Забыл пароль от TG-бота** — удали `configs/_tg.cfg` и перезапусти, визард спросит новый.

## Лицензия

MIT

## Ссылки

- Автор: [@yusxe](https://t.me/yusxe)
- Плагины: [t.me/excplugins](https://t.me/excplugins)
- GitHub: [github.com/mooonfrog/starvellbot](https://github.com/mooonfrog/starvellbot)
