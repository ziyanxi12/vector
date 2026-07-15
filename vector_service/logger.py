import logging
import os
import shutil
from datetime import date
from logging import LogRecord


class _DebugOnlyFilter(logging.Filter):
    def filter(self, record: LogRecord) -> bool:
        return record.levelno == logging.DEBUG


class _ExcludeDebugFilter(logging.Filter):
    def filter(self, record: LogRecord) -> bool:
        return record.levelno > logging.DEBUG


class _DailyFileHandler(logging.FileHandler):
    """File handler that rolls over to a new file at midnight.
    
    Current day log: vector-service.txt / vector-service-debug.txt
    Historical logs: vector-service-YYYY-MM-DD.txt / vector-service-YYYY-MM-DD-debug.txt
    """

    def __init__(self, log_dir: str, suffix: str):
        self._log_dir = log_dir
        self._suffix = suffix
        self._current_date = date.today()
        os.makedirs(log_dir, exist_ok=True)
        super().__init__(self._build_current_path(), encoding="utf-8")

    def _build_current_path(self) -> str:
        return os.path.join(self._log_dir, f"vector-service{self._suffix}")

    def _build_dated_path(self, d: date) -> str:
        date_str = d.strftime("%Y-%m-%d")
        return os.path.join(self._log_dir, f"vector-service-{date_str}{self._suffix}")

    def emit(self, record: LogRecord) -> None:
        today = date.today()
        if today != self._current_date:
            self.close()
            old_path = self._build_current_path()
            new_path = self._build_dated_path(self._current_date)
            if os.path.exists(old_path):
                shutil.move(old_path, new_path)
            self._current_date = today
            self.baseFilename = os.path.abspath(self._build_current_path())
            self.stream = self._open()
        super().emit(record)


def setup_logging(log_dir: str, verbose_http: bool = False) -> None:
    formatter = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    debug_handler = _DailyFileHandler(log_dir, "-debug.txt")
    debug_handler.setLevel(logging.DEBUG)
    debug_handler.addFilter(_DebugOnlyFilter())
    debug_handler.setFormatter(formatter)

    service_handler = _DailyFileHandler(log_dir, ".txt")
    service_handler.setLevel(logging.INFO)
    service_handler.addFilter(_ExcludeDebugFilter())
    service_handler.setFormatter(formatter)

    root = logging.getLogger()
    root.setLevel(logging.DEBUG)
    root.addHandler(debug_handler)
    root.addHandler(service_handler)

    if not verbose_http:
        logging.getLogger("httpcore").setLevel(logging.WARNING)
        logging.getLogger("httpx").setLevel(logging.WARNING)
        logging.getLogger("elastic_transport.transport").setLevel(logging.WARNING)


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)
