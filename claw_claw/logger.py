"""Logging setup with redaction."""
from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

from claw_claw.utils import redact_text


class RedactingFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        base = super().format(record)
        return redact_text(base)


def setup_logger(log_dir: Path, name: str, filename: str) -> logging.Logger:
    log_dir.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger(name)
    logger.setLevel(logging.INFO)
    if logger.handlers:
        return logger

    handler = RotatingFileHandler(log_dir / filename, maxBytes=1_000_000, backupCount=5)
    formatter = RedactingFormatter("%(asctime)s %(levelname)s %(message)s")
    handler.setFormatter(formatter)
    logger.addHandler(handler)
    logger.propagate = False
    return logger
