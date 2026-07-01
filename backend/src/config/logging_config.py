"""
File logging configuration with rotating handler and ZIP compression.
Writes to log file ONLY — does not add another console handler.
"""

import gzip
import logging
import os
import shutil
from logging.handlers import RotatingFileHandler
from pathlib import Path

from src.config.settings import settings


class CompressedRotatingFileHandler(RotatingFileHandler):
    """RotatingFileHandler that compresses rotated log files with gzip."""

    def rotation_filename(self, default_name: str) -> str:
        return default_name + ".gz"

    def rotate(self, source: str, dest: str) -> None:
        with open(source, "rb") as f_in:
            with gzip.open(dest, "wb") as f_out:
                shutil.copyfileobj(f_in, f_out)
        os.remove(source)


def configure_file_logging() -> None:
    """
    Add a rotating file handler to the root logger.
    This writes to the log FILE only (not console).
    Console output is handled by structured_logger.py.
    """
    log_path = Path(settings.LOG_FILE_PATH)
    log_path.parent.mkdir(parents=True, exist_ok=True)

    handler = CompressedRotatingFileHandler(
        filename=str(log_path),
        maxBytes=settings.LOG_MAX_BYTES,
        backupCount=settings.LOG_BACKUP_COUNT,
        encoding="utf-8",
    )

    # File gets a readable format (not JSON)
    formatter = logging.Formatter(
        fmt="%(asctime)s | %(levelname)-5s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    handler.setFormatter(formatter)
    handler.setLevel(getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO))

    # Only add to root logger — it will receive events from all loggers
    logging.getLogger().addHandler(handler)
