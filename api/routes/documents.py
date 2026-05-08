"""Document extraction pipeline routes.

POST /api/v1/documents/process
  Upload three documents → extract raw data → return for review.

POST /api/v1/documents/verify
  Submit user-edited data → store in session → return for confirmation.

POST /api/v1/documents/fill  (future)
  AI maps verified session data → PDF fields → return filled PDF.
"""

from __future__ import annotations

from fastapi import APIRouter, File, Form, UploadFile

from api.core.config import settings
from api.schemas.documents import ProcessDocumentsResponse, VerifyRequest, VerifyResponse
from api.services import document_service

router = APIRouter(prefix="/documents", tags=["documents"])


@router.post("/process", response_model=ProcessDocumentsResponse)
async def process_documents(
    template_id: str = Form(..., description="Template ID (must exist under templates/)"),
    emirates_id_file: UploadFile = File(..., description="Emirates ID PDF"),
    passport_file: UploadFile = File(..., description="Passport PDF"),
    qa_document_file: UploadFile = File(..., description="Q&A document (.docx)"),
) -> ProcessDocumentsResponse:
    """Extract raw data from uploaded documents, map fields via AI, and return client_json."""
    _validate_upload(emirates_id_file, expected_suffix=".pdf", label="emirates_id_file")
    _validate_upload(passport_file, expected_suffix=".pdf", label="passport_file")
    _validate_upload(qa_document_file, expected_suffix=".docx", label="qa_document_file")

    return await document_service.process_documents(
        emirates_id_bytes=await _read_upload(emirates_id_file),
        passport_bytes=await _read_upload(passport_file),
        qa_bytes=await _read_upload(qa_document_file),
        template_id=template_id,
    )


@router.post("/verify", response_model=VerifyResponse)
async def verify_documents(request: VerifyRequest) -> VerifyResponse:
    """Store the reviewer's corrected data against the session.

    Returns the stored data so the frontend can display it for final confirmation.
    """
    verified = await document_service.update_session(
        session_id=request.session_id,
        verified_data=request.verified_data,
    )
    return VerifyResponse(session_id=request.session_id, verified_data=verified)


# --- Helpers ---

def _validate_upload(upload: UploadFile, expected_suffix: str, label: str) -> None:
    from fastapi import HTTPException

    filename = upload.filename or ""
    if not filename.lower().endswith(expected_suffix):
        raise HTTPException(
            status_code=422,
            detail=f"'{label}' must be a {expected_suffix} file, got: '{filename}'",
        )


async def _read_upload(upload: UploadFile) -> bytes:
    from fastapi import HTTPException

    data = await upload.read()
    if len(data) > settings.max_upload_bytes:
        limit_mb = settings.max_upload_bytes // 1024 // 1024
        raise HTTPException(
            status_code=413,
            detail=(
                f"File '{upload.filename}' exceeds the {limit_mb} MB limit "
                f"({len(data) // 1024 // 1024} MB uploaded)."
            ),
        )
    if not data:
        raise HTTPException(
            status_code=422,
            detail=f"File '{upload.filename}' is empty.",
        )
    return data
