"""Configure application logging from validated settings."""

from __future__ import annotations

import logging
import sys

from .config import LoggingSettings
from .exceptions import ConfigurationError

LOGGER_NAME = "vasp2kinetics"


def configure_logging(settings: LoggingSettings) -> logging.Logger:
    """Configure and return the project logger without duplicate handlers."""

    logger = logging.getLogger(LOGGER_NAME)
    logger.setLevel(settings.level)
    logger.propagate = False

    for handler in logger.handlers:
        handler.close()
    logger.handlers.clear()

    formatter = logging.Formatter(
        fmt="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S%z",
    )

    if settings.console:
        console_handler = logging.StreamHandler(sys.stderr)
        console_handler.setFormatter(formatter)
        logger.addHandler(console_handler)

    if settings.file is not None:
        try:
            settings.file.parent.mkdir(parents=True, exist_ok=True)
            file_handler = logging.FileHandler(settings.file, encoding="utf-8")
        except OSError as exc:
            raise ConfigurationError(
                f"Unable to open configured log file: {settings.file}"
            ) from exc
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)

    return logger
