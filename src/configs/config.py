import configparser
import hashlib
import json
import logging
import os
import secrets
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

log = logging.getLogger("config")

DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/147.0.0.0 Safari/537.36"
)

CONFIG_DIR = Path("configs")

FILE_MAIN = CONFIG_DIR / "_main.cfg"
FILE_TG = CONFIG_DIR / "_tg.cfg"
FILE_SETTINGS = CONFIG_DIR / "_settings.cfg"

DEFAULT_WATERMARK_TEXT = "[ 🐈 #starvellbot ]"


_LAYOUT: dict[Path, dict[str, list[tuple[str, str]]]] = {
    FILE_MAIN: {
        "Account": [
            ("session_cookie", "str"),
            ("user_agent", "str"),
            ("online_keeper", "bool"),
        ],
        "Network": [
            ("proxy", "str_optional"),
        ],
    },
    FILE_TG: {
        "Bot": [
            ("telegram_bot_token", "str"),
        ],
        "Auth": [
            ("telegram_password_hash", "json"),
            ("telegram_password_attempts", "json"),
            ("telegram_password_max_attempts", "int"),
            ("telegram_password_ban_minutes", "int"),
            ("authorized_telegram_users", "json"),
        ],
    },
    FILE_SETTINGS: {
        "General": [
            ("timezone", "str"),
            ("auto_read_chats", "bool"),
        ],
        "Blacklist": [
            ("blacklist_usernames", "json"),
        ],
        "Triggers": [
            ("triggers", "json"),
        ],
        "StarvellCommands": [
            ("starvell_commands", "json"),
        ],
        "QuickReplies": [
            ("quick_replies", "json"),
        ],
        "Notifications": [
            ("notify_messages", "bool"),
            ("notify_orders", "bool"),
            ("notify_order_status", "bool"),
            ("notify_reviews", "bool"),
            ("notify_commands", "bool"),
        ],
        "Reviews": [
            ("review_auto_reply_enabled", "bool"),
            ("review_replies", "json"),
        ],
        "Thanks": [
            ("thanks_after_complete_enabled", "bool"),
            ("thanks_text", "str"),
        ],
        "Greeting": [
            ("greeting_enabled", "bool"),
            ("greeting_text", "str"),
            ("greeted_chat_ids", "json"),
        ],
        "RateLimit": [
            ("send_message_rate_per_minute", "int"),
        ],
        "Watermark": [
            ("watermark_enabled", "bool"),
            ("watermark_text", "str"),
        ],
        "Plugins": [
            ("disabled_plugins", "json"),
        ],
    },
}


def _hash_password(password: str, salt: Optional[str] = None) -> dict:
    if not password:
        return {"hash": "", "salt": "", "scheme": "scrypt"}
    salt_bytes = bytes.fromhex(salt) if salt else os.urandom(16)
    digest = hashlib.scrypt(
        password.encode("utf-8"),
        salt=salt_bytes,
        n=2 ** 14,
        r=8,
        p=1,
        dklen=32,
    )
    return {"hash": digest.hex(), "salt": salt_bytes.hex(), "scheme": "scrypt"}


def _verify_password(password: str, stored: dict) -> bool:
    if not stored or not stored.get("hash"):
        return False
    try:
        check = hashlib.scrypt(
            password.encode("utf-8"),
            salt=bytes.fromhex(stored["salt"]),
            n=2 ** 14,
            r=8,
            p=1,
            dklen=32,
        )
    except (ValueError, KeyError):
        return False
    return secrets.compare_digest(check.hex(), stored["hash"])


def _to_str(value: Any, kind: str) -> str:
    if kind == "bool":
        return "true" if bool(value) else "false"
    if kind == "int":
        return str(int(value))
    if kind == "str":
        return "" if value is None else str(value)
    if kind == "str_optional":
        return "" if value is None else str(value)
    if kind == "json":
        return json.dumps(value, ensure_ascii=False)
    return "" if value is None else str(value)


def _from_str(raw: str, kind: str, default: Any) -> Any:
    if raw is None:
        return default
    if kind == "bool":
        return raw.strip().lower() in ("1", "true", "yes", "on", "y")
    if kind == "int":
        try:
            return int(raw)
        except (ValueError, TypeError):
            return default
    if kind == "str":
        return raw
    if kind == "str_optional":
        return raw if raw else None
    if kind == "json":
        if not raw.strip():
            return default
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return default
    return raw


@dataclass
class Config:
    session_cookie: str = ""
    proxy: Optional[str] = None
    user_agent: str = DEFAULT_USER_AGENT
    online_keeper: bool = True

    telegram_bot_token: str = ""
    telegram_password_hash: dict = field(default_factory=dict)
    telegram_password_attempts: dict = field(default_factory=dict)
    telegram_password_max_attempts: int = 5
    telegram_password_ban_minutes: int = 15

    timezone: str = "Europe/Moscow"
    auto_read_chats: bool = True

    authorized_telegram_users: list[int] = field(default_factory=list)
    blacklist_usernames: list[str] = field(default_factory=list)

    triggers: dict[str, str] = field(default_factory=dict)
    starvell_commands: dict[str, str] = field(default_factory=dict)
    quick_replies: list[str] = field(default_factory=list)

    notify_messages: bool = True
    notify_orders: bool = True
    notify_order_status: bool = True
    notify_reviews: bool = True
    notify_commands: bool = True

    review_auto_reply_enabled: bool = True
    review_replies: dict[str, str] = field(default_factory=dict)

    thanks_after_complete_enabled: bool = True
    thanks_text: str = ""

    greeting_enabled: bool = False
    greeting_text: str = ""
    greeted_chat_ids: list[str] = field(default_factory=list)

    send_message_rate_per_minute: int = 20

    watermark_enabled: bool = True
    watermark_text: str = DEFAULT_WATERMARK_TEXT

    disabled_plugins: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        self._dir: Path = CONFIG_DIR
        self._lock = threading.RLock()
    @classmethod
    def load(cls, directory: Path = CONFIG_DIR) -> "Config":
        directory = Path(directory)
        directory.mkdir(parents=True, exist_ok=True)
        cfg = cls()
        cfg._dir = directory

        files_exist = any(
            (directory / p.name).exists() for p in (FILE_MAIN, FILE_TG, FILE_SETTINGS)
        )

        for file_name, sections in _LAYOUT.items():
            file_path = directory / file_name.name
            if not file_path.exists():
                continue
            parser = configparser.ConfigParser(interpolation=None)
            parser.read(file_path, encoding="utf-8")
            for section, fields_ in sections.items():
                if not parser.has_section(section):
                    continue
                for name, kind in fields_:
                    if not parser.has_option(section, name):
                        continue
                    raw = parser.get(section, name, fallback=None)
                    default = getattr(cfg, name)
                    setattr(cfg, name, _from_str(raw, kind, default))

        if not files_exist:
            cfg.save()
            log.warning(
                "конфиги созданы в %s. заполни session_cookie, telegram_bot_token и пароль",
                directory,
            )
        return cfg

    def save(self) -> None:
        with self._lock:
            for file_name, sections in _LAYOUT.items():
                parser = configparser.ConfigParser(interpolation=None)
                for section, fields_ in sections.items():
                    parser.add_section(section)
                    for name, kind in fields_:
                        parser.set(section, name, _to_str(getattr(self, name), kind))
                file_path = self._dir / file_name.name
                file_path.parent.mkdir(parents=True, exist_ok=True)
                tmp = file_path.with_suffix(file_path.suffix + ".tmp")
                with tmp.open("w", encoding="utf-8") as f:
                    parser.write(f)
                tmp.replace(file_path)

    def set_password(self, password: str) -> None:
        with self._lock:
            self.telegram_password_hash = _hash_password(password)
            self.telegram_password_attempts = {}
            self.save()

    def verify_password(self, user_id: int, password: str) -> tuple[bool, Optional[str]]:
        with self._lock:
            now = int(time.time())
            entry = self.telegram_password_attempts.get(str(user_id), {})
            ban_until = int(entry.get("ban_until", 0) or 0)
            if ban_until > now:
                left = (ban_until - now) // 60 + 1
                return False, f"Слишком много попыток. Подожди ~{left} мин."

            if _verify_password(password, self.telegram_password_hash):
                self.telegram_password_attempts.pop(str(user_id), None)
                self.save()
                return True, None

            count = int(entry.get("count", 0) or 0) + 1
            attempts_left = self.telegram_password_max_attempts - count
            if attempts_left <= 0:
                ban_until = now + self.telegram_password_ban_minutes * 60
                self.telegram_password_attempts[str(user_id)] = {
                    "count": 0,
                    "ban_until": ban_until,
                }
                self.save()
                return False, (
                    f"Превышен лимит попыток. Доступ заморожен на {self.telegram_password_ban_minutes} мин."
                )
            self.telegram_password_attempts[str(user_id)] = {"count": count, "ban_until": 0}
            self.save()
            return False, f"Неверный пароль. Осталось попыток: {attempts_left}."

    def authorize_user(self, user_id: int) -> bool:
        with self._lock:
            if user_id in self.authorized_telegram_users:
                return False
            self.authorized_telegram_users.append(user_id)
            self.save()
            return True

    def revoke_user(self, user_id: int) -> bool:
        with self._lock:
            if user_id not in self.authorized_telegram_users:
                return False
            self.authorized_telegram_users.remove(user_id)
            self.save()
            return True

    def is_authorized(self, user_id: int) -> bool:
        return user_id in self.authorized_telegram_users

    def add_blacklist(self, username: str) -> bool:
        username = username.lower().lstrip("@")
        with self._lock:
            if username in self.blacklist_usernames:
                return False
            self.blacklist_usernames.append(username)
            self.save()
            return True

    def remove_blacklist(self, username: str) -> bool:
        username = username.lower().lstrip("@")
        with self._lock:
            if username not in self.blacklist_usernames:
                return False
            self.blacklist_usernames.remove(username)
            self.save()
            return True

    def is_blacklisted(self, username: Optional[str]) -> bool:
        if not username:
            return False
        return username.lower().lstrip("@") in self.blacklist_usernames

    def set_trigger(self, key: str, response: str) -> None:
        with self._lock:
            self.triggers[key.lower()] = response
            self.save()

    def remove_trigger(self, key: str) -> bool:
        with self._lock:
            if key.lower() not in self.triggers:
                return False
            del self.triggers[key.lower()]
            self.save()
            return True

    def set_starvell_command(self, key: str, response: str) -> None:
        with self._lock:
            self.starvell_commands[key.lower()] = response
            self.save()

    def remove_starvell_command(self, key: str) -> bool:
        with self._lock:
            if key.lower() not in self.starvell_commands:
                return False
            del self.starvell_commands[key.lower()]
            self.save()
            return True

    def get_starvell_command(self, key: str) -> Optional[str]:
        return self.starvell_commands.get(key.lower())

    def add_quick_reply(self, text: str) -> None:
        with self._lock:
            self.quick_replies.append(text)
            self.save()

    def remove_quick_reply(self, index: int) -> bool:
        with self._lock:
            if index < 0 or index >= len(self.quick_replies):
                return False
            del self.quick_replies[index]
            self.save()
            return True

    def review_reply_for(self, rating: int) -> Optional[str]:
        return self.review_replies.get(str(rating))

    def mark_chat_greeted(self, chat_id: str) -> None:
        with self._lock:
            if chat_id not in self.greeted_chat_ids:
                self.greeted_chat_ids.append(chat_id)
                if len(self.greeted_chat_ids) > 5000:
                    del self.greeted_chat_ids[: len(self.greeted_chat_ids) - 5000]
                self.save()

    def is_chat_greeted(self, chat_id: str) -> bool:
        return chat_id in self.greeted_chat_ids

    def apply_watermark(self, text: str) -> str:
        if not self.watermark_enabled or not self.watermark_text:
            return text
        return f"{self.watermark_text}\n\n{text}"

    def is_plugin_enabled(self, uuid: str) -> bool:
        return uuid not in self.disabled_plugins

    def toggle_plugin(self, uuid: str) -> bool:
        with self._lock:
            if uuid in self.disabled_plugins:
                self.disabled_plugins.remove(uuid)
                enabled = True
            else:
                self.disabled_plugins.append(uuid)
                enabled = False
            self.save()
            return enabled


def load_config(directory: Path = CONFIG_DIR) -> Config:
    return Config.load(directory)
