"""Pre-flight validators run before the PDF is touched.

Each validator raises a specific subclass of
:class:`pdf_filler.exceptions.PdfFillerError` on failure. They are kept here
so that :class:`pdf_filler.filler.PdfFiller` can stay focused on rendering.
"""

from __future__ import annotations

import datetime as dt
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from .config import SETTINGS
from .exceptions import (
    CoordinateMapError,
    DataValidationError,
    PageOutOfRangeError,
    TemplateMismatchError,
    TemplateNotFoundError,
)
from .models import FieldsConfig, TemplateMetadata
from .utils import load_json, sha256_file


def validate_template_path(path: Path) -> Path:
    """Ensure template exists, is a file, is non-empty, and not too large."""
    if not path.exists():
        raise TemplateNotFoundError(f"Template PDF not found: {path}")
    if not path.is_file():
        raise TemplateNotFoundError(f"Template path is not a file: {path}")

    size = path.stat().st_size
    if size == 0:
        raise TemplateNotFoundError(f"Template file is empty: {path}")
    if size > SETTINGS.max_template_bytes:
        raise TemplateNotFoundError(
            f"Template {path} is {size} bytes, exceeds limit "
            f"{SETTINGS.max_template_bytes} bytes."
        )
    return path


def validate_template_hash(
    template_path: Path,
    metadata: TemplateMetadata | None,
    *,
    ignore: bool = False,
) -> str | None:
    """Verify the template SHA-256 against metadata.

    Returns the computed hash so callers can log it.

    Args:
        template_path: Path to the template PDF.
        metadata: Optional template metadata.
        ignore: When ``True``, mismatches do not raise (used by
            ``--ignore-template-hash``).
    """
    if metadata is None or metadata.sha256 == "":
        return None  # caller should warn at info level

    actual = sha256_file(template_path)
    if actual.lower() != metadata.sha256.lower():
        if ignore:
            return actual
        raise TemplateMismatchError(
            f"Template SHA-256 mismatch: expected {metadata.sha256}, got {actual}. "
            f"Pass --ignore-template-hash to override."
        )
    return actual


def validate_pages_in_range(
    fields_config: FieldsConfig,
    pdf_page_count: int,
) -> None:
    """Make sure every field references a page that exists in the template."""
    for name, field in fields_config.fields.items():
        if field.page < 1 or field.page > pdf_page_count:
            raise PageOutOfRangeError(name, field.page, pdf_page_count)


def validate_metadata_page_count(
    metadata: TemplateMetadata | None,
    pdf_page_count: int,
) -> None:
    """If metadata declares an expected page count, the PDF must match it."""
    if metadata is None:
        return
    if metadata.expected_pages != pdf_page_count:
        raise TemplateMismatchError(
            f"Template page count mismatch: metadata says {metadata.expected_pages}, "
            f"PDF has {pdf_page_count}."
        )


def validate_input_data(data_path: Path) -> dict[str, Any]:
    """Load input data JSON and perform light shape validation."""
    if not data_path.exists():
        raise DataValidationError(f"Input data file not found: {data_path}")
    size = data_path.stat().st_size
    if size > SETTINGS.max_data_bytes:
        raise DataValidationError(
            f"Input data file {data_path} is {size} bytes, exceeds limit "
            f"{SETTINGS.max_data_bytes} bytes."
        )
    try:
        raw = load_json(data_path)
    except ValueError as exc:
        raise DataValidationError(str(exc)) from exc

    if not isinstance(raw, dict):
        raise DataValidationError(
            f"Input data must be a JSON object at the top level (got {type(raw).__name__})."
        )
    return raw


def load_template_metadata(path: Path | None) -> TemplateMetadata | None:
    """Load and validate template metadata if a path was provided."""
    if path is None:
        return None
    if not path.exists():
        raise CoordinateMapError(f"Template metadata not found: {path}")
    try:
        raw = load_json(path)
    except ValueError as exc:
        raise CoordinateMapError(str(exc)) from exc
    if not isinstance(raw, dict):
        raise CoordinateMapError("Template metadata JSON must be an object.")
    try:
        return TemplateMetadata.model_validate(raw)
    except ValidationError as exc:
        lines = [f"Invalid template metadata at {path}:"]
        for err in exc.errors():
            loc = ".".join(str(p) for p in err["loc"])
            lines.append(f"  - {loc}: {err['msg']}")
        raise CoordinateMapError("\n".join(lines)) from exc


# --------------------------------------------------------------------------- #
# Date parsing helper                                                          #
# --------------------------------------------------------------------------- #


def parse_date_value(value: Any) -> dt.date:
    """Parse a date from a string or accept a :class:`datetime.date`.

    Accepts ISO 8601 (``YYYY-MM-DD``) by default. Falls back to
    ``python-dateutil`` if installed, allowing more permissive inputs without
    making it a required dependency.
    """
    if isinstance(value, dt.date) and not isinstance(value, dt.datetime):
        return value
    if isinstance(value, dt.datetime):
        return value.date()
    if isinstance(value, str):
        candidate = value.strip()
        try:
            return dt.date.fromisoformat(candidate)
        except ValueError:
            pass
        try:
            from dateutil import parser as _du_parser  # type: ignore[import-untyped]
        except ImportError as exc:
            raise DataValidationError(
                f"Could not parse date '{value}' as ISO 8601 (YYYY-MM-DD). "
                f"Install python-dateutil for more permissive parsing."
            ) from exc
        try:
            return _du_parser.parse(candidate).date()
        except (ValueError, TypeError) as exc:
            raise DataValidationError(f"Could not parse date '{value}': {exc}") from exc
    raise DataValidationError(
        f"Unsupported date value type {type(value).__name__}: {value!r}"
    )
