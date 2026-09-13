import logging
import sys

from app.config import get_settings

RESET = "\033[0m"
COLORS = {
    "green": "\033[32m",
    "red": "\033[31m",
    "yellow": "\033[33m",
    "cyan": "\033[36m",
    "blue": "\033[34m",
    "magenta": "\033[35m",
    "bright_magenta": "\033[1;35m",
    "gray": "\033[90m",
}


class ColoredFormatter(logging.Formatter):
    def __init__(self, fmt: str, use_color: bool) -> None:
        super().__init__(fmt)
        self.use_color = use_color

    def format(self, record: logging.LogRecord) -> str:
        message = super().format(record)
        if not self.use_color:
            return message
        color = self._color_for(record)
        return f"{color}{message}{RESET}"

    def _color_for(self, record: logging.LogRecord) -> str:
        if record.levelno >= logging.ERROR:
            return COLORS["red"]
        if record.levelno >= logging.WARNING:
            return COLORS["yellow"]

        text = record.getMessage().lower()

        if "check succeeded" in text:
            return COLORS["green"]
        if "check failed" in text or "collection failed" in text:
            return COLORS["red"]
        if "checking proxy" in text:
            return COLORS["cyan"]
        if "collection started" in text:
            return COLORS["blue"]
        if "checker queue refilled" in text:
            return COLORS["bright_magenta"]
        if "collection completed" in text or "discovered new proxy" in text:
            return COLORS["magenta"]
        if "cooldown" in text:
            return COLORS["yellow"]
        if "recheck enqueued" in text or "recheck queued" in text:
            return COLORS["blue"]
        if "wal checkpoint" in text or "score recalculation" in text or "cleanup removed" in text:
            return COLORS["gray"]
        if "background jobs" in text or "checker workers" in text or "loaded" in text:
            return COLORS["gray"]

        return RESET


def setup_logging() -> None:
    settings = get_settings()
    use_color = settings.log_color_enabled and sys.stdout.isatty()
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(ColoredFormatter(settings.log_format, use_color=use_color))

    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(getattr(logging, settings.log_level.upper(), logging.INFO))
