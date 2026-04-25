"""
Logger utility module.
"""

import logging
import logging.config
from typing import Optional

from src.utils.config import settings


def setup_logging() -> None:
    """Configure application logging."""
    log_config = {
        "version": 1,
        "disable_existing_loggers": False,
        "formatters": {
            "default": {
                "format": "[%(asctime)s] %(levelname)s - %(name)s - %(message)s",
                "datefmt": "%Y-%m-%d %H:%M:%S",
            },
            "detailed": {
                "format": "[%(asctime)s] %(levelname)s - %(name)s:%(lineno)d - %(funcName)s() - %(message)s",
                "datefmt": "%Y-%m-%d %H:%M:%S",
            },
        },
        "handlers": {
            "console": {
                "class": "logging.StreamHandler",
                "level": settings.log_level,
                "formatter": "detailed" if settings.app_debug else "default",
                "stream": "ext://sys.stdout",
            },
        },
        "root": {
            "level": settings.log_level,
            "handlers": ["console"],
        },
    }

    logging.config.dictConfig(log_config)


def get_logger(name: Optional[str] = None) -> logging.Logger:
    """Get or create a logger with the given name."""
    return logging.getLogger(name or __name__)


# Initialize logging on module import
setup_logging()

