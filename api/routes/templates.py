"""Public read-only template routes."""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends

from api.dependencies.templates import get_templates_root
from api.schemas.template import TemplateListResponse, TemplateMetadataResponse
from api.services import template_service

router = APIRouter(prefix="/templates", tags=["Templates"])


@router.get(
    "",
    response_model=TemplateListResponse,
    summary="List available templates",
)
def list_templates(
    templates_root: Path = Depends(get_templates_root),
) -> TemplateListResponse:
    return template_service.list_templates(templates_root)


@router.get(
    "/{template_id}",
    response_model=TemplateMetadataResponse,
    summary="Get template metadata",
)
def get_template(
    template_id: str,
    templates_root: Path = Depends(get_templates_root),
) -> TemplateMetadataResponse:
    return template_service.get_template_metadata_response(templates_root, template_id)
