"""Logger estructurado para SACBinance v3.

Formato: [timestamp] [NIVEL  ] [modulo                ] mensaje
Ejemplo: [10:00:00.001] [INFO   ] [data_ingestion.hydrator] Hidratacion completa: 247 pares
"""
import logging
import sys
import time
from logging import LogRecord

from src.config.settings import get_settings

_configured = False


class _Fmt(logging.Formatter):
    def formatTime(self, record: LogRecord, datefmt=None) -> str:
        ct = self.converter(record.created)
        ms = int((record.created - int(record.created)) * 1000)
        return time.strftime("%Y-%m-%d %H:%M:%S", ct) + f".{ms:03d}"

    def format(self, record: LogRecord) -> str:
        ts = self.formatTime(record)
        lvl = record.levelname.ljust(7)
        mod = record.name.replace("src.", "").ljust(28)
        return f"[{ts}] [{lvl}] [{mod}] {record.getMessage()}"


def _configure() -> None:
    global _configured
    if _configured:
        return
    level = getattr(logging, get_settings().log_level.upper(), logging.INFO)
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(_Fmt())
    root = logging.getLogger()
    root.setLevel(level)
    root.handlers = [handler]
    _configured = True


def get_logger(name: str) -> logging.Logger:
    _configure()
    return logging.getLogger(name)


setup_logging = _configure
