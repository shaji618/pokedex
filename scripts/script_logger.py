import logging
import sys


class ScriptEmojiFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        message = record.getMessage()
        return message


class ScriptLogger:
    def __init__(self, name: str) -> None:
        self.logger = logging.getLogger(name)
        self._setup_logger()

    def _setup_logger(self) -> None:
        if self.logger.handlers:
            return
        self.logger.setLevel(logging.INFO)
        handler = logging.StreamHandler(sys.stdout)
        handler.setLevel(logging.DEBUG)
        formatter = ScriptEmojiFormatter()
        handler.setFormatter(formatter)
        self.logger.addHandler(handler)
        self.logger.propagate = False

    def success(self, message: str, indent: int = 0) -> None:
        prefix = "  " * indent
        self.logger.info(f"{prefix}✅ {message}")

    def failure(self, message: str, indent: int = 0) -> None:
        prefix = "  " * indent
        self.logger.error(f"{prefix}❌ {message}")

    def step(self, message: str, emoji: str = "🎯") -> None:
        self.logger.info(f"{emoji} {message}")

    def substep(self, message: str, indent: int = 1) -> None:
        prefix = "  " * indent
        self.logger.info(f"{prefix}{message}")

    def validation(self, message: str, indent: int = 0) -> None:
        prefix = "  " * indent
        self.logger.info(f"{prefix}🧪 {message}")

    def network(self, message: str, indent: int = 0) -> None:
        prefix = "  " * indent
        self.logger.info(f"{prefix}🌐 {message}")

    def progress(self, message: str, indent: int = 0) -> None:
        prefix = "  " * indent
        self.logger.info(f"{prefix}📊 {message}")

    def processing(self, message: str, indent: int = 0) -> None:
        prefix = "  " * indent
        self.logger.info(f"{prefix}📦 {message}")

    def info(self, message: str, indent: int = 0) -> None:
        prefix = "  " * indent
        self.logger.info(f"{prefix}{message}")

    def warning(self, message: str, indent: int = 0) -> None:
        prefix = "  " * indent
        self.logger.warning(f"{prefix}⚠️ {message}")

    def error(self, message: str, indent: int = 0) -> None:
        prefix = "  " * indent
        self.logger.error(f"{prefix}❌ {message}")


_script_logger = None


def get_script_logger(script_name: str = "pokemon.script") -> ScriptLogger:
    global _script_logger
    if _script_logger is None:
        _script_logger = ScriptLogger(script_name)
    return _script_logger
