import logging
from typing import Any, ClassVar


class EmojiFormatter(logging.Formatter):
    LEVEL_EMOJIS: ClassVar[dict[int, str]] = {
        logging.DEBUG: "🔍",
        logging.INFO: "ℹ️",
        logging.WARNING: "⚠️",
        logging.ERROR: "❌",
        logging.CRITICAL: "💥",
    }
    CONTEXT_EMOJIS: ClassVar[dict[str, str]] = {
        "success": "✅",
        "failure": "❌",
        "warning": "⚠️",
        "info": "ℹ️",
        "debug": "🔍",
        "progress": "📊",
        "processing": "📦",
        "network": "🌐",
        "browser": "🎭",
        "validation": "🧪",
        "audio": "🔊",
        "image": "🖼️",
        "pokemon": "🎮",
        "data": "📄",
        "config": "⚙️",
        "cache": "💾",
        "performance": "⚡",
        "cleanup": "🧹",
    }

    def format(self, record: logging.LogRecord) -> str:
        message = record.getMessage()
        if any(
            emoji in message
            for emoji in ["🎮", "✅", "❌", "⚠️", "🔍", "📊", "📦", "🌐", "🎭", "🧪"]
        ):
            return message
        level_emoji = self.LEVEL_EMOJIS.get(record.levelno, "")
        if message.startswith("  ") or message.startswith("    "):
            return message
        else:
            return f"{level_emoji} {message}" if level_emoji else message


class PokemonLogger:
    def __init__(self, name: str) -> None:
        self.logger = logging.getLogger(name)
        self._setup_logger()

    def _setup_logger(self) -> None:
        if self.logger.handlers:
            return
        self.logger.setLevel(logging.INFO)
        handler = logging.StreamHandler()
        handler.setLevel(logging.DEBUG)
        formatter = EmojiFormatter()
        handler.setFormatter(formatter)
        self.logger.addHandler(handler)
        self.logger.propagate = False

    def info(self, message: str, **keyword_arguments: Any) -> None:
        self.logger.info(message, **keyword_arguments)

    def warning(self, message: str, **keyword_arguments: Any) -> None:
        self.logger.warning(message, **keyword_arguments)

    def error(self, message: str, **keyword_arguments: Any) -> None:
        self.logger.error(message, **keyword_arguments)

    def debug(self, message: str, **keyword_arguments: Any) -> None:
        self.logger.debug(message, **keyword_arguments)

    def success(self, message: str, indent: int = 0) -> None:
        prefix = "  " * indent
        self.logger.info(f"{prefix}✅ {message}")

    def failure(self, message: str, indent: int = 0) -> None:
        prefix = "  " * indent
        self.logger.error(f"{prefix}❌ {message}")

    def progress(self, message: str, indent: int = 0) -> None:
        prefix = "  " * indent
        self.logger.info(f"{prefix}📊 {message}")

    def processing(self, message: str, indent: int = 0) -> None:
        prefix = "  " * indent
        self.logger.info(f"{prefix}📦 {message}")

    def network(self, message: str, indent: int = 0) -> None:
        prefix = "  " * indent
        self.logger.info(f"{prefix}🌐 {message}")

    def validation(self, message: str, indent: int = 0) -> None:
        prefix = "  " * indent
        self.logger.info(f"{prefix}🧪 {message}")

    def pokemon(self, message: str, indent: int = 0) -> None:
        prefix = "  " * indent
        self.logger.info(f"{prefix}🎮 {message}")

    def step(self, step_number: int, message: str, emoji: str = "🎯") -> None:
        self.logger.info(f"{emoji} Step {step_number}: {message}")

    def substep(self, message: str, indent: int = 1) -> None:
        prefix = "  " * indent
        self.logger.info(f"{prefix}{message}")


_core_logger: PokemonLogger | None = None


def get_logger() -> PokemonLogger:
    if globals()["_core_logger"] is None:
        globals()["_core_logger"] = PokemonLogger("pokemon.core")

    return globals()["_core_logger"]
