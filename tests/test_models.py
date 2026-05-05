"""Tests for Pydantic models and fields-config loading."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from pdf_filler.coordinates import load_fields_config, summarise_fields_config
from pdf_filler.exceptions import CoordinateMapError
from pdf_filler.models import (
    CheckboxFieldConfig,
    CheckboxGroupFieldConfig,
    DateFieldConfig,
    FieldsConfig,
    MultilineTextFieldConfig,
    TemplateMetadata,
    TextFieldConfig,
)


def test_text_field_config_defaults() -> None:
    cfg = TextFieldConfig(data_key="surname", page=1, x=10, y=20)
    assert cfg.type == "text"
    assert cfg.font_size == 9.0
    assert cfg.font == "helv"
    assert cfg.align == "left"
    assert cfg.overflow == "shrink"
    assert cfg.required is False


def test_text_field_min_font_size_must_not_exceed_font_size() -> None:
    with pytest.raises(ValidationError):
        TextFieldConfig(
            data_key="a", page=1, x=0, y=0, font_size=8, min_font_size=12
        )


def test_multiline_field_requires_width() -> None:
    with pytest.raises(ValidationError):
        MultilineTextFieldConfig(
            data_key="a", page=1, x=0, y=0  # type: ignore[call-arg]
        )


def test_checkbox_field_basic() -> None:
    cfg = CheckboxFieldConfig(
        data_key="sex", page=1, x=0, y=0, checked_when="male", check_style="x"
    )
    assert cfg.type == "checkbox"
    assert cfg.box_size == 8.0


def test_checkbox_group_basic() -> None:
    cfg = CheckboxGroupFieldConfig(
        data_key="civil_status",
        page=1,
        type="checkbox_group",
        options={
            "Single": {"x": 10, "y": 20},
            "Married": {"x": 30, "y": 20},
        },
    )
    assert cfg.type == "checkbox_group"
    assert cfg.options["Single"].x == 10


def test_date_field_basic() -> None:
    cfg = DateFieldConfig(
        data_key="dob", page=1, x=0, y=0, type="date", format="%d-%m-%Y"
    )
    assert cfg.type == "date"
    assert cfg.format == "%d-%m-%Y"


def test_fields_config_discriminated_union(small_fields_config: dict[str, Any]) -> None:
    cfg = FieldsConfig.model_validate(small_fields_config)
    assert isinstance(cfg.fields["surname"], TextFieldConfig)
    assert isinstance(cfg.fields["dob"], DateFieldConfig)
    assert isinstance(cfg.fields["address"], MultilineTextFieldConfig)
    assert isinstance(cfg.fields["sex_male"], CheckboxFieldConfig)
    assert isinstance(cfg.fields["civil_status"], CheckboxGroupFieldConfig)


def test_fields_config_rejects_unknown_field_type(
    small_fields_config: dict[str, Any],
) -> None:
    bad = dict(small_fields_config)
    bad["fields"] = dict(bad["fields"])
    bad["fields"]["weird"] = {
        "type": "not_a_real_type",
        "data_key": "x",
        "page": 1,
        "x": 0,
        "y": 0,
    }
    with pytest.raises(ValidationError):
        FieldsConfig.model_validate(bad)


def test_fields_config_rejects_extra_keys(small_fields_config: dict[str, Any]) -> None:
    bad = dict(small_fields_config)
    bad["fields"] = dict(bad["fields"])
    bad["fields"]["surname"] = {**bad["fields"]["surname"], "made_up_key": 1}
    with pytest.raises(ValidationError):
        FieldsConfig.model_validate(bad)


def test_fields_config_must_be_non_empty() -> None:
    with pytest.raises(ValidationError):
        FieldsConfig.model_validate(
            {
                "form_name": "x",
                "pages": [],
                "fields": {},
            }
        )


def test_load_fields_config_missing_file(tmp_path: Path) -> None:
    with pytest.raises(CoordinateMapError, match="not found"):
        load_fields_config(tmp_path / "nope.json")


def test_load_fields_config_invalid_json(tmp_path: Path) -> None:
    p = tmp_path / "bad.json"
    p.write_text("{not valid json", encoding="utf-8")
    with pytest.raises(CoordinateMapError):
        load_fields_config(p)


def test_load_fields_config_top_level_must_be_object(tmp_path: Path) -> None:
    p = tmp_path / "list.json"
    p.write_text("[]", encoding="utf-8")
    with pytest.raises(CoordinateMapError, match="object at the top level"):
        load_fields_config(p)


def test_load_fields_config_validation_error_lists_each_problem(
    tmp_path: Path, small_fields_config: dict[str, Any]
) -> None:
    bad = json.loads(json.dumps(small_fields_config))
    bad["fields"]["surname"]["page"] = -1  # invalid (PositiveInt)
    p = tmp_path / "bad.json"
    p.write_text(json.dumps(bad), encoding="utf-8")
    with pytest.raises(CoordinateMapError) as exc_info:
        load_fields_config(p)
    assert "page" in str(exc_info.value)


def test_summarise_fields_config(small_fields_config: dict[str, Any]) -> None:
    cfg = FieldsConfig.model_validate(small_fields_config)
    summary = summarise_fields_config(cfg)
    assert summary["field_count"] == len(small_fields_config["fields"])
    assert summary["fields_by_type"]["text"] >= 1
    assert summary["fields_by_type"]["checkbox"] >= 1
    assert summary["fields_by_type"]["checkbox_group"] >= 1
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
