"""Maps pdf_filler domain exceptions to HTTP responses."""

from __future__ import annotations

from fastapi import HTTPException

from pdf_filler.exceptions import (
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


def domain_exc_to_http(exc: PdfFillerError) -> HTTPException:
    """Convert a PdfFillerError to the appropriate HTTPException."""
    detail = str(exc)

    if isinstance(exc, TemplateNotFoundError):
        return HTTPException(status_code=404, detail=detail)

    if isinstance(exc, (DataValidationError, MissingRequiredFieldError)):
        return HTTPException(status_code=422, detail=detail)

    if isinstance(exc, CoordinateMapError):
        return HTTPException(status_code=422, detail=detail)

    if isinstance(exc, (TemplateMismatchError, PageOutOfRangeError)):
        return HTTPException(status_code=409, detail=detail)

    if isinstance(exc, TextOverflowError):
        return HTTPException(status_code=422, detail=detail)

    if isinstance(exc, UnsupportedFieldTypeError):
        return HTTPException(status_code=501, detail=detail)

    # Catch-all for base PdfFillerError
    return HTTPException(status_code=500, detail=detail)
