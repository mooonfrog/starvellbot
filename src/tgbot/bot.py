import logging
from typing import Tuple
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import BotCommand, BotCommandScopeDefault
from src.configs.config import Config
from src.starvellapi import Account
from src.tgbot.confirm import ConfirmStore
from src.tgbot.handlers import router
from src.tgbot.middlewares import AuthMiddleware, DependenciesMiddleware
from src.utils.worker import Worker
log = logging.getLogger('telegrambot')
NAME_SUFFIX = ' | sᴛᴀʀᴠᴇʟʟʙᴏᴛ'
MENU_COMMANDS: list[BotCommand] = [BotCommand(command='start', description='Главное меню'), BotCommand(command='logs', description='Скачать лог-файл'), BotCommand(command='update', description='Обновить бота с GitHub'), BotCommand(command='restart', description='Перезапустить бота')]

def build_bot(config: Config, account: Account, worker: Worker, app: object | None=None) -> Tuple[Bot, Dispatcher]:
    if not config.telegram_bot_token:
        raise RuntimeError('telegram_bot_token не задан в конфиге')
    bot = Bot(token=config.telegram_bot_token, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dp = Dispatcher(storage=MemoryStorage())
    deps = DependenciesMiddleware(config=config, account=account, worker=worker, app=app, confirm_store=ConfirmStore())
    auth = AuthMiddleware(config)
    dp.message.middleware(deps)
    dp.callback_query.middleware(deps)
    dp.message.middleware(auth)
    dp.callback_query.middleware(auth)
    dp.include_router(router)
    if app is not None:
        for plugin in getattr(app, 'plugins', {}).values():
            tg_router = getattr(plugin.plugin, 'TELEGRAM_ROUTER', None)
            if tg_router is not None and plugin.enabled:
                dp.include_router(tg_router)
    return (bot, dp)

async def setup_commands(bot: Bot) -> None:
    try:
        await bot.set_my_commands(MENU_COMMANDS, scope=BotCommandScopeDefault())
    except Exception:
        log.exception('команды бота не зарегались')

async def setup_bot_name(bot: Bot) -> None:
    try:
        me = await bot.get_me()
        base_name = (me.first_name or '').strip()
        if base_name.endswith('sᴛᴀʀᴠᴇʟʟʙᴏᴛ'):
            return
        try:
            current = await bot.get_my_name()
            current_name = (current.name or '').strip() if current else ''
            if current_name.endswith('sᴛᴀʀᴠᴇʟʟʙᴏᴛ'):
                return
        except Exception:
            current_name = base_name
        new_name = f'{base_name}{NAME_SUFFIX}'
        if len(new_name) > 64:
            new_name = new_name[:64 - len('sᴛᴀʀᴠᴇʟʟʙᴏᴛ')] + 'sᴛᴀʀᴠᴇʟʟʙᴏᴛ'
        if current_name == new_name:
            return
        await bot.set_my_name(new_name)
        log.info('имя бота: %r', new_name)
    except Exception:
        log.exception('имя бота не обновилось')