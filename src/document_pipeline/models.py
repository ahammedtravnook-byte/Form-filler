"""Pydantic models for intermediate extraction results."""

from __future__ import annotations

from pydantic import BaseModel, Field


class PassportData(BaseModel):
    surname: str
    given_names: str
    document_number: str
    nationality: str
    date_of_birth: str  # ISO 8601: YYYY-MM-DD
    expiry_date: str  # ISO 8601: YYYY-MM-DD
    issuing_country: str
    sex: str
    document_type: str = "P"


class EmiratesIdData(BaseModel):
    full_name_en: str
    full_name_ar: str | None = None
    id_number: str  # 784-YYYY-XXXXXXX-X
    nationality: str
    date_of_birth: str | None = None  # ISO 8601: YYYY-MM-DD
    issue_date: str | None = None     # ISO 8601: YYYY-MM-DD
    expiry_date: str                  # ISO 8601: YYYY-MM-DD
    gender: str


class QAData(BaseModel):
    # Maps the original question text (as written in the document) to its answer.
    raw_answers: dict[str, str] = Field(default_factory=dict)


class ValidationWarning(BaseModel):
    field: str
    message: str
    source_a: str
    source_b: str


class ExtractionResult(BaseModel):
    passport: PassportData | None = None
    emirates_id: EmiratesIdData | None = None
    qa: QAData | None = None
    extraction_errors: list[str] = Field(default_factory=list)
