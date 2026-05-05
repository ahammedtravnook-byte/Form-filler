"""Reads template assets from disk and returns API-level response objects."""

from __future__ import annotations

from pathlib import Path

from api.schemas.template import TemplateListResponse, TemplateMetadataResponse
from api.services import storage_service as store


def get_template_metadata_response(
    templates_root: Path,
    template_id: str,
) -> TemplateMetadataResponse:
    store.require_template(templates_root, template_id)

    has_pdf = store.pdf_path(templates_root, template_id).exists()
    has_map = store.map_path(templates_root, template_id).exists()
    meta = store.load_metadata_safe(templates_root, template_id)

    from pdf_filler.models import TemplateMetadata  # local import to avoid circular

    if isinstance(meta, TemplateMetadata):
        return TemplateMetadataResponse(
            template_id=meta.template_id,
            template_version=meta.template_version,
            description=meta.description,
            expected_pages=meta.expected_pages,
            has_coordinate_map=has_map,
            has_pdf=has_pdf,
        )

    # Metadata file absent — return bare-bones info derived from folder name.
    return TemplateMetadataResponse(
        template_id=template_id,
        template_version="unknown",
        description="",
        expected_pages=0,
        has_coordinate_map=has_map,
        has_pdf=has_pdf,
    )


def list_templates(templates_root: Path) -> TemplateListResponse:
    ids = store.list_template_ids(templates_root)
    items = [get_template_metadata_response(templates_root, tid) for tid in ids]
    return TemplateListResponse(templates=items, total=len(items))
