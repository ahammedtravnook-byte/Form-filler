"""Admin routes: upload, update, delete templates and fields configs.

All routes require the admin API key via Bearer token.

Upload rules
------------
* POST /admin/templates/{template_id}
    — Requires: fields_config (JSON file)
    — Optional: template_pdf (PDF file), template_metadata (JSON file)
    — Creates a new template directory. Fails with 409 if already exists.

* PUT /admin/templates/{template_id}
    — Same fields as POST, but replaces an existing template.
    — Requires: fields_config (JSON file)
    — Optional: template_pdf (PDF file), template_metadata (JSON file)

* PATCH /admin/templates/{template_id}/fields-config
    — Replace only the fields_config.json of an existing template.

* DELETE /admin/templates/{template_id}
    — Removes the entire template directory.

* GET /admin/templates/{template_id}/fields-config
    — Returns the raw fields_config.json content (useful for inspection).
"""

from __future__ import annotations

import json
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile

from api.core.config import settings
from api.core.logging import get_logger
from api.dependencies.auth import require_admin
from api.dependencies.templates import get_templates_root
from api.schemas.template import FieldsConfigResponse
from api.schemas.validation import AdminTemplateDeleteResponse, AdminTemplateUploadResponse
from api.services import storage_service as store
from pdf_filler.coordinates import load_fields_config

_log = get_logger("api.admin_templates")

router = APIRouter(
    prefix="/admin/templates",
    tags=["Admin — Templates"],
    dependencies=[Depends(require_admin)],
)


# --------------------------------------------------------------------------- #
# Helpers                                                                      #
# --------------------------------------------------------------------------- #


def _read_and_validate_fields_config(upload: UploadFile) -> bytes:
    """Read the fields config upload, enforce size limit, validate JSON + schema."""
    raw = upload.file.read()
    if len(raw) > settings.max_upload_bytes:
        raise HTTPException(413, "fields_config file too large.")
    try:
        json.loads(raw)
    except json.JSONDecodeError as exc:
        raise HTTPException(422, f"fields_config is not valid JSON: {exc}") from exc

    # Validate against FieldsConfig schema — raises CoordinateMapError → 422 via middleware
    import tempfile
    from pathlib import Path as _P

    with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as tmp:
        tmp.write(raw)
        tmp_path = _P(tmp.name)
    try:
        load_fields_config(tmp_path)
    finally:
        tmp_path.unlink(missing_ok=True)

    return raw


def _read_pdf(upload: UploadFile) -> bytes:
    if not (upload.filename or "").lower().endswith(".pdf"):
        raise HTTPException(422, "template_pdf must be a .pdf file.")
    raw = upload.file.read()
    if len(raw) > settings.max_upload_bytes:
        raise HTTPException(413, "template_pdf too large.")
    if len(raw) == 0:
        raise HTTPException(422, "template_pdf is empty.")
    return raw


def _read_meta(upload: UploadFile) -> bytes:
    raw = upload.file.read()
    try:
        json.loads(raw)
    except json.JSONDecodeError as exc:
        raise HTTPException(422, f"template_metadata is not valid JSON: {exc}") from exc
    return raw


# --------------------------------------------------------------------------- #
# Routes                                                                       #
# --------------------------------------------------------------------------- #


@router.post(
    "/{template_id}",
    response_model=AdminTemplateUploadResponse,
    status_code=201,
    summary="Upload a new template (PDF + fields config)",
)
async def create_template(
    template_id: str,
    fields_config: UploadFile = File(..., description="fields_config.json"),
    template_pdf: UploadFile | None = File(None, description="template.pdf (optional now, required before filling)"),
    template_metadata: UploadFile | None = File(None, description="template_metadata.json (optional)"),
    templates_root: Path = Depends(get_templates_root),
) -> AdminTemplateUploadResponse:
    if store.template_exists(templates_root, template_id):
        raise HTTPException(409, f"Template '{template_id}' already exists. Use PUT to update.")

    map_bytes = _read_and_validate_fields_config(fields_config)
    pdf_bytes = _read_pdf(template_pdf) if template_pdf else None
    meta_bytes = _read_meta(template_metadata) if template_metadata else None

    saved = store.save_template_files(
        templates_root,
        template_id,
        pdf_bytes=pdf_bytes,
        map_bytes=map_bytes,
        meta_bytes=meta_bytes,
    )
    return AdminTemplateUploadResponse(
        template_id=template_id,
        message="Template created.",
        files_saved=saved,
    )


@router.put(
    "/{template_id}",
    response_model=AdminTemplateUploadResponse,
    summary="Replace an existing template (PDF + fields config)",
)
async def update_template(
    template_id: str,
    fields_config: UploadFile = File(..., description="fields_config.json"),
    template_pdf: UploadFile | None = File(None, description="template.pdf"),
    template_metadata: UploadFile | None = File(None, description="template_metadata.json"),
    templates_root: Path = Depends(get_templates_root),
) -> AdminTemplateUploadResponse:
    store.require_template(templates_root, template_id)

    map_bytes = _read_and_validate_fields_config(fields_config)
    pdf_bytes = _read_pdf(template_pdf) if template_pdf else None
    meta_bytes = _read_meta(template_metadata) if template_metadata else None

    saved = store.save_template_files(
        templates_root,
        template_id,
        pdf_bytes=pdf_bytes,
        map_bytes=map_bytes,
        meta_bytes=meta_bytes,
    )
    return AdminTemplateUploadResponse(
        template_id=template_id,
        message="Template updated.",
        files_saved=saved,
    )


@router.patch(
    "/{template_id}/fields-config",
    response_model=AdminTemplateUploadResponse,
    summary="Replace only the fields config of an existing template",
)
async def update_fields_config(
    template_id: str,
    fields_config: UploadFile = File(..., description="New fields_config.json"),
    templates_root: Path = Depends(get_templates_root),
) -> AdminTemplateUploadResponse:
    store.require_template(templates_root, template_id)

    map_bytes = _read_and_validate_fields_config(fields_config)

    saved = store.save_template_files(
        templates_root,
        template_id,
        pdf_bytes=None,
        map_bytes=map_bytes,
        meta_bytes=None,
    )
    return AdminTemplateUploadResponse(
        template_id=template_id,
        message="Fields config updated.",
        files_saved=saved,
    )


@router.get(
    "/{template_id}/fields-config",
    response_model=FieldsConfigResponse,
    summary="Inspect the fields config of a template",
)
def get_fields_config(
    template_id: str,
    templates_root: Path = Depends(get_templates_root),
) -> FieldsConfigResponse:
    store.require_template(templates_root, template_id)
    raw = store.load_raw_map(templates_root, template_id)
    return FieldsConfigResponse(template_id=template_id, fields_config=raw)


@router.delete(
    "/{template_id}",
    response_model=AdminTemplateDeleteResponse,
    summary="Delete a template and all its files",
)
def delete_template(
    template_id: str,
    templates_root: Path = Depends(get_templates_root),
) -> AdminTemplateDeleteResponse:
    store.delete_template(templates_root, template_id)
    return AdminTemplateDeleteResponse(
        template_id=template_id,
        message="Template deleted.",
    )
