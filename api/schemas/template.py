"""Schemas for template metadata responses."""

from __future__ import annotations

from pydantic import BaseModel


class TemplateMetadataResponse(BaseModel):
    template_id: str
    template_version: str
    description: str
    expected_pages: int
    has_fields_config: bool
    has_pdf: bool


class TemplateListResponse(BaseModel):
    templates: list[TemplateMetadataResponse]
    total: int


class FieldsConfigResponse(BaseModel):
    """Admin-only: raw fields config content."""
    template_id: str
    fields_config: dict  # type: ignore[type-arg]


# Back-compat alias
CoordinateMapResponse = FieldsConfigResponse
