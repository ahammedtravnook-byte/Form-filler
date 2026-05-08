"""Request/response schemas for the document extraction pipeline routes."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class ValidationWarningSchema(BaseModel):
    field: str
    message: str
    source_a: str
    source_b: str


class ProcessDocumentsResponse(BaseModel):
    session_id: str
    # extracted_data: dict[str, Any]
    # validation_warnings: list[ValidationWarningSchema]
    client_json: dict[str, Any] = Field(
        default_factory=dict,
        description="AI-mapped fields: keys from fields_config, values from extracted data.",
    )


class VerifyRequest(BaseModel):
    session_id: str = Field(..., description="Session ID returned by /process")
    verified_data: dict[str, Any] = Field(
        ..., description="User-reviewed and corrected extraction result"
    )


class VerifyResponse(BaseModel):
    session_id: str
    verified_data: dict[str, Any]
