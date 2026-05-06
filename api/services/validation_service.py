"""Pre-fill input data validation against a fields config.

Checks that all *required* fields have values and returns a structured
report of present/absent optional fields — without touching PyMuPDF.
"""

from __future__ import annotations

from typing import Any

from api.schemas.submission import ValidationResponse
from pdf_filler.models import FieldsConfig
from pdf_filler.utils import is_empty_value


def validate_data_against_map(
    template_id: str,
    data: dict[str, Any],
    fields_config: FieldsConfig,
) -> ValidationResponse:
    errors: list[str] = []
    fields_present: list[str] = []
    fields_missing_optional: list[str] = []

    for name, cfg in fields_config.fields.items():
        value = data.get(cfg.data_key)
        empty = is_empty_value(value)

        if not empty:
            fields_present.append(name)
        elif cfg.required:
            errors.append(
                f"Required field '{name}' (data_key: '{cfg.data_key}') is missing."
            )
        else:
            fields_missing_optional.append(name)

    return ValidationResponse(
        template_id=template_id,
        valid=len(errors) == 0,
        fields_present=fields_present,
        fields_missing_optional=fields_missing_optional,
        errors=errors,
    )
