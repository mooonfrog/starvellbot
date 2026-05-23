from pathlib import Path
from typing import Optional

from src.configs.config import Config, load_config
from src.utils.console import (
    BLUE,
    BOLD,
    CYAN,
    DIM,
    MAGENTA,
    RESET,
    WHITE,
    YELLOW,
    fail_mark,
    info_mark,
    success_mark,
)

BANNER = r"""

   ┌─┐┌┬┐┌─┐┬─┐┬  ┬┌─┐┬  ┬  ┌┐ ┌─┐┌┬┐
   └─┐ │ ├─┤├┬┘└┐┌┘├┤ │  │  ├┴┐│ │ │ 
   └─┘ ┴ ┴ ┴┴└─ └┘ └─┘┴─┘┴─┘└─┘└─┘ ┴ 

   ʕ•ᴥ•ʔっ  StarvellBot  -  by @yusxe
   plugins: t.me/excplugins

   github: github.com/mooonfrog/starvellbot
   
"""

KAOMOJI_HELLO = "ʕっ•ᴥ•ʔっ"
KAOMOJI_HAPPY = "(*^▽^*)"
KAOMOJI_LOVE = "(♥ᴗ♥)"
KAOMOJI_TADA = "※\\(^o^)/※"
KAOMOJI_OK = "(•̀ᴗ•́)و"
KAOMOJI_OOPS = "(╯°□°)╯"


def print_banner(version: str = "") -> None:
    print(f"{MAGENTA}{BOLD}{BANNER}{RESET}")
    if version:
        print(f"{DIM}{WHITE}   version {version}{RESET}\n")


def _ask(
    label: str,
    kao: str = KAOMOJI_HAPPY,
    default: Optional[str] = None,
    optional: bool = False,
) -> str:
    if default is not None:
        suffix = f" {DIM}[ {default} ]{RESET}"
    elif optional:
        suffix = f" {DIM}[ нажмите Enter чтобы пропустить ]{RESET}"
    else:
        suffix = ""
    prompt = f"{CYAN}?{RESET} {BOLD}{label}{RESET} {YELLOW}{kao}{RESET}{suffix}: "
    while True:
        try:
            value = input(prompt)
        except EOFError:
            value = ""
        value = value.strip()
        if not value and default is not None:
            return default
        if not value and optional:
            return ""
        if value:
            return value
        print(f"   {fail_mark()} Поле не может быть пустым {KAOMOJI_OOPS}")


def _print_section(title: str, kao: str) -> None:
    print(f"\n{BOLD}{title}{RESET} {YELLOW}{kao}{RESET}")


def run_setup_wizard(directory: Path) -> Config:
    print(
        f"{info_mark()} Конфиги в {directory} не настроены. Прогоним опросник, это быстро {KAOMOJI_HELLO}\n"
    )

    cfg = load_config(directory)

    _print_section("Starvell аккаунт", KAOMOJI_LOVE)
    cfg.session_cookie = _ask(
        "Сессия (session) куки с starvell.com",
        kao=KAOMOJI_HAPPY,
    )
    proxy = _ask(
        "Прокси (формат http://user:pass@host:port)",
        kao=KAOMOJI_HAPPY,
        optional=True,
    )
    cfg.proxy = proxy or None

    _print_section("Telegram", KAOMOJI_TADA)
    cfg.telegram_bot_token = _ask(
        "Введите Telegram Bot Token (от @BotFather)",
        kao=KAOMOJI_TADA,
    )
    while True:
        password = _ask("Пароль для входа в TG-бота", kao=KAOMOJI_OK)
        confirm = _ask("Повторите пароль", kao=KAOMOJI_OK)
        if password == confirm:
            cfg.set_password(password)
            break
        print(f"   {fail_mark()} Пароли не совпали {KAOMOJI_OOPS}")

    cfg.save()
    print(f"\n{success_mark()} Конфиги сохранены в {directory} {KAOMOJI_TADA}\n")
    return cfg


def ensure_config(directory: Path) -> Config:
    cfg = load_config(directory)
    needs_wizard = (
        not cfg.session_cookie
        or not cfg.telegram_bot_token
        or not cfg.telegram_password_hash
        or not cfg.telegram_password_hash.get("hash")
    )
    if needs_wizard:
        return run_setup_wizard(directory)
    return cfg
