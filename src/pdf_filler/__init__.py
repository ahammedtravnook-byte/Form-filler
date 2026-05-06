"""pdf_filler: coordinate-based static PDF template filler.

This package treats the PDF as a fixed visual template and stamps text and
checkbox marks at configured coordinates. It does *not* rely on AcroForm or
XFA form fields.
"""

from __future__ import annotations

from .exceptions import (
    CoordinateMapError,
    DataValidationError,
    MissingRequiredFieldError,
    PageOutOfRangeError,
    PdfFillerError,
    TemplateMismatchError,
    TemplateNotFoundError,
    TextOverflowError,
    UnsupportedFieldTypeError,
)
from .filler import FillResult, PdfFiller
from .models import (
    CheckboxFieldConfig,
    CheckboxGroupFieldConfig,
    CoordinateMap,
    DateFieldConfig,
    FieldConfig,
    FieldsConfig,
    FillRequest,
    MultilineTextFieldConfig,
    TemplateMetadata,
    TextFieldConfig,
)

__all__ = [
    "CheckboxFieldConfig",
    "CheckboxGroupFieldConfig",
    "CoordinateMap",
    "CoordinateMapError",
    "DataValidationError",
    "DateFieldConfig",
    "FieldConfig",
    "FieldsConfig",
    "FillRequest",
    "FillResult",
    "MissingRequiredFieldError",
    "MultilineTextFieldConfig",
    "PageOutOfRangeError",
    "PdfFiller",
    "PdfFillerError",
    "TemplateMetadata",
    "TemplateMismatchError",
    "TemplateNotFoundError",
    "TextFieldConfig",
    "TextOverflowError",
    "UnsupportedFieldTypeError",
]

__version__ = "0.2.0"
