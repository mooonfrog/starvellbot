from typing import Iterable

from colorama import Fore, Style, init as colorama_init

colorama_init(autoreset=False)

BLUE = Fore.LIGHTBLUE_EX
CYAN = Fore.CYAN
GREEN = Fore.LIGHTGREEN_EX
YELLOW = Fore.LIGHTYELLOW_EX
RED = Fore.LIGHTRED_EX
MAGENTA = Fore.LIGHTMAGENTA_EX
WHITE = Fore.WHITE
DIM = Style.DIM
RESET = Style.RESET_ALL
BOLD = Style.BRIGHT

OK = "[OK]"
FAIL = "[!!]"
WARN = "[..]"
INFO = "[i]"
PLUS = "[+]"
MINUS = "[-]"
ARROW = "->"
BULLET = "*"


def colorize(text: str, color: str) -> str:
    return f"{color}{text}{RESET}"


def success_mark() -> str:
    return f"{GREEN}{OK}{RESET}"


def fail_mark() -> str:
    return f"{RED}{FAIL}{RESET}"


def warn_mark() -> str:
    return f"{YELLOW}{WARN}{RESET}"


def info_mark() -> str:
    return f"{CYAN}{INFO}{RESET}"


def print_block(title: str, lines: Iterable[str], frame_color: str = BLUE) -> None:
    items = [str(line) for line in lines]
    print(f"{BOLD}{title}{RESET}")
    if not items:
        return
    for line in items[:-1]:
        print(f"{frame_color}┃{RESET}  {line}")
    print(f"{frame_color}┗{RESET}  {items[-1]}")


def info_line(label: str, value: str, color: str = GREEN) -> str:
    return f"{color}{label}:{RESET} {value}"


def status_line(label: str, enabled: bool) -> str:
    mark = f"{GREEN}ON{RESET}" if enabled else f"{RED}OFF{RESET}"
    return f"{label}: [{mark}]"


def banner(title: str, subtitle: str | None = None, color: str = CYAN) -> None:
    text = title if not subtitle else f"{title}  -  {subtitle}"
    width = max(len(text) + 6, 40)
    bar = "=" * width
    print(f"{color}{bar}{RESET}")
    pad = (width - len(text) - 2) // 2
    line = " " * pad + text
    print(f"{color}|{BOLD}{line.ljust(width - 2)}{RESET}{color}|{RESET}")
    print(f"{color}{bar}{RESET}")


import logging as _logging

_LEVEL_COLORS = {
    _logging.DEBUG: BLUE,
    _logging.INFO: GREEN,
    _logging.WARNING: YELLOW,
    _logging.ERROR: RED,
    _logging.CRITICAL: MAGENTA,
}


class ColorFormatter(_logging.Formatter):
    def __init__(self, fmt: str, datefmt: str | None = None) -> None:
        super().__init__(fmt=fmt, datefmt=datefmt)

    def format(self, record: _logging.LogRecord) -> str:
        color = _LEVEL_COLORS.get(record.levelno, "")
        original = record.levelname
        if color:
            record.levelname = f"{color}{original}{RESET}"
        try:
            return super().format(record)
        finally:
            record.levelname = original



def log_block(
    logger: _logging.Logger,
    level: int,
    title: str,
    lines: list[str],
    frame_color: str = BLUE,
) -> None:
    logger.log(level, "%s", title)
    items = list(lines)
    if not items:
        return
    for line in items[:-1]:
        logger.log(level, "%s  %s", f"{frame_color}┃{RESET}", line)
    logger.log(level, "%s  %s", f"{frame_color}┗{RESET}", items[-1])
