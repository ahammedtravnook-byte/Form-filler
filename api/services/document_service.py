"""Orchestrator for the document extraction pipeline.

Responsibilities:
  1. Read uploaded file bytes
  2. Dispatch to src/document_pipeline/ extraction functions
  3. Store ExtractionResult in a session keyed by session_id

Routes:
  POST /process  — extract from uploaded documents, return raw data for review
  POST /verify   — accept user-edited data, hold it for confirmation
  POST /fill     — AI maps verified data → PDF fields, returns filled PDF (future)

Session store is an in-process dict — intentional for MVP simplicity.
Replace with Redis + TTL before deploying behind multiple workers.
"""

from __future__ import annotations

import uuid
from typing import Any

from api.core.logging import get_logger
from api.schemas.documents import ProcessDocumentsResponse, ValidationWarningSchema
from document_pipeline.cross_validator import cross_validate
from document_pipeline.emirates_id import extract_emirates_id
from document_pipeline.models import ExtractionResult
from document_pipeline.mrz import extract_passport_mrz
from document_pipeline.qa_document import extract_qa_answers

_log = get_logger("api.document_service")

# Maps session_id → ExtractionResult dict (raw, as returned by /process).
# Overwritten by /verify with the user-edited version.
_sessions: dict[str, dict[str, Any]] = {}


async def process_documents(
    emirates_id_bytes: bytes,
    passport_bytes: bytes,
    qa_bytes: bytes,
) -> ProcessDocumentsResponse:
    """Extract fields from the three source documents and return raw model data.

    Extraction errors are non-fatal — partial results plus error list are
    returned so the reviewer can fill in missing fields manually.
    """
    result = ExtractionResult()

    # --- Passport ---
    try:
        result.passport = extract_passport_mrz(passport_bytes)
        _log.info("Passport MRZ extracted: %s %s", result.passport.surname, result.passport.given_names)
    except Exception as exc:
        msg = f"Passport extraction failed: {exc}"
        _log.warning(msg)
        result.extraction_errors.append(msg)

    # --- Emirates ID ---
    try:
        result.emirates_id, eid_errors = extract_emirates_id(emirates_id_bytes)
        if eid_errors:
            result.extraction_errors.extend(eid_errors)
            _log.warning("Emirates ID partial extraction: %s", eid_errors)
        _log.info("Emirates ID extracted: %s", result.emirates_id.id_number)
    except Exception as exc:
        msg = f"Emirates ID extraction failed: {exc}"
        _log.warning(msg)
        result.extraction_errors.append(msg)

    # --- Q&A document ---
    try:
        result.qa = extract_qa_answers(qa_bytes)
        _log.info("Q&A answers extracted: %d pairs", len(result.qa.raw_answers))
    except Exception as exc:
        msg = f"Q&A extraction failed: {exc}"
        _log.warning(msg)
        result.extraction_errors.append(msg)

    # --- Cross-document validation warnings ---
    warnings: list[ValidationWarningSchema] = [
        ValidationWarningSchema(field="extraction", message=err, source_a="pipeline", source_b="")
        for err in result.extraction_errors
    ]
    warnings.extend(
        ValidationWarningSchema(field=w.field, message=w.message, source_a=w.source_a, source_b=w.source_b)
        for w in cross_validate(result)
    )

    # --- Store raw extraction in session ---
    session_id = str(uuid.uuid4())
    _sessions[session_id] = result.model_dump()
    _log.info("Session %s created.", session_id)

    return ProcessDocumentsResponse(
        session_id=session_id,
        extracted_data=result.model_dump(),
        validation_warnings=warnings,
    )


async def update_session(session_id: str, verified_data: dict[str, Any]) -> dict[str, Any]:
    """Overwrite the session with user-edited data. Returns the stored data."""
    if session_id not in _sessions:
        from fastapi import HTTPException
        raise HTTPException(
            status_code=404,
            detail=f"Session '{session_id}' not found or expired. Re-upload documents.",
        )
    _sessions[session_id] = verified_data
    _log.info("Session %s updated by reviewer.", session_id)
    return verified_data


def get_session(session_id: str) -> dict[str, Any]:
    """Return stored session data, or raise 404."""
    if session_id not in _sessions:
        from fastapi import HTTPException
        raise HTTPException(
            status_code=404,
            detail=f"Session '{session_id}' not found or expired.",
        )
    return _sessions[session_id]
