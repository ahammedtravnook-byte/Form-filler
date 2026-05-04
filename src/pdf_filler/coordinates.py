"""Coordinate-map loading and inspection helpers.

This module wraps :class:`pdf_filler.models.CoordinateMap` with file IO and a
human-friendly inspection summary used by the ``inspect-template`` and
``validate-coordinate-map`` CLI commands.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from pydantic import ValidationError

from .exceptions import CoordinateMapError
from .models import CoordinateMap
from .utils import load_json


def load_coordinate_map(path: Path) -> CoordinateMap:
    """Load and validate a coordinate map JSON file.

    Raises :class:`CoordinateMapError` with a multi-line message that contains
    every Pydantic validation error in order, so misconfigured maps are easy
    to debug.
    """
    if not path.exists():
        raise CoordinateMapError(f"Coordinate map not found: {path}")

    try:
        raw = load_json(path)
    except ValueError as exc:
        raise CoordinateMapError(str(exc)) from exc

    if not isinstance(raw, dict):
        raise CoordinateMapError("Coordinate map JSON must be an object at the top level.")

    try:
        return CoordinateMap.model_validate(raw)
    except ValidationError as exc:
        # Re-raise with a flat, readable summary.
        lines = [f"Invalid coordinate map at {path}:"]
        for err in exc.errors():
            loc = ".".join(str(p) for p in err["loc"])
            lines.append(f"  - {loc}: {err['msg']}")
        raise CoordinateMapError("\n".join(lines)) from exc


def page_iter(coord_map: CoordinateMap) -> dict[int, list[str]]:
    """Group field names by 1-based page number for easy iteration/reporting."""
    grouped: dict[int, list[str]] = {}
    for name, field in coord_map.fields.items():
        grouped.setdefault(field.page, []).append(name)
    return grouped


def summarise_coordinate_map(coord_map: CoordinateMap) -> dict[str, Any]:
    """Return a structured summary suitable for printing or JSON output."""
    by_type: dict[str, int] = {}
    for field in coord_map.fields.values():
        by_type[field.type] = by_type.get(field.type, 0) + 1

    return {
        "template_id": coord_map.template_id,
        "template_version": coord_map.template_version,
        "page_size": coord_map.page_size,
        "field_count": len(coord_map.fields),
        "fields_by_type": by_type,
        "fields_by_page": {p: len(names) for p, names in page_iter(coord_map).items()},
    }
