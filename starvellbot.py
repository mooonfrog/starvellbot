import asyncio
import importlib.util
import inspect
import logging
import sys
from dataclasses import dataclass, field
from pathlib import Path
from types import ModuleType
from typing import Any, Callable, Iterable, Optional
from uuid import UUID

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from aiogram import Bot, Dispatcher

from src.configs.config import Config
from src.starvellapi import Account, OnlineKeeper, Runner
from src.starvellapi.exceptions import AuthExpiredError
from src.starvellapi.updater.events import (
    BaseEvent,
    CommandInvokedEvent,
    NewMessageEvent,
    NewOrderEvent,
    NewReviewEvent,
    OrderStatusChangedEvent,
)
from src.utils.console import (
    BLUE,
    CYAN,
    GREEN,
    MAGENTA,
    RED,
    RESET,
    YELLOW,
    info_line,
    log_block,
    status_line,
)
from src.utils.state_store import StateStore
from src.utils.worker import Worker

log = logging.getLogger("starvellbot")
PLUGINS_DIR = ROOT / "plugins"
HANDLER_BINDS: tuple[str, ...] = (
    "BIND_TO_PRE_INIT",
    "BIND_TO_POST_INIT",
    "BIND_TO_PRE_START",
    "BIND_TO_POST_START",
    "BIND_TO_PRE_STOP",
    "BIND_TO_POST_STOP",
    "BIND_TO_NEW_MESSAGE",
    "BIND_TO_NEW_ORDER",
    "BIND_TO_ORDER_STATUS_CHANGED",
    "BIND_TO_NEW_REVIEW",
    "BIND_TO_COMMAND",
)
EVENT_TO_BIND: dict[type[BaseEvent], str] = {
    NewMessageEvent: "BIND_TO_NEW_MESSAGE",
    NewOrderEvent: "BIND_TO_NEW_ORDER",
    OrderStatusChangedEvent: "BIND_TO_ORDER_STATUS_CHANGED",
    NewReviewEvent: "BIND_TO_NEW_REVIEW",
    CommandInvokedEvent: "BIND_TO_COMMAND",
}


@dataclass
class PluginData:
    name: str
    version: str
    description: str
    credits: str
    uuid: str
    path: str
    plugin: ModuleType
    enabled: bool = True
    delete_handler: Optional[Callable] = None
    error: Optional[str] = None
    error_count: int = 0
    commands: dict[str, str] = field(default_factory=dict)

    def __repr__(self) -> str:
        return f"<PluginData name={self.name!r} v{self.version} enabled={self.enabled}>"


def _is_uuid4(value: str) -> bool:
    try:
        return str(UUID(value, version=4)) == value
    except (ValueError, AttributeError, TypeError):
        return False


class App:
    def __init__(self, config: Config) -> None:
        self.config = config
        self.account: Optional[Account] = None
        self.worker: Optional[Worker] = None
        self.online: Optional[OnlineKeeper] = None
        self.bot: Optional[Bot] = None
        self.dispatcher: Optional[Dispatcher] = None
        self.runner: Optional[Runner] = None
        self.plugins: dict[str, PluginData] = {}
        self._handlers: dict[str, list[tuple[str, Callable]]] = {
            name: [] for name in HANDLER_BINDS
        }

    def discover_plugins(self) -> None:
        if not PLUGINS_DIR.exists():
            PLUGINS_DIR.mkdir(parents=True, exist_ok=True)
            log.info("создана папка %s", PLUGINS_DIR)
        files = sorted(
            (p for p in PLUGINS_DIR.glob("*.py") if not p.name.startswith("_"))
        )
        if not files:
            log.info("плагинов нет, кидай .py в %s/", PLUGINS_DIR.name)
            return
        if str(PLUGINS_DIR.resolve()) not in sys.path:
            sys.path.append(str(PLUGINS_DIR.resolve()))
        loaded_lines: list[str] = []
        for file in files:
            if self._is_noplug(file):
                continue
            try:
                data = self._load_plugin(file)
            except Exception as e:
                log.exception("плагин %s не загрузился", file.name)
                loaded_lines.append(f"{RED}[x]{RESET} {file.name}: {e}")
                continue
            if not _is_uuid4(data.uuid):
                loaded_lines.append(f"{RED}[x]{RESET} {file.name}: кривой UUID")
                continue
            if data.uuid in self.plugins:
                existing = self.plugins[data.uuid]
                loaded_lines.append(
                    f"{RED}[x]{RESET} {file.name}: UUID занят {existing.name}"
                )
                continue
            data.enabled = self.config.is_plugin_enabled(data.uuid)
            self.plugins[data.uuid] = data
            mark = f"{GREEN}[+]{RESET}" if data.enabled else f"{YELLOW}[-]{RESET}"
            loaded_lines.append(
                f"{mark} {data.name} {CYAN}v{data.version}{RESET} - {data.credits}"
            )
        title = f"{CYAN}плагины:{RESET} {GREEN}{len(self.plugins)}{RESET} шт."
        log_block(log, logging.INFO, title, loaded_lines or ["нет валидных"])

    @staticmethod
    def _is_noplug(file: Path) -> bool:
        try:
            with file.open("r", encoding="utf-8") as f:
                first = f.readline().strip()
        except OSError:
            return True
        return first.startswith("#") and "noplug" in first.lower()

    def _load_plugin(self, file: Path) -> PluginData:
        module_name = f"plugins.{file.stem}"
        spec = importlib.util.spec_from_file_location(module_name, file)
        if spec is None or spec.loader is None:
            raise ImportError(f"не удалось создать spec для {file}")
        module = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = module
        spec.loader.exec_module(module)
        for required in ("NAME", "VERSION", "DESCRIPTION", "CREDITS", "UUID"):
            if not hasattr(module, required):
                raise AttributeError(f"в {file.name} нет поля {required}")
        return PluginData(
            name=str(getattr(module, "NAME")),
            version=str(getattr(module, "VERSION")),
            description=str(getattr(module, "DESCRIPTION")),
            credits=str(getattr(module, "CREDITS")),
            uuid=str(getattr(module, "UUID")),
            path=str(file),
            plugin=module,
            delete_handler=getattr(module, "BIND_TO_DELETE", None),
        )

    def register_handlers(self) -> None:
        for plugin in self.plugins.values():
            for name in HANDLER_BINDS:
                funcs: Iterable[Callable] = getattr(plugin.plugin, name, ()) or ()
                for func in funcs:
                    self._handlers[name].append((plugin.uuid, func))

    async def call_handlers(self, name: str, *args: Any) -> None:
        for plugin_uuid, func in list(self._handlers[name]):
            plugin = self.plugins.get(plugin_uuid)
            if plugin is not None and (not plugin.enabled):
                continue
            try:
                result = func(self, *args)
                if inspect.isawaitable(result):
                    await result
            except Exception as exc:
                log.exception(
                    "плагин %s остановился (%s)",
                    plugin.name if plugin else plugin_uuid,
                    name,
                )
                if plugin is not None:
                    plugin.error = f"{name}: {type(exc).__name__}: {exc}"
                    plugin.error_count = getattr(plugin, "error_count", 0) + 1
                    if plugin.error_count >= 5:
                        plugin.enabled = False
                        if plugin.uuid not in self.config.disabled_plugins:
                            self.config.disabled_plugins.append(plugin.uuid)
                            self.config.save()
                        log.warning(
                            "выключил %s после %d ошибок подряд",
                            plugin.name,
                            plugin.error_count,
                        )

    async def on_event(self, event: BaseEvent) -> None:
        bind = EVENT_TO_BIND.get(type(event))
        if bind is None:
            return
        await self.call_handlers(bind, event)

    def print_init_summary(self) -> None:
        plugins_count = sum((1 for p in self.plugins.values() if p.enabled))
        plugins_total = len(self.plugins)
        my_id = self.worker.my_id if self.worker else "-"
        lines = [
            info_line("Аккаунт", f"id={my_id}", color=GREEN),
            info_line("Таймзона", self.config.timezone, color=GREEN),
            info_line(
                "Прокси",
                self.config.proxy or "не используется",
                color=GREEN if self.config.proxy else YELLOW,
            ),
            status_line("OnlineKeeper", self.config.online_keeper),
            status_line("Авто-чтение чатов", self.config.auto_read_chats),
            status_line(
                "Авто-благодарность", self.config.thanks_after_complete_enabled
            ),
            status_line("Watermark", self.config.watermark_enabled),
            status_line("Авто-ответ на отзывы", self.config.review_auto_reply_enabled),
            info_line(
                "Плагины",
                f"{plugins_count}/{plugins_total} активны",
                color=GREEN if plugins_count else YELLOW,
            ),
            info_line(
                "Telegram-бот",
                "включён" if self.config.telegram_bot_token else "выключен",
                color=GREEN if self.config.telegram_bot_token else YELLOW,
            ),
        ]
        print("")
        log_block(
            log, logging.INFO, f"{MAGENTA}Состояние:{RESET}", lines, frame_color=BLUE
        )
        print("")

    async def runner_loop(self, state_store: StateStore) -> None:
        runner = Runner(self.account, state_store=state_store)
        try:
            async for event in runner.listen():
                try:
                    await self.worker.process_event(event)
                except Exception:
                    log.exception("Worker error")
        except AuthExpiredError:
            log.error("Session expired")
            raise
        except asyncio.CancelledError:
            raise
        finally:
            await runner.stop()

    async def telegram_loop(self) -> None:
        from src.tgbot.bot import build_bot, setup_bot_name, setup_commands
        from src.tgbot.notifier import TelegramNotifier

        if not self.config.telegram_bot_token:
            log.warning("telegram_bot_token пуст, тг-бот не поднимается")
            return
        self.bot, self.dispatcher = build_bot(
            self.config, self.account, self.worker, self
        )
        await setup_bot_name(self.bot)
        await setup_commands(self.bot)
        if self.worker:
            notifier = TelegramNotifier(self.bot, self.config, self.worker)
            self.worker.add_listener(notifier)
        try:
            await self.dispatcher.start_polling(self.bot, handle_signals=False)
        finally:
            await self.bot.session.close()
