"""Schemas for template metadata responses."""

from __future__ import annotations

from pydantic import BaseModel


class TemplateMetadataResponse(BaseModel):
    template_id: str
    template_version: str
    description: str
    expected_pages: int
    has_coordinate_map: bool
    has_pdf: bool


class TemplateListResponse(BaseModel):
    templates: list[TemplateMetadataResponse]
    total: int


class CoordinateMapResponse(BaseModel):
    """Admin-only: raw coordinate map content."""
    template_id: str
    coordinate_map: dict  # type: ignore[type-arg]
