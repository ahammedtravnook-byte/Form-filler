"""Custom exception hierarchy for pdf_filler.

All exceptions inherit from :class:`PdfFillerError` so callers can catch the
whole package's failure modes with a single ``except`` clause when that is
appropriate, while still being able to handle specific cases granularly.
"""

from __future__ import annotations


class PdfFillerError(Exception):
    """Base class for all pdf_filler errors."""


class TemplateNotFoundError(PdfFillerError):
    """Raised when the template PDF cannot be found at the given path."""


class DataValidationError(PdfFillerError):
    """Raised when the input data JSON fails Pydantic validation or shape checks."""


class CoordinateMapError(PdfFillerError):
    """Raised when the coordinate map JSON is invalid or self-inconsistent."""


class MissingRequiredFieldError(PdfFillerError):
    """Raised when a required field has no value in the input data."""

    def __init__(self, field_name: str, source_path: str) -> None:
        self.field_name = field_name
        self.source_path = source_path
        super().__init__(
            f"Required field '{field_name}' is missing data at source path '{source_path}'."
        )


class TemplateMismatchError(PdfFillerError):
    """Raised when the template SHA-256 hash does not match the metadata."""


class PageOutOfRangeError(PdfFillerError):
    """Raised when a coordinate field references a page that doesn't exist in the PDF."""

    def __init__(self, field_name: str, page: int, page_count: int) -> None:
        self.field_name = field_name
        self.page = page
        self.page_count = page_count
        super().__init__(
            f"Field '{field_name}' references page {page}, but the template only has "
            f"{page_count} page(s)."
        )


class TextOverflowError(PdfFillerError):
    """Raised when text doesn't fit and the overflow strategy is 'error'."""

    def __init__(self, field_name: str, text_len: int, max_width: float) -> None:
        self.field_name = field_name
        self.text_len = text_len
        self.max_width = max_width
        super().__init__(
            f"Field '{field_name}' overflows: {text_len} characters could not fit "
            f"within max_width={max_width} points."
        )


class UnsupportedFieldTypeError(PdfFillerError):
    """Raised when a coordinate field type is not implemented."""
