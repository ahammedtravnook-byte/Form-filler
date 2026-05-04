"""Tests for utils helpers and coordinate-map page validation."""

from __future__ import annotations

from pathlib import Path

import pytest

from pdf_filler.exceptions import (
    CoordinateMapError,
    DataValidationError,
    PageOutOfRangeError,
    TemplateMismatchError,
)
from pdf_filler.models import CoordinateMap, TemplateMetadata
from pdf_filler.utils import (
    MISSING,
    is_empty_value,
    is_missing,
    resolve_path,
    safe_resolve_output_path,
    sha256_file,
)
from pdf_filler.validators import (
    load_template_metadata,
    parse_date_value,
    validate_input_data,
    validate_metadata_page_count,
    validate_pages_in_range,
    validate_template_path,
)

# --------------------------------------------------------------------------- #
# resolve_path / is_empty_value                                                #
# --------------------------------------------------------------------------- #


def test_resolve_path_simple() -> None:
    data = {"a": {"b": {"c": 42}}}
    assert resolve_path(data, "a.b.c") == 42


def test_resolve_path_missing_segment_returns_missing() -> None:
    data = {"a": {"b": {}}}
    assert is_missing(resolve_path(data, "a.b.c"))


def test_resolve_path_falsy_value_is_present_not_missing() -> None:
    data = {"a": {"b": ""}}
    val = resolve_path(data, "a.b")
    assert val == ""
    assert not is_missing(val)


def test_resolve_path_empty_path_returns_missing() -> None:
    assert resolve_path({"a": 1}, "") is MISSING


def test_resolve_path_through_non_dict_returns_missing() -> None:
    data = {"a": "string"}
    assert is_missing(resolve_path(data, "a.b"))


def test_is_empty_value_for_typical_values() -> None:
    assert is_empty_value(MISSING)
    assert is_empty_value(None)
    assert is_empty_value("")
    assert is_empty_value("   ")
    assert not is_empty_value("x")
    assert not is_empty_value(0)        # explicit numeric zero
    assert not is_empty_value(False)    # explicit boolean false


# --------------------------------------------------------------------------- #
# safe_resolve_output_path                                                     #
# --------------------------------------------------------------------------- #


def test_safe_resolve_output_path_inside_root(tmp_path: Path) -> None:
    out = tmp_path / "sub" / "out.pdf"
    resolved = safe_resolve_output_path(out, allowed_root=tmp_path)
    assert resolved == out.resolve()


def test_safe_resolve_output_path_outside_root_raises(tmp_path: Path) -> None:
    sibling = tmp_path.parent / "elsewhere" / "out.pdf"
    with pytest.raises(ValueError, match="outside the allowed root"):
        safe_resolve_output_path(sibling, allowed_root=tmp_path)


# --------------------------------------------------------------------------- #
# sha256_file                                                                  #
# --------------------------------------------------------------------------- #


def test_sha256_file(tmp_path: Path) -> None:
    p = tmp_path / "x.bin"
    p.write_bytes(b"hello")
    # SHA-256 of b"hello"
    expected = "2cf24dba5fb0a30e26e83b2ac5b9e29e1b161e5c1fa7425e73043362938b9824"
    assert sha256_file(p) == expected


# --------------------------------------------------------------------------- #
# Page-range validation                                                        #
# --------------------------------------------------------------------------- #


def test_validate_pages_in_range_ok(coord_map_obj: CoordinateMap) -> None:
    validate_pages_in_range(coord_map_obj, pdf_page_count=4)


def test_validate_pages_in_range_too_high(coord_map_obj: CoordinateMap) -> None:
    with pytest.raises(PageOutOfRangeError) as exc_info:
        validate_pages_in_range(coord_map_obj, pdf_page_count=1)
    err = exc_info.value
    # address is on page 2 in the fixture; should be the first to fail OR another field on >1
    assert err.page > 1
    assert err.page_count == 1


def test_metadata_page_count_mismatch_raises() -> None:
    meta = TemplateMetadata(template_id="x", template_version="1", expected_pages=4)
    with pytest.raises(TemplateMismatchError, match="page count"):
        validate_metadata_page_count(meta, pdf_page_count=3)


def test_metadata_none_skips_check() -> None:
    validate_metadata_page_count(None, pdf_page_count=99)


# --------------------------------------------------------------------------- #
# Template path validation                                                     #
# --------------------------------------------------------------------------- #


def test_validate_template_path_missing(tmp_path: Path) -> None:
    from pdf_filler.exceptions import TemplateNotFoundError

    with pytest.raises(TemplateNotFoundError):
        validate_template_path(tmp_path / "nope.pdf")


def test_validate_template_path_empty_file(tmp_path: Path) -> None:
    from pdf_filler.exceptions import TemplateNotFoundError

    p = tmp_path / "empty.pdf"
    p.write_bytes(b"")
    with pytest.raises(TemplateNotFoundError, match="empty"):
        validate_template_path(p)


# --------------------------------------------------------------------------- #
# Input data validation                                                        #
# --------------------------------------------------------------------------- #


def test_validate_input_data_ok(written_input_data: Path) -> None:
    raw = validate_input_data(written_input_data)
    assert "applicant" in raw


def test_validate_input_data_missing_file(tmp_path: Path) -> None:
    with pytest.raises(DataValidationError):
        validate_input_data(tmp_path / "nope.json")


def test_validate_input_data_top_level_must_be_object(tmp_path: Path) -> None:
    p = tmp_path / "arr.json"
    p.write_text("[1,2,3]", encoding="utf-8")
    with pytest.raises(DataValidationError, match="object at the top level"):
        validate_input_data(p)


# --------------------------------------------------------------------------- #
# Template metadata loading                                                    #
# --------------------------------------------------------------------------- #


def test_load_template_metadata_none() -> None:
    assert load_template_metadata(None) is None


def test_load_template_metadata_ok(tmp_path: Path) -> None:
    p = tmp_path / "meta.json"
    p.write_text(
        '{"template_id":"x","template_version":"1","expected_pages":4,"sha256":""}',
        encoding="utf-8",
    )
    meta = load_template_metadata(p)
    assert meta is not None
    assert meta.expected_pages == 4


def test_load_template_metadata_missing_file(tmp_path: Path) -> None:
    with pytest.raises(CoordinateMapError):
        load_template_metadata(tmp_path / "nope.json")


# --------------------------------------------------------------------------- #
# Date parsing                                                                 #
# --------------------------------------------------------------------------- #


def test_parse_date_iso() -> None:
    d = parse_date_value("1990-04-21")
    assert (d.year, d.month, d.day) == (1990, 4, 21)


def test_parse_date_invalid_raises() -> None:
    with pytest.raises(DataValidationError):
        parse_date_value(12345)  # type: ignore[arg-type]
