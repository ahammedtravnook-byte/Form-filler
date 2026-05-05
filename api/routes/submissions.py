"""Fill and validate routes (public — no admin key required)."""

from __future__ import annotations

import json
from pathlib import Path

from fastapi import APIRouter, Depends, File, UploadFile
from fastapi.responses import Response

from api.core.config import settings
from api.core.exceptions import domain_exc_to_http
from api.core.logging import get_logger
from api.dependencies.templates import get_templates_root
from api.schemas.submission import (
    BatchFillRequest,
    FillRequest,
    ValidationRequest,
    ValidationResponse,
)
from api.services import pdf_fill_service, storage_service as store, validation_service
from api.services.excel_service import parse_excel
from pdf_filler.coordinates import load_fields_config
from pdf_filler.exceptions import PdfFillerError

_log = get_logger("api.submissions")

router = APIRouter(prefix="/templates", tags=["Submissions"])

_ZIP_MEDIA = "application/zip"
_PDF_MEDIA = "application/pdf"


# --------------------------------------------------------------------------- #
# Validate                                                                     #
# --------------------------------------------------------------------------- #


@router.post(
    "/{template_id}/validate",
    response_model=ValidationResponse,
    summary="Validate input data against template (dry run, no PDF produced)",
)
def validate_submission(
    template_id: str,
    body: ValidationRequest,
    templates_root: Path = Depends(get_templates_root),
) -> ValidationResponse:
    store.require_template(templates_root, template_id)
    map_path = store.require_map(templates_root, template_id)
    fields_cfg = load_fields_config(map_path)
    return validation_service.validate_data_against_map(template_id, body.data, fields_cfg)


# --------------------------------------------------------------------------- #
# Single fill                                                                  #
# --------------------------------------------------------------------------- #


@router.post(
    "/{template_id}/fill",
    response_class=Response,
    responses={
        200: {
            "content": {_PDF_MEDIA: {}},
            "description": "Filled PDF file.",
            "headers": {
                "X-Fields-Written": {"description": "Number of fields stamped."},
                "X-Fields-Skipped": {"description": "Number of optional fields skipped."},
                "X-Warnings": {"description": "Number of non-fatal warnings."},
            },
        },
        404: {"description": "Template not found."},
        422: {"description": "Validation error in input data."},
    },
    summary="Fill a PDF template with a single record",
)
async def fill_template(
    template_id: str,
    body: FillRequest,
    templates_root: Path = Depends(get_templates_root),
) -> Response:
    store.require_template(templates_root, template_id)
    try:
        pdf_bytes, result = await pdf_fill_service.fill_template(
            templates_root, template_id, body.data
        )
    except PdfFillerError as exc:
        raise domain_exc_to_http(exc) from exc

    filename = f"{template_id}_filled.pdf"
    return Response(
        content=pdf_bytes,
        media_type=_PDF_MEDIA,
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "X-Fields-Written": str(len(result.fields_written)),
            "X-Fields-Skipped": str(len(result.fields_skipped)),
            "X-Warnings": str(len(result.warnings)),
        },
    )


# --------------------------------------------------------------------------- #
# Batch fill — JSON                                                            #
# --------------------------------------------------------------------------- #


@router.post(
    "/{template_id}/fill/batch",
    response_class=Response,
    responses={
        200: {
            "content": {_ZIP_MEDIA: {}},
            "description": "ZIP archive containing one PDF per input record.",
            "headers": {
                "X-Batch-Total": {"description": "Total records submitted."},
                "X-Batch-Succeeded": {"description": "Records successfully filled."},
                "X-Batch-Failed": {"description": "Records that failed (see X-Batch-Errors)."},
                "X-Batch-Errors": {"description": "JSON array of {index, filename, error} for failed records."},
            },
        },
        404: {"description": "Template not found."},
        422: {"description": "records list is empty or malformed."},
    },
    summary="Fill a template with multiple records — returns a ZIP of PDFs",
)
async def fill_template_batch(
    template_id: str,
    body: BatchFillRequest,
    templates_root: Path = Depends(get_templates_root),
) -> Response:
    store.require_template(templates_root, template_id)

    batch = await pdf_fill_service.fill_template_batch(
        templates_root, template_id, body.records
    )

    filename = f"{template_id}_batch.zip"
    return Response(
        content=batch.zip_bytes,
        media_type=_ZIP_MEDIA,
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "X-Batch-Total": str(batch.total),
            "X-Batch-Succeeded": str(batch.succeeded),
            "X-Batch-Failed": str(batch.failed),
            "X-Batch-Errors": json.dumps(batch.errors),
        },
    )


# --------------------------------------------------------------------------- #
# Batch fill — Excel                                                           #
# --------------------------------------------------------------------------- #


@router.post(
    "/{template_id}/fill/excel",
    response_class=Response,
    responses={
        200: {
            "content": {_ZIP_MEDIA: {}},
            "description": (
                "ZIP archive containing one PDF per row in the uploaded Excel file. "
                "Column headers must match the data_key values from the fields config "
                "(e.g. surname, first_name, passport_number)."
            ),
            "headers": {
                "X-Batch-Total": {"description": "Total rows parsed from Excel."},
                "X-Batch-Succeeded": {"description": "Records successfully filled."},
                "X-Batch-Failed": {"description": "Records that failed."},
                "X-Batch-Errors": {"description": "JSON array of {index, filename, error}."},
            },
        },
        404: {"description": "Template not found."},
        422: {"description": "Excel file could not be parsed or has no data rows."},
    },
    summary="Fill a template from an Excel file — one row per PDF, returned as a ZIP",
)
async def fill_template_excel(
    template_id: str,
    file: UploadFile = File(..., description="Excel file (.xlsx). One row = one filled PDF. Column headers = data_key values from fields_config.json."),
    templates_root: Path = Depends(get_templates_root),
) -> Response:
    store.require_template(templates_root, template_id)

    if not (file.filename or "").lower().endswith((".xlsx", ".xls")):
        from fastapi import HTTPException
        raise HTTPException(422, "Only .xlsx / .xls files are accepted.")

    raw = await file.read()
    if len(raw) > settings.max_upload_bytes:
        from fastapi import HTTPException
        raise HTTPException(413, "Excel file too large.")

    records = parse_excel(raw)
    _log.info("Excel upload: %d rows parsed for template '%s'.", len(records), template_id)

    batch = await pdf_fill_service.fill_template_batch(
        templates_root, template_id, records
    )

    filename = f"{template_id}_excel_batch.zip"
    return Response(
        content=batch.zip_bytes,
        media_type=_ZIP_MEDIA,
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "X-Batch-Total": str(batch.total),
            "X-Batch-Succeeded": str(batch.succeeded),
            "X-Batch-Failed": str(batch.failed),
            "X-Batch-Errors": json.dumps(batch.errors),
        },
    )
