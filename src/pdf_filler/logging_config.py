"""Centralised logging configuration.

The package uses the standard ``logging`` module with a ``rich`` handler when
available. **Never log raw field values** — they may be PII (passport numbers,
addresses, dates of birth). Log field names and outcomes only.
"""

from __future__ import annotations

import logging
from typing import Final

from rich.logging import RichHandler

_LOGGER_NAME: Final[str] = "pdf_filler"
_DEFAULT_FORMAT: Final[str] = "%(message)s"
_configured: bool = False


def configure_logging(level: int | str = logging.INFO, *, force: bool = False) -> logging.Logger:
    """Configure the package logger and return it.

    Args:
        level: Logging level (int or string name).
        force: Re-apply configuration even if already configured.
    """
    global _configured
    logger = logging.getLogger(_LOGGER_NAME)

    if _configured and not force:
        logger.setLevel(level)
        return logger

    # Wipe any handlers installed by an earlier configuration to keep things clean.
    for handler in list(logger.handlers):
        logger.removeHandler(handler)

    handler = RichHandler(
        rich_tracebacks=True,
        show_time=True,
        show_path=False,
        markup=False,
    )
    handler.setFormatter(logging.Formatter(_DEFAULT_FORMAT, datefmt="[%X]"))

    logger.addHandler(handler)
    logger.setLevel(level)
    logger.propagate = False  # don't double-print via root
    _configured = True
    return logger


def get_logger(name: str | None = None) -> logging.Logger:
    """Return a child logger under the ``pdf_filler`` namespace."""
    if name is None or name == _LOGGER_NAME:
        return logging.getLogger(_LOGGER_NAME)
    return logging.getLogger(f"{_LOGGER_NAME}.{name}")
