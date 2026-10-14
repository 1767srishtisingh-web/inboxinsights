# modules/logger.py
"""
Centralized logging. Every run writes structured entries to
logs/application.log (rotated so it never grows unbounded) and mirrors
INFO+ to the console.
"""

import logging
import os
from logging.handlers import RotatingFileHandler

from config.settings import LOGS_DIR

os.makedirs(LOGS_DIR, exist_ok=True)
LOG_FILE = os.path.join(LOGS_DIR, "application.log")

_FORMAT = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"


def get_logger(name: str = "inbox_insights") -> logging.Logger:
    logger = logging.getLogger(name)
    if logger.handlers:  # already configured (avoid duplicate handlers)
        return logger

    logger.setLevel(logging.DEBUG)

    file_handler = RotatingFileHandler(
        LOG_FILE, maxBytes=5 * 1024 * 1024, backupCount=5, encoding="utf-8"
    )
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(logging.Formatter(_FORMAT))

    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(logging.Formatter(_FORMAT))

    logger.addHandler(file_handler)
    logger.addHandler(console_handler)
    return logger
