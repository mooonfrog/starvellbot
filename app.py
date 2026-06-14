import asyncio
import logging
import os
import sys
import time
from logging.handlers import RotatingFileHandler
from pathlib import Path
ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from src.configs.config import CONFIG_DIR
from src.starvellapi import Account, OnlineKeeper
from src.starvellapi.exceptions import StarvellAPIError
from src.utils.not_config import ensure_config, print_banner
from src.utils.state_store import StateStore
from src.utils.tg_log_handler import TelegramLogHandler
from src.utils.worker import Worker
from starvellbot import App
from version import VERSION
LOG_DIR = ROOT / 'logs'
LOG_FILE = LOG_DIR / 'log.log'
DATA_DIR = ROOT / 'data'
log = logging.getLogger('starvellbot')

def _clear_console() -> None:
    try:
        if sys.platform.startswith('win'):
            os.system('cls')
        else:
            os.system('clear')
    except Exception:
        pass

def _set_console_title(title: str) -> None:
    try:
        if sys.platform.startswith('win'):
            os.system(f'title {title}')
        else:
            sys.stdout.write(f'\x1b]0;{title}\x07')
            sys.stdout.flush()
    except Exception:
        pass

def _setup_logging() -> TelegramLogHandler:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    fmt_string = '%(asctime)s [%(levelname)s] %(name)s: %(message)s'
    datefmt = '%Y-%m-%d %H:%M:%S'
    fmt = logging.Formatter(fmt_string, datefmt=datefmt)
    from src.utils.console import ColorFormatter
    color_fmt = ColorFormatter(fmt_string, datefmt=datefmt)
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    for handler in list(root.handlers):
        root.removeHandler(handler)
    console = logging.StreamHandler(sys.stdout)
    console.setLevel(logging.INFO)
    console.setFormatter(color_fmt)
    root.addHandler(console)
    file_handler = RotatingFileHandler(LOG_FILE, maxBytes=2 * 1024 * 1024, backupCount=5, encoding='utf-8')
    file_handler.setLevel(logging.INFO)
    file_handler.setFormatter(fmt)
    root.addHandler(file_handler)
    tg_handler = TelegramLogHandler(level=logging.CRITICAL)
    tg_handler.setFormatter(fmt)
    root.addHandler(tg_handler)
    for noisy in ('httpx', 'httpcore', 'hpack', 'aiogram', 'aiogram.dispatcher', 'aiogram.event', 'aiogram.middlewares', 'websockets', 'websockets.client', 'websockets.server', 'starvellapi', 'starvellapi.online', 'starvellapi.runner'):
        logging.getLogger(noisy).setLevel(logging.WARNING)
    return tg_handler

async def _runner_task(app: App, state_store: StateStore) -> None:
    log.info('runner запущен')
    try:
        await app.runner_loop(state_store)
    finally:
        log.info('runner остановлен')

async def _telegram_task(app: App, tg_handler: TelegramLogHandler) -> None:
    if not app.config.telegram_bot_token:
        log.warning('telegram_bot_token пуст, тг-бот не запустится')
        return
    log.info('запускаю тг-бота...')

    async def _ready() -> None:
        await asyncio.sleep(0.5)
        if app.bot is not None:
            tg_handler.attach(app.bot, app.config.authorized_telegram_users, asyncio.get_running_loop())
            log.info('tg-логгер запущен')
    asyncio.create_task(_ready())
    try:
        await app.telegram_loop()
    finally:
        log.info('тг-бот остановлен')

async def _main_async(tg_handler: TelegramLogHandler) -> None:
    config = ensure_config(CONFIG_DIR)
    if not config.session_cookie:
        log.error('session_cookie пустой. заполни configs/_main.cfg и перезапусти')
        return
    app = App(config)
    app.discover_plugins()
    app.register_handlers()
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    state_store = StateStore(DATA_DIR / 'state.json')
    account = Account(session_cookie=config.session_cookie, proxy=config.proxy, user_agent=config.user_agent)
    app.account = account
    async with account:
        worker = Worker(account, config)
        app.worker = worker
        await worker.initialize()
        await worker.start_queue()
        worker.add_listener(app.on_event)
        await app.call_handlers('BIND_TO_PRE_INIT')
        app.print_init_summary()
        await app.call_handlers('BIND_TO_POST_INIT')
        if config.online_keeper:
            app.online = OnlineKeeper(account)
            await app.online.start()
        await app.call_handlers('BIND_TO_PRE_START')
        runner_task = asyncio.create_task(_runner_task(app, state_store))
        telegram_task = asyncio.create_task(_telegram_task(app, tg_handler))
        await app.call_handlers('BIND_TO_POST_START')
        tasks = [runner_task, telegram_task]
        try:
            await asyncio.gather(*tasks)
        except asyncio.CancelledError:
            pass
        finally:
            await app.call_handlers('BIND_TO_PRE_STOP')
            for t in tasks:
                t.cancel()
            for t in tasks:
                try:
                    await t
                except (asyncio.CancelledError, Exception):
                    pass
            await worker.stop_queue()
            if app.online is not None:
                await app.online.stop()
            await app.call_handlers('BIND_TO_POST_STOP')
            tg_handler.stop()

def _acquire_instance_lock(timeout: float=10.0):
    """Берём эксклюзивный лок, чтобы не запустить второй экземпляр бота.

    Два экземпляра = два WebSocket'а к Starvell = дублирующиеся уведомления.
    При /restart старый процесс ещё пару секунд держит лок, поэтому новый
    процесс повторяет попытки в течение timeout секунд, прежде чем сдаться.
    Возвращает открытый файловый объект (лок держится, пока он жив) или None.
    """
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    lock_path = DATA_DIR / 'instance.lock'
    lock_file = open(lock_path, 'w')
    if sys.platform.startswith('win'):
        import msvcrt

        def _try_lock() -> bool:
            try:
                msvcrt.locking(lock_file.fileno(), msvcrt.LK_NBLCK, 1)
                return True
            except OSError:
                return False
    else:
        import fcntl

        def _try_lock() -> bool:
            try:
                fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                return True
            except OSError:
                return False
    deadline = time.monotonic() + timeout
    while True:
        if _try_lock():
            lock_file.seek(0)
            lock_file.truncate()
            lock_file.write(str(os.getpid()))
            lock_file.flush()
            return lock_file
        if time.monotonic() >= deadline:
            lock_file.close()
            return None
        time.sleep(0.5)


def main() -> None:
    _clear_console()
    _set_console_title(f'StarvellBot - {VERSION}')
    print_banner(VERSION)
    tg_handler = _setup_logging()
    instance_lock = _acquire_instance_lock()
    if instance_lock is None:
        log.error('Бот уже запущен (lock %s занят). Второй экземпляр не запускается.', DATA_DIR / 'instance.lock')
        sys.exit(1)
    log.info('starvellbot %s старт', VERSION)
    try:
        asyncio.run(_main_async(tg_handler))
    except KeyboardInterrupt:
        log.info('остановлен.')
    except RuntimeError as e:
        if 'Event loop stopped before Future completed' not in str(e):
            log.exception('RuntimeError')
    except StarvellAPIError as e:
        log.error('starvell api: %s', e)
        sys.exit(1)
    if os.environ.pop('STARVELLBOT_RESTART', ''):
        import subprocess
        log.info('рестарт по /restart')
        subprocess.Popen([sys.executable, str(Path(__file__).resolve())])
        sys.exit(0)
if __name__ == '__main__':
    main()