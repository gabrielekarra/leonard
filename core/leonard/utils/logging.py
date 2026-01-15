"""Logging configuration for Leonard Core."""

import logging
import sys


def setup_logging(level: int = logging.INFO) -> logging.Logger:
    """Configure and return the application logger."""
    logger = logging.getLogger("leonard")
    logger.setLevel(level)

    if not logger.handlers:
        handler = logging.StreamHandler(sys.stdout)
        handler.setLevel(level)
        formatter = logging.Formatter(
            "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
        handler.setFormatter(formatter)
        logger.addHandler(handler)

    return logger


logger = setup_logging()
