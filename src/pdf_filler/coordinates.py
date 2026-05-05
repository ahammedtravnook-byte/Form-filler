"""Fields-config loading and inspection helpers.

This module wraps :class:`pdf_filler.models.FieldsConfig` with file IO and a
human-friendly inspection summary used by the ``inspect-template`` and
``validate-fields-config`` CLI commands.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from pydantic import ValidationError

from .exceptions import CoordinateMapError
from .models import FieldsConfig
from .utils import load_json


def load_fields_config(path: Path) -> FieldsConfig:
    """Load and validate a fields config JSON file.

    Raises :class:`CoordinateMapError` with a multi-line message that contains
    every Pydantic validation error in order, so misconfigured configs are
    easy to debug.
    """
    if not path.exists():
        raise CoordinateMapError(f"Fields config not found: {path}")

    try:
        raw = load_json(path)
    except ValueError as exc:
        raise CoordinateMapError(str(exc)) from exc

    if not isinstance(raw, dict):
        raise CoordinateMapError("Fields config JSON must be an object at the top level.")

    try:
        return FieldsConfig.model_validate(raw)
    except ValidationError as exc:
        lines = [f"Invalid fields config at {path}:"]
        for err in exc.errors():
            loc = ".".join(str(p) for p in err["loc"])
            lines.append(f"  - {loc}: {err['msg']}")
        raise CoordinateMapError("\n".join(lines)) from exc


# Back-compat alias — older callers still import ``load_coordinate_map``.
load_coordinate_map = load_fields_config


def page_iter(config: FieldsConfig) -> dict[int, list[str]]:
    """Group field names by 1-based page number for easy iteration/reporting."""
    grouped: dict[int, list[str]] = {}
    for name, field in config.fields.items():
        grouped.setdefault(field.page, []).append(name)
    return grouped


def summarise_fields_config(config: FieldsConfig) -> dict[str, Any]:
    """Return a structured summary suitable for printing or JSON output."""
    by_type: dict[str, int] = {}
    for field in config.fields.values():
        by_type[field.type] = by_type.get(field.type, 0) + 1

    return {
        "form_name": config.form_name,
        "field_count": len(config.fields),
        "page_count": len(config.pages),
        "fields_by_type": by_type,
        "fields_by_page": {p: len(names) for p, names in page_iter(config).items()},
    }


# Back-compat alias.
summarise_coordinate_map = summarise_fields_config
