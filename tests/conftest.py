"""Shared pytest fixtures.

These fixtures synthesise a small 4-page A4 PDF and a minimal fields config
so that every test runs hermetically — no real Schengen template required.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import fitz  # PyMuPDF
import pytest

from pdf_filler.models import FieldsConfig


@pytest.fixture
def synthetic_template(tmp_path: Path) -> Path:
    """Create a 4-page A4 PDF with a couple of printed labels."""
    path = tmp_path / "synthetic_template.pdf"
    doc = fitz.open()
    for page_no in range(1, 5):
        page = doc.new_page(width=595, height=842)  # A4
        page.insert_text(
            fitz.Point(50, 50),
            f"Synthetic test template — page {page_no}",
            fontname="helv",
            fontsize=12,
        )
    doc.save(str(path))
    doc.close()
    return path


@pytest.fixture
def small_fields_config() -> dict[str, Any]:
    """A small but representative fields config dict."""
    return {
        "form_name": "Synthetic Form",
        "pages": [
            {"page_number": 1, "pdf_width": 595, "pdf_height": 842},
            {"page_number": 2, "pdf_width": 595, "pdf_height": 842},
        ],
        "fields": {
            "surname": {
                "data_key": "surname",
                "page": 1,
                "x": 50,
                "y": 200,
                "font_size": 10,
                "font": "helv",
                "required": True,
                "width": 400,
                "align": "left",
                "overflow": "shrink",
                "min_font_size": 7,
            },
            "middle_name": {
                "data_key": "middle_name",
                "page": 1,
                "x": 50,
                "y": 220,
                "font_size": 10,
                "required": False,
                "width": 400,
            },
            "dob": {
                "type": "date",
                "data_key": "date_of_birth",
                "page": 1,
                "x": 50,
                "y": 250,
                "format": "%d-%m-%Y",
                "required": True,
                "width": 200,
                "overflow": "error",
            },
            "address": {
                "type": "multiline_text",
                "data_key": "home_address",
                "page": 2,
                "x": 50,
                "y": 100,
                "font_size": 9,
                "required": True,
                "width": 400,
                "line_height": 11,
                "max_lines": 4,
                "overflow": "error",
            },
            "sex_male": {
                "type": "checkbox",
                "data_key": "sex",
                "page": 1,
                "x": 50,
                "y": 300,
                "box_size": 8,
                "checked_when": "male",
                "check_style": "x",
                "required": False,
            },
            "is_student": {
                "type": "checkbox",
                "data_key": "is_student",
                "page": 1,
                "x": 70,
                "y": 300,
                "box_size": 8,
                "check_style": "check",
                "required": False,
            },
            "civil_status": {
                "type": "checkbox_group",
                "data_key": "civil_status",
                "page": 1,
                "description": "Civil status group",
                "options": {
                    "Single":  {"x": 90,  "y": 300},
                    "Married": {"x": 110, "y": 300},
                },
            },
        },
    }


# Back-compat alias so older tests still importing ``small_coordinate_map`` keep working.
@pytest.fixture
def small_coordinate_map(small_fields_config: dict[str, Any]) -> dict[str, Any]:
    return small_fields_config


@pytest.fixture
def small_input_data() -> dict[str, Any]:
    """Input data that satisfies all required fields in ``small_fields_config``."""
    return {
        "surname": "DOE",
        "first_names": "JOHN",
        "date_of_birth": "1990-04-21",
        "home_address": "123 Example St, Mumbai, India",
        "sex": "male",
        "is_student": True,
        "civil_status": "Married",
    }


@pytest.fixture
def written_fields_config(
    tmp_path: Path, small_fields_config: dict[str, Any]
) -> Path:
    path = tmp_path / "fields_config.json"
    path.write_text(json.dumps(small_fields_config), encoding="utf-8")
    return path


@pytest.fixture
def written_coord_map(written_fields_config: Path) -> Path:
    """Back-compat alias for the older fixture name."""
    return written_fields_config


@pytest.fixture
def written_input_data(
    tmp_path: Path, small_input_data: dict[str, Any]
) -> Path:
    path = tmp_path / "input_data.json"
    path.write_text(json.dumps(small_input_data), encoding="utf-8")
    return path


@pytest.fixture
def fields_config_obj(small_fields_config: dict[str, Any]) -> FieldsConfig:
    return FieldsConfig.model_validate(small_fields_config)


@pytest.fixture
def coord_map_obj(fields_config_obj: FieldsConfig) -> FieldsConfig:
    """Back-compat alias for the older fixture name."""
    return fields_config_obj
