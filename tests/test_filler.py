"""End-to-end tests for the PdfFiller engine."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import fitz  # PyMuPDF
import pytest

from pdf_filler.exceptions import (
    MissingRequiredFieldError,
    PageOutOfRangeError,
    PdfFillerError,
    TemplateMismatchError,
    TextOverflowError,
)
from pdf_filler.filler import PdfFiller, _checkbox_should_check
from pdf_filler.models import CoordinateMap, TemplateMetadata
from pdf_filler.utils import sha256_file

# --------------------------------------------------------------------------- #
# Successful fill                                                              #
# --------------------------------------------------------------------------- #


def test_fill_writes_output_pdf(
    synthetic_template: Path,
    coord_map_obj: CoordinateMap,
    small_input_data: dict[str, Any],
    tmp_path: Path,
) -> None:
    output = tmp_path / "filled.pdf"
    filler = PdfFiller(synthetic_template, coord_map_obj)
    result = filler.fill(small_input_data, output)

    assert output.exists()
    assert output.stat().st_size > 0
    assert result.page_count == 4
    assert "surname" in result.fields_written
    # Ensure stamped text is present in the output PDF.
    with fitz.open(output) as doc:
        page1_text = doc[0].get_text()
        assert "DOE" in page1_text


def test_fill_does_not_modify_template(
    synthetic_template: Path,
    coord_map_obj: CoordinateMap,
    small_input_data: dict[str, Any],
    tmp_path: Path,
) -> None:
    before = sha256_file(synthetic_template)
    output = tmp_path / "filled.pdf"
    PdfFiller(synthetic_template, coord_map_obj).fill(small_input_data, output)
    after = sha256_file(synthetic_template)
    assert before == after


# --------------------------------------------------------------------------- #
# Required / optional handling                                                 #
# --------------------------------------------------------------------------- #


def test_required_field_missing_raises(
    synthetic_template: Path,
    coord_map_obj: CoordinateMap,
    small_input_data: dict[str, Any],
    tmp_path: Path,
) -> None:
    bad = {k: v for k, v in small_input_data.items() if k != "surname"}

    with pytest.raises(MissingRequiredFieldError) as exc_info:
        PdfFiller(synthetic_template, coord_map_obj).fill(bad, tmp_path / "out.pdf")
    assert exc_info.value.field_name == "surname"
    assert exc_info.value.source_path == "surname"


def test_optional_missing_field_is_skipped(
    synthetic_template: Path,
    coord_map_obj: CoordinateMap,
    small_input_data: dict[str, Any],
    tmp_path: Path,
) -> None:
    # middle_name is optional and not provided
    out = tmp_path / "out.pdf"
    result = PdfFiller(synthetic_template, coord_map_obj).fill(small_input_data, out)
    assert "middle_name" in result.fields_skipped
    assert any("middle_name" in w for w in result.warnings)


# --------------------------------------------------------------------------- #
# Checkbox logic                                                               #
# --------------------------------------------------------------------------- #


def test_checkbox_checked_when_string_match() -> None:
    assert _checkbox_should_check("male", "male") is True
    assert _checkbox_should_check("male", "MALE") is True  # case-insensitive
    assert _checkbox_should_check("male", "female") is False


def test_checkbox_boolean_mode_truthy() -> None:
    assert _checkbox_should_check(None, True) is True
    assert _checkbox_should_check(None, False) is False
    assert _checkbox_should_check(None, 1) is True
    assert _checkbox_should_check(None, 0) is False


def test_checkbox_boolean_mode_with_explicit_bool_checked_when() -> None:
    assert _checkbox_should_check(True, True) is True
    assert _checkbox_should_check(True, False) is False
    assert _checkbox_should_check(False, False) is True


def test_checkbox_unchecked_for_empty_value(
    synthetic_template: Path,
    coord_map_obj: CoordinateMap,
    small_input_data: dict[str, Any],
    tmp_path: Path,
) -> None:
    data = {**small_input_data, "sex": ""}  # empty string → unchecked, not an error
    out = tmp_path / "out.pdf"
    result = PdfFiller(synthetic_template, coord_map_obj).fill(data, out)
    assert "sex_male" in result.fields_skipped


# --------------------------------------------------------------------------- #
# Page-range / template-mismatch errors                                        #
# --------------------------------------------------------------------------- #


def test_page_out_of_range_error(
    synthetic_template: Path,
    small_coordinate_map: dict[str, Any],
    small_input_data: dict[str, Any],
    tmp_path: Path,
) -> None:
    bad_map = dict(small_coordinate_map)
    bad_map["fields"] = dict(bad_map["fields"])
    bad_map["fields"]["surname"] = {**bad_map["fields"]["surname"], "page": 99}
    coord_map = CoordinateMap.model_validate(bad_map)

    with pytest.raises(PageOutOfRangeError):
        PdfFiller(synthetic_template, coord_map).fill(small_input_data, tmp_path / "x.pdf")


def test_metadata_page_count_check_runs(
    synthetic_template: Path,
    coord_map_obj: CoordinateMap,
    small_input_data: dict[str, Any],
    tmp_path: Path,
) -> None:
    # synthetic template has 4 pages; metadata says 7 → mismatch
    meta = TemplateMetadata(template_id="x", template_version="1", expected_pages=7)
    filler = PdfFiller(synthetic_template, coord_map_obj, metadata=meta)
    with pytest.raises(TemplateMismatchError, match="page count"):
        filler.fill(small_input_data, tmp_path / "x.pdf")


def test_template_hash_mismatch_raises(
    synthetic_template: Path,
    coord_map_obj: CoordinateMap,
    small_input_data: dict[str, Any],
    tmp_path: Path,
) -> None:
    meta = TemplateMetadata(
        template_id="x",
        template_version="1",
        expected_pages=4,
        sha256="0" * 64,
    )
    with pytest.raises(TemplateMismatchError, match="SHA-256"):
        PdfFiller(synthetic_template, coord_map_obj, metadata=meta).fill(
            small_input_data, tmp_path / "x.pdf"
        )


def test_template_hash_mismatch_can_be_ignored(
    synthetic_template: Path,
    coord_map_obj: CoordinateMap,
    small_input_data: dict[str, Any],
    tmp_path: Path,
) -> None:
    meta = TemplateMetadata(
        template_id="x",
        template_version="1",
        expected_pages=4,
        sha256="0" * 64,
    )
    out = tmp_path / "x.pdf"
    result = PdfFiller(synthetic_template, coord_map_obj, metadata=meta).fill(
        small_input_data, out, ignore_template_hash=True
    )
    assert out.exists()
    assert result.template_sha256 is not None  # actual hash returned


# --------------------------------------------------------------------------- #
# Overflow                                                                     #
# --------------------------------------------------------------------------- #


def test_overflow_error_raises_when_text_too_wide(
    synthetic_template: Path,
    small_coordinate_map: dict[str, Any],
    small_input_data: dict[str, Any],
    tmp_path: Path,
) -> None:
    bad = dict(small_coordinate_map)
    bad["fields"] = dict(bad["fields"])
    # Force overflow: tiny width with large fixed font_size and overflow=error.
    bad["fields"]["surname"] = {
        **bad["fields"]["surname"],
        "width": 5,
        "min_font_size": 10,
        "overflow": "error",
        "font_size": 10,
    }
    coord_map = CoordinateMap.model_validate(bad)

    with pytest.raises(TextOverflowError):
        PdfFiller(synthetic_template, coord_map).fill(
            small_input_data, tmp_path / "out.pdf"
        )


# --------------------------------------------------------------------------- #
# Output file existence                                                        #
# --------------------------------------------------------------------------- #


def test_existing_output_requires_overwrite(
    synthetic_template: Path,
    coord_map_obj: CoordinateMap,
    small_input_data: dict[str, Any],
    tmp_path: Path,
) -> None:
    out = tmp_path / "out.pdf"
    out.write_bytes(b"placeholder")
    filler = PdfFiller(synthetic_template, coord_map_obj)
    with pytest.raises(PdfFillerError, match="already exists"):
        filler.fill(small_input_data, out)
    # Same call with overwrite succeeds.
    filler.fill(small_input_data, out, overwrite=True)
    assert out.read_bytes()[:4] == b"%PDF"


def test_creates_missing_output_directory(
    synthetic_template: Path,
    coord_map_obj: CoordinateMap,
    small_input_data: dict[str, Any],
    tmp_path: Path,
) -> None:
    nested = tmp_path / "deeply" / "nested" / "path" / "out.pdf"
    PdfFiller(synthetic_template, coord_map_obj).fill(small_input_data, nested)
    assert nested.exists()


# --------------------------------------------------------------------------- #
# Debug boxes                                                                  #
# --------------------------------------------------------------------------- #


def test_debug_boxes_does_not_break_output(
    synthetic_template: Path,
    coord_map_obj: CoordinateMap,
    small_input_data: dict[str, Any],
    tmp_path: Path,
) -> None:
    out = tmp_path / "debug.pdf"
    PdfFiller(synthetic_template, coord_map_obj).fill(
        small_input_data, out, debug_boxes=True
    )
    assert out.exists()
    with fitz.open(out) as doc:
        assert "DOE" in doc[0].get_text()
