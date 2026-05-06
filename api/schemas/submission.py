"""Schemas for fill submissions."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field, model_validator


class FillRequest(BaseModel):
    """Body for POST /templates/{template_id}/fill."""
    data: dict[str, Any]


class BatchFillRequest(BaseModel):
    """Body for POST /templates/{template_id}/fill/batch."""
    records: list[dict[str, Any]] = Field(
        ...,
        min_length=1,
        description="One or more data objects. Each produces one filled PDF in the ZIP.",
    )


class BatchFillErrorDetail(BaseModel):
    index: int
    filename: str
    error: str


class BatchFillResponse(BaseModel):
    """Returned in X-Batch-Summary response header (JSON-encoded)."""
    total: int
    succeeded: int
    failed: int
    errors: list[BatchFillErrorDetail]


class ValidationRequest(BaseModel):
    """Body for POST /templates/{template_id}/validate."""
    data: dict[str, Any]


class ValidationResponse(BaseModel):
    template_id: str
    valid: bool
    fields_present: list[str]
    fields_missing_optional: list[str]
    errors: list[str]
