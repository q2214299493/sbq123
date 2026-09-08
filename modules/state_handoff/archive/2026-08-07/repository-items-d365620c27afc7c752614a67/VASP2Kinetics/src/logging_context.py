"""Shared temporary attachment of configured phase-specific log files."""

from __future__ import annotations

import logging
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from .exceptions import LoggingError


@contextmanager
def phase_log(logger: logging.Logger, path: str | Path) -> Iterator[None]:
    """Attach one configured file handler without duplicating existing handlers."""

    resolved = Path(path).expanduser().resolve()
    for existing in logger.handlers:
        if isinstance(existing, logging.FileHandler) and Path(
            existing.baseFilename
        ).resolve() == resolved:
            yield
            return
    try:
        resolved.parent.mkdir(parents=True, exist_ok=True)
        handler = logging.FileHandler(resolved, encoding="utf-8")
    except OSError as exc:
        raise LoggingError(f"PHASE_LOG_OPEN_ERROR: {resolved}") from exc
    handler.setFormatter(
        logging.Formatter(
            "%(asctime)s | %(levelname)s | %(name)s | %(message)s",
            datefmt="%Y-%m-%dT%H:%M:%S%z",
        )
    )
    logger.addHandler(handler)
    try:
        yield
    finally:
        logger.removeHandler(handler)
        handler.close()
