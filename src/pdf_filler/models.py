"""Pydantic v2 models for the fields config, template metadata, and fill request.

The field configs are a discriminated union on the ``type`` field. The new
``fields_config.json`` schema is intentionally compact:

* Each field has a top-level ``data_key`` (the key in the flat input data).
* Plain text fields omit ``type`` (defaulted to ``"text"``).
* Checkbox groups carry ``type: "checkbox_group"`` and an ``options`` map
  whose keys are the values that should toggle each option's box.
"""

from __future__ import annotations

from pathlib import Path
from typing import Annotated, Any, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    PositiveFloat,
    PositiveInt,
    field_validator,
    model_validator,
)

# --------------------------------------------------------------------------- #
# Shared types                                                                 #
# --------------------------------------------------------------------------- #

Alignment = Literal["left", "center", "right"]
OverflowStrategy = Literal["error", "shrink", "truncate"]
CheckStyle = Literal["check", "x", "filled_square"]


class _BaseField(BaseModel):
    """Common fields shared by every concrete field type."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    data_key: str = Field(
        ...,
        description="Key in the flat input data dict (e.g. 'surname').",
        min_length=1,
    )
    page: PositiveInt = Field(
        ...,
        description="1-based page number (PyMuPDF uses 0-based internally).",
    )
    required: bool = Field(default=False)
    description: str = ""


class _PlacedField(_BaseField):
    """A field with a single (x, y) placement plus optional bounding box."""

    x: float = Field(..., description="X coordinate in points (origin top-left).")
    y: float = Field(..., description="Y coordinate in points (origin top-left).")


# --------------------------------------------------------------------------- #
# Concrete field configs                                                       #
# --------------------------------------------------------------------------- #


class TextFieldConfig(_PlacedField):
    """A single-line text field stamped onto the page."""

    type: Literal["text"] = "text"
    font_size: PositiveFloat = 9.0
    font: str = "helv"
    align: Alignment = "left"
    width: PositiveFloat | None = None
    height: PositiveFloat | None = None
    max_chars: PositiveInt | None = None
    overflow: OverflowStrategy = "shrink"
    min_font_size: PositiveFloat = 6.0
    color: tuple[float, float, float] = (0.0, 0.0, 0.0)

    @model_validator(mode="after")
    def _check_min_font_size(self) -> TextFieldConfig:
        if self.min_font_size > self.font_size:
            raise ValueError(
                f"min_font_size ({self.min_font_size}) cannot exceed font_size ({self.font_size})."
            )
        return self


class MultilineTextFieldConfig(_PlacedField):
    """A multi-line text field rendered into a bounding rectangle."""

    type: Literal["multiline_text"] = "multiline_text"
    font_size: PositiveFloat = 9.0
    font: str = "helv"
    align: Alignment = "left"
    width: PositiveFloat = Field(..., description="Required for multiline text.")
    height: PositiveFloat | None = None
    line_height: PositiveFloat = 11.0
    max_lines: PositiveInt = Field(default=5)
    overflow: OverflowStrategy = "shrink"
    color: tuple[float, float, float] = (0.0, 0.0, 0.0)


class DateFieldConfig(_PlacedField):
    """A date field, formatted via :py:meth:`datetime.date.strftime`."""

    type: Literal["date"] = "date"
    font_size: PositiveFloat = 9.0
    font: str = "helv"
    align: Alignment = "left"
    format: str = "%d-%m-%Y"
    width: PositiveFloat | None = None
    overflow: OverflowStrategy = "shrink"
    color: tuple[float, float, float] = (0.0, 0.0, 0.0)


class CheckboxFieldConfig(_PlacedField):
    """A standalone boolean checkbox stamped over a printed empty box."""

    type: Literal["checkbox"] = "checkbox"
    box_size: PositiveFloat = 8.0
    checked_when: str | int | float | bool | None = None
    check_style: CheckStyle = "x"
    line_width: PositiveFloat = 1.2
    color: tuple[float, float, float] = (0.0, 0.0, 0.0)


class CheckboxOption(BaseModel):
    """A single (x, y) anchor for one option in a checkbox group."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    x: float
    y: float


class CheckboxGroupFieldConfig(_BaseField):
    """A group of mutually-exclusive (or selectable) checkboxes.

    The input value is matched (case-insensitively) against the keys of
    ``options``; the matching option's box is checked. Multiple values can be
    supplied as a list to check several options.
    """

    type: Literal["checkbox_group"] = "checkbox_group"
    options: dict[str, CheckboxOption] = Field(..., min_length=1)
    box_size: PositiveFloat = 8.0
    check_style: CheckStyle = "x"
    line_width: PositiveFloat = 1.2
    color: tuple[float, float, float] = (0.0, 0.0, 0.0)


class ImageFieldConfig(_PlacedField):
    """Placeholder for future image support (e.g. a photograph)."""

    type: Literal["image"] = "image"
    width: PositiveFloat
    height: PositiveFloat
    keep_aspect: bool = True


class SignatureTextFieldConfig(_PlacedField):
    """A signature rendered as text in a script-like font."""

    type: Literal["signature_text"] = "signature_text"
    font_size: PositiveFloat = 14.0
    font: str = "helv"
    align: Alignment = "left"
    width: PositiveFloat | None = None
    overflow: OverflowStrategy = "shrink"
    min_font_size: PositiveFloat = 8.0
    color: tuple[float, float, float] = (0.0, 0.0, 0.0)


# Discriminated union: pydantic picks the right model based on the ``type`` tag.
FieldConfig = Annotated[
    TextFieldConfig
    | MultilineTextFieldConfig
    | CheckboxFieldConfig
    | CheckboxGroupFieldConfig
    | DateFieldConfig
    | ImageFieldConfig
    | SignatureTextFieldConfig,
    Field(discriminator="type"),
]


# --------------------------------------------------------------------------- #
# Page geometry & top-level fields config                                      #
# --------------------------------------------------------------------------- #


class PageGeometry(BaseModel):
    """Per-page width/height declared in the fields config (informational)."""

    model_config = ConfigDict(extra="forbid")

    page_number: PositiveInt
    pdf_width: PositiveFloat
    pdf_height: PositiveFloat


class FieldsConfig(BaseModel):
    """Top-level fields-config document (the new compact schema)."""

    model_config = ConfigDict(extra="forbid")

    form_name: str = Field(..., min_length=1)
    pages: list[PageGeometry] = Field(default_factory=list)
    fields: dict[str, FieldConfig]  # type: ignore[valid-type]

    @field_validator("fields", mode="before")
    @classmethod
    def _default_field_type(cls, value: Any) -> Any:
        """Inject ``type: "text"`` into field dicts that omit ``type``."""
        if not isinstance(value, dict):
            return value
        out: dict[str, Any] = {}
        for name, cfg in value.items():
            if isinstance(cfg, dict) and "type" not in cfg:
                out[name] = {**cfg, "type": "text"}
            else:
                out[name] = cfg
        return out

    @field_validator("fields")
    @classmethod
    def _check_fields_non_empty(cls, value: dict[str, Any]) -> dict[str, Any]:
        if not value:
            raise ValueError("Fields config must define at least one field.")
        return value

    def field_names(self) -> list[str]:
        """Return field names in declaration order."""
        return list(self.fields.keys())


# Back-compat alias — the rest of the package historically referred to this
# document as the "coordinate map". Keep the name to minimise churn.
CoordinateMap = FieldsConfig


# --------------------------------------------------------------------------- #
# Template metadata                                                            #
# --------------------------------------------------------------------------- #


class TemplateMetadata(BaseModel):
    """Companion metadata file describing the template PDF."""

    model_config = ConfigDict(extra="forbid")

    template_id: str = Field(..., min_length=1)
    template_version: str = Field(..., min_length=1)
    expected_pages: PositiveInt
    sha256: str = ""
    description: str = ""

    @field_validator("sha256")
    @classmethod
    def _check_sha(cls, value: str) -> str:
        v = value.strip().lower()
        if v == "":
            return v
        if len(v) != 64 or any(c not in "0123456789abcdef" for c in v):
            raise ValueError("sha256 must be a 64-character hex string or empty.")
        return v


# --------------------------------------------------------------------------- #
# Fill request (used by CLI / programmatic API)                                #
# --------------------------------------------------------------------------- #


class FillRequest(BaseModel):
    """Bundle of inputs required to perform a fill operation."""

    model_config = ConfigDict(extra="forbid", arbitrary_types_allowed=True)

    template_path: Path
    data: dict[str, Any]
    fields_config: FieldsConfig
    metadata: TemplateMetadata | None = None
    output_path: Path
    debug_boxes: bool = False
    ignore_template_hash: bool = False
    overwrite: bool = False
