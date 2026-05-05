"""Admin upload schemas."""

from __future__ import annotations

from pydantic import BaseModel


class AdminTemplateUploadResponse(BaseModel):
    template_id: str
    message: str
    files_saved: list[str]


class AdminTemplateDeleteResponse(BaseModel):
    template_id: str
    message: str
