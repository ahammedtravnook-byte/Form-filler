"""Shared pytest fixtures.

These fixtures synthesise a small 4-page A4 PDF and a minimal coordinate map
so that every test runs hermetically — no real Schengen template required.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import fitz  # PyMuPDF
import pytest

from pdf_filler.models import CoordinateMap


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
def small_coordinate_map() -> dict[str, Any]:
    """A small but representative coordinate map dict."""
    return {
        "template_id": "synthetic",
        "template_version": "1.0.0",
        "page_size": "A4",
        "coordinate_system": "pymupdf",
        "units": "points",
        "fields": {
            "surname": {
                "type": "text",
                "source": "applicant.surname",
                "page": 1,
                "x": 50,
                "y": 200,
                "font_size": 10,
                "font": "helv",
                "required": True,
                "max_width": 400,
                "align": "left",
                "overflow": "shrink",
                "min_font_size": 7,
            },
            "middle_name": {
                "type": "text",
                "source": "applicant.middle_name",
                "page": 1,
                "x": 50,
                "y": 220,
                "font_size": 10,
                "required": False,
                "max_width": 400,
            },
            "dob": {
                "type": "date",
                "source": "applicant.date_of_birth",
                "page": 1,
                "x": 50,
                "y": 250,
                "format": "%d-%m-%Y",
                "required": True,
                "max_width": 200,
                "overflow": "error",
            },
            "address": {
                "type": "multiline_text",
                "source": "applicant.home_address",
                "page": 2,
                "x": 50,
                "y": 100,
                "font_size": 9,
                "required": True,
                "max_width": 400,
                "line_height": 11,
                "max_lines": 4,
                "overflow": "error",
            },
            "sex_male": {
                "type": "checkbox",
                "source": "applicant.sex",
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
                "source": "applicant.is_student",
                "page": 1,
                "x": 70,
                "y": 300,
                "box_size": 8,
                "check_style": "check",
                "required": False,
            },
        },
    }


@pytest.fixture
def small_input_data() -> dict[str, Any]:
    """Input data that satisfies all required fields in ``small_coordinate_map``."""
    return {
        "applicant": {
            "surname": "DOE",
            "first_names": "JOHN",
            "date_of_birth": "1990-04-21",
            "home_address": "123 Example St, Mumbai, India",
            "sex": "male",
            "is_student": True,
        }
    }


@pytest.fixture
def written_coord_map(
    tmp_path: Path, small_coordinate_map: dict[str, Any]
) -> Path:
    path = tmp_path / "coordinate_map.json"
    path.write_text(json.dumps(small_coordinate_map), encoding="utf-8")
    return path


@pytest.fixture
def written_input_data(
    tmp_path: Path, small_input_data: dict[str, Any]
) -> Path:
    path = tmp_path / "input_data.json"
    path.write_text(json.dumps(small_input_data), encoding="utf-8")
    return path


@pytest.fixture
def coord_map_obj(small_coordinate_map: dict[str, Any]) -> CoordinateMap:
    return CoordinateMap.model_validate(small_coordinate_map)
