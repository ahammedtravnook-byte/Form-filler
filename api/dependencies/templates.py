"""Dependency that resolves the templates root from settings."""

from __future__ import annotations

from pathlib import Path

from api.core.config import settings


def get_templates_root() -> Path:
    """FastAPI dependency — returns the configured templates directory."""
    return settings.templates_dir
