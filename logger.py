"""Application logging with rotation and basic identifier redaction."""

from __future__ import annotations

import logging
import re
from logging.handlers import RotatingFileHandler
from pathlib import Path


class IdentifierRedactionFilter(logging.Filter):
    """Keep national IDs, postal codes, and phones out of ordinary logs."""

    _identifier = re.compile(r"(?<!\d)(\d{3})\d{4,5}(\d{3})(?!\d)")

    def filter(self, record: logging.LogRecord) -> bool:
        message = record.getMessage()
        record.msg = self._identifier.sub(r"\1****\2", message)
        record.args = ()
        return True


def setup_logging(log_dir: Path, level: int = logging.INFO) -> logging.Logger:
    log_dir.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger("sida")
    logger.setLevel(level)
    logger.propagate = False

    if logger.handlers:
        return logger

    formatter = logging.Formatter(
        "%(asctime)s | %(levelname)s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    redact = IdentifierRedactionFilter()

    file_handler = RotatingFileHandler(
        log_dir / "sida_automation.log",
        maxBytes=5 * 1024 * 1024,
        backupCount=5,
        encoding="utf-8",
    )
    file_handler.setFormatter(formatter)
    file_handler.addFilter(redact)

    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    console_handler.addFilter(redact)

    logger.addHandler(file_handler)
    logger.addHandler(console_handler)
    return logger

