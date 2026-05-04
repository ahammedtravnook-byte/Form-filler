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
    CoordinateMap,
    DateFieldConfig,
    FieldConfig,
    FillRequest,
    MultilineTextFieldConfig,
    TemplateMetadata,
    TextFieldConfig,
)

__all__ = [
    "CheckboxFieldConfig",
    "CoordinateMap",
    "CoordinateMapError",
    "DataValidationError",
    "DateFieldConfig",
    "FieldConfig",
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

__version__ = "0.1.0"
