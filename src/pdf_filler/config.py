"""Package-wide constants and runtime configuration.

These values can be overridden via environment variables for deployments where
the defaults are too restrictive (e.g. CI bundling many high-resolution scans).
"""

from __future__ import annotations

import os
from dataclasses import dataclass


def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def _env_bool(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Settings:
    """Runtime safety/limits settings."""

    # Maximum template PDF size in bytes (default 50 MB).
    max_template_bytes: int = _env_int("PDF_FILLER_MAX_TEMPLATE_BYTES", 50 * 1024 * 1024)

    # Maximum allowed input data file size in bytes (default 1 MB).
    max_data_bytes: int = _env_int("PDF_FILLER_MAX_DATA_BYTES", 1 * 1024 * 1024)

    # Whether to allow encrypted PDFs at all (currently unsupported).
    allow_encrypted_pdfs: bool = _env_bool("PDF_FILLER_ALLOW_ENCRYPTED", False)

    # Default checkbox box size in points (used if not specified per-field).
    default_checkbox_size: float = 8.0

    # Default font for text fields if not specified.
    default_font: str = "helv"


SETTINGS = Settings()
