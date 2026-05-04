"""Tests for Pydantic models and coordinate-map loading."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from pdf_filler.coordinates import load_coordinate_map, summarise_coordinate_map
from pdf_filler.exceptions import CoordinateMapError
from pdf_filler.models import (
    CheckboxFieldConfig,
    CoordinateMap,
    DateFieldConfig,
    MultilineTextFieldConfig,
    TemplateMetadata,
    TextFieldConfig,
)


def test_text_field_config_defaults() -> None:
    cfg = TextFieldConfig(source="a.b", page=1, x=10, y=20)
    assert cfg.type == "text"
    assert cfg.font_size == 10.0
    assert cfg.font == "helv"
    assert cfg.align == "left"
    assert cfg.overflow == "error"
    assert cfg.required is False


def test_text_field_min_font_size_must_not_exceed_font_size() -> None:
    with pytest.raises(ValidationError):
        TextFieldConfig(
            source="a", page=1, x=0, y=0, font_size=8, min_font_size=12
        )


def test_multiline_field_requires_max_width_and_line_height() -> None:
    with pytest.raises(ValidationError):
        MultilineTextFieldConfig(
            source="a.b", page=1, x=0, y=0  # type: ignore[call-arg]
        )


def test_checkbox_field_basic() -> None:
    cfg = CheckboxFieldConfig(
        source="a.b", page=1, x=0, y=0, checked_when="male", check_style="x"
    )
    assert cfg.type == "checkbox"
    assert cfg.box_size == 8.0


def test_date_field_basic() -> None:
    cfg = DateFieldConfig(source="a.b", page=1, x=0, y=0, format="%d-%m-%Y")
    assert cfg.type == "date"
    assert cfg.format == "%d-%m-%Y"


def test_coordinate_map_discriminated_union(small_coordinate_map: dict[str, Any]) -> None:
    cmap = CoordinateMap.model_validate(small_coordinate_map)
    assert isinstance(cmap.fields["surname"], TextFieldConfig)
    assert isinstance(cmap.fields["dob"], DateFieldConfig)
    assert isinstance(cmap.fields["address"], MultilineTextFieldConfig)
    assert isinstance(cmap.fields["sex_male"], CheckboxFieldConfig)


def test_coordinate_map_rejects_unknown_field_type(
    small_coordinate_map: dict[str, Any],
) -> None:
    bad = dict(small_coordinate_map)
    bad["fields"] = dict(bad["fields"])
    bad["fields"]["weird"] = {
        "type": "not_a_real_type",
        "source": "x",
        "page": 1,
        "x": 0,
        "y": 0,
    }
    with pytest.raises(ValidationError):
        CoordinateMap.model_validate(bad)


def test_coordinate_map_rejects_extra_keys(small_coordinate_map: dict[str, Any]) -> None:
    bad = dict(small_coordinate_map)
    bad["fields"] = dict(bad["fields"])
    bad["fields"]["surname"] = {**bad["fields"]["surname"], "made_up_key": 1}
    with pytest.raises(ValidationError):
        CoordinateMap.model_validate(bad)


def test_coordinate_map_must_be_non_empty() -> None:
    with pytest.raises(ValidationError):
        CoordinateMap.model_validate(
            {
                "template_id": "x",
                "template_version": "1",
                "page_size": "A4",
                "coordinate_system": "pymupdf",
                "units": "points",
                "fields": {},
            }
        )


def test_load_coordinate_map_missing_file(tmp_path: Path) -> None:
    with pytest.raises(CoordinateMapError, match="not found"):
        load_coordinate_map(tmp_path / "nope.json")


def test_load_coordinate_map_invalid_json(tmp_path: Path) -> None:
    p = tmp_path / "bad.json"
    p.write_text("{not valid json", encoding="utf-8")
    with pytest.raises(CoordinateMapError):
        load_coordinate_map(p)


def test_load_coordinate_map_top_level_must_be_object(tmp_path: Path) -> None:
    p = tmp_path / "list.json"
    p.write_text("[]", encoding="utf-8")
    with pytest.raises(CoordinateMapError, match="object at the top level"):
        load_coordinate_map(p)


def test_load_coordinate_map_validation_error_lists_each_problem(
    tmp_path: Path, small_coordinate_map: dict[str, Any]
) -> None:
    bad = json.loads(json.dumps(small_coordinate_map))
    bad["fields"]["surname"]["page"] = -1  # invalid (PositiveInt)
    p = tmp_path / "bad.json"
    p.write_text(json.dumps(bad), encoding="utf-8")
    with pytest.raises(CoordinateMapError) as exc_info:
        load_coordinate_map(p)
    assert "page" in str(exc_info.value)


def test_summarise_coordinate_map(small_coordinate_map: dict[str, Any]) -> None:
    cmap = CoordinateMap.model_validate(small_coordinate_map)
    summary = summarise_coordinate_map(cmap)
    assert summary["field_count"] == len(small_coordinate_map["fields"])
    assert summary["fields_by_type"]["text"] >= 1
    assert summary["fields_by_type"]["checkbox"] >= 1
    assert summary["fields_by_page"][1] >= 1


def test_template_metadata_sha_validation() -> None:
    TemplateMetadata(template_id="x", template_version="1", expected_pages=4)  # ok empty
    TemplateMetadata(
        template_id="x",
        template_version="1",
        expected_pages=4,
        sha256="a" * 64,
    )
    with pytest.raises(ValidationError):
        TemplateMetadata(
            template_id="x",
            template_version="1",
            expected_pages=4,
            sha256="not-hex",
        )
    with pytest.raises(ValidationError):
        TemplateMetadata(
            template_id="x",
            template_version="1",
            expected_pages=4,
            sha256="a" * 63,  # wrong length
        )
