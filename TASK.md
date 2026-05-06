# Document Extraction Pipeline — Implementation Plan

## Problem Statement

Currently the `/fill` endpoint accepts a pre-built JSON body. The requirement is to add an upstream pipeline that:
1. Accepts raw identity documents (Emirates ID PDF, Passport PDF, Q&A DOCX)
2. Extracts and normalises data into the same JSON shape `input_client.json` expects
3. Presents that JSON to the frontend for verification/editing
4. Accepts the verified JSON and forwards it to the existing `/fill` endpoint

---

## Architecture Decision

### What changes, what does not

| Layer | Status |
|---|---|
| `src/pdf_filler/` | **Untouched** — core engine stays as-is |
| `api/` | **Untouched** — existing routes stay as-is |
| `src/document_pipeline/` | **New** — all extraction, parsing, validation logic lives here |
| `api/routes/documents.py` | **New** — two thin route handlers only, no business logic |
| `api/schemas/documents.py` | **New** — request/response Pydantic models for the new routes |
| `api/services/document_service.py` | **New** — thin orchestrator that calls into `src/document_pipeline/` |

### New folder: `src/document_pipeline/`

```
src/document_pipeline/
├── __init__.py
├── ocr.py                  # PDF → image → text via Tesseract/EasyOCR
├── mrz.py                  # Passport MRZ extraction via FastMRZ
├── emirates_id.py          # Emirates ID field parsing (regex + heuristics)
├── qa_document.py          # Q&A DOCX parsing via python-docx
├── normaliser.py           # Merge extracted sources → unified JSON dict
├── cross_validator.py      # Cross-document field consistency checks
└── models.py               # Pydantic models for extraction results
```

---

## New Routes

### Route 1: Upload and process documents

```
POST /api/v1/documents/process
Content-Type: multipart/form-data

Fields:
  emirates_id_file  (PDF, required)
  passport_file     (PDF, required)
  qa_document_file  (DOCX, required)

Response 200:
{
  "session_id": "<uuid>",
  "extracted_data": { ...same shape as input_client.json... },
  "validation_warnings": [
    { "field": "name", "message": "Passport name 'OMAR AHMED' differs from Emirates ID 'Omar Ahmed'" }
  ]
}

Response 422:
{
  "detail": "Emirates ID PDF contains no readable image layer"
}
```

`session_id` is a server-side key (in-memory dict or temp file) that stores
the extracted JSON so Route 2 does not re-upload files.

### Route 2: Submit verified data to fill

```
POST /api/v1/documents/verify
Content-Type: application/json

Body:
{
  "session_id": "<uuid>",
  "verified_data": { ...user-edited JSON... },
  "template_id": "schengen"
}

Response 200: application/pdf  (the filled PDF, identical to /fill response)
```

This route validates `verified_data`, then internally calls the same
`PdfFillService.fill_template()` used by `/fill`. No duplication.

---

## Library Recommendations

### Mandatory

| Library | Why | Install |
|---|---|---|
| `FastMRZ` | Machine-readable zone parsing from passport image. Returns structured dict with surname, given_names, nationality, DOB, expiry, document_number. | `pip install fastmrz` |
| `python-docx` | Parse `.docx` Q&A document — iterate paragraphs, tables, detect Q&A pattern. | `pip install python-docx` |
| `pymupdf` (already installed) | Extract page as pixmap (PNG bytes) from Emirates ID PDF and Passport PDF before OCR. | already present |
| `Pillow` | Image pre-processing before OCR (contrast, resize, grayscale). FastMRZ and pytesseract both accept PIL images. | `pip install Pillow` |

### OCR (choose one)

| Option | Pros | Cons |
|---|---|---|
| **Tesseract + pytesseract** | Best Arabic support (ara traineddata), free, battle-tested, runs locally | Requires system-level `tesseract` binary install |
| **EasyOCR** | Pure Python install, supports Arabic+English in one call, no system binary | Large model download (~500 MB GPU / ~200 MB CPU), slower first run |

**Recommendation: pytesseract** for the Emirates ID (needs Arabic for the Arabic name side). The English fields on the Emirates ID and the entire passport can use `eng` lang. Install: `pip install pytesseract` + `choco install tesseract` on Windows or apt on Linux.

### Optional but useful

| Library | Why |
|---|---|
| `python-dateutil` (already installed) | Parse any date string format from OCR output |
| `fuzzywuzzy` / `thefuzz` | Fuzzy name matching for cross-document validation (handles OCR noise) |
| `regex` | More powerful than `re` for Arabic Unicode ranges and lookaheads |

---

## Implementation Steps (ordered)

### Step 1 — Models (`src/document_pipeline/models.py`)

Define Pydantic v2 models for intermediate extraction results:

```python
class PassportData(BaseModel):
    surname: str
    given_names: str
    document_number: str
    nationality: str
    date_of_birth: str      # ISO format
    expiry_date: str        # ISO format
    issuing_country: str
    sex: str

class EmiratesIdData(BaseModel):
    full_name_en: str
    full_name_ar: str | None
    id_number: str          # 784-YYYY-XXXXXXX-X
    nationality: str
    date_of_birth: str
    expiry_date: str
    gender: str

class QAData(BaseModel):
    raw_answers: dict[str, str]     # question_key → answer text

class ExtractionResult(BaseModel):
    passport: PassportData | None
    emirates_id: EmiratesIdData | None
    qa: QAData | None
    extraction_errors: list[str]
```

### Step 2 — PDF to image (`src/document_pipeline/ocr.py`)

Use PyMuPDF (already installed) to render PDF pages to PNG in memory:

```python
def pdf_page_to_image(pdf_bytes: bytes, page_index: int = 0, dpi: int = 300) -> bytes:
    """Return PNG bytes for one page of a PDF."""
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    page = doc[page_index]
    mat = fitz.Matrix(dpi / 72, dpi / 72)
    pix = page.get_pixmap(matrix=mat, colorspace=fitz.csRGB)
    return pix.tobytes("png")

def extract_text_from_pdf_image(pdf_bytes: bytes, lang: str = "eng") -> str:
    """OCR all pages of a PDF, return concatenated text."""
    ...
```

Emirates ID PDFs contain scanned images — render each page at 300 DPI for acceptable OCR quality.

### Step 3 — Passport MRZ extraction (`src/document_pipeline/mrz.py`)

FastMRZ accepts a file path or PIL image. Wrap it:

```python
from fastmrz import FastMRZ

def extract_passport_mrz(pdf_bytes: bytes) -> PassportData:
    """
    Render passport PDF page to image, run FastMRZ, return structured data.
    Raises ValueError if MRZ is not detected.
    """
    png_bytes = pdf_page_to_image(pdf_bytes, page_index=0, dpi=300)
    image = Image.open(io.BytesIO(png_bytes))
    mrz = FastMRZ()
    result = mrz.get_passport_details(image)
    # result is a dict: {"surname": ..., "given_names": ..., ...}
    if not result or result.get("mrz_type") not in ("TD3", "TD1", "TD2"):
        raise ValueError("No valid MRZ found in passport PDF")
    return PassportData(...)
```

FastMRZ returns a dict with keys: `mrz_type`, `document_type`, `country`, `surname`,
`given_names`, `document_number`, `nationality`, `date_of_birth`, `sex`, `expiry_date`.

### Step 4 — Emirates ID parsing (`src/document_pipeline/emirates_id.py`)

Emirates IDs have a predictable layout. After OCR:
1. ID number: regex `784-\d{4}-\d{7}-\d`
2. Name: line after "Name:" label
3. Nationality: line after "Nationality:"
4. DOB: regex for DD/MM/YYYY or DD-MM-YYYY
5. Expiry: similar to DOB
6. Gender: "Male" / "Female" / "M" / "F"

```python
def parse_emirates_id_text(ocr_text: str) -> EmiratesIdData:
    ...

def extract_emirates_id(pdf_bytes: bytes) -> EmiratesIdData:
    text = extract_text_from_pdf_image(pdf_bytes, lang="eng+ara")
    return parse_emirates_id_text(text)
```

Keep regex patterns as module-level constants so they can be adjusted without touching logic.

### Step 5 — Q&A DOCX parsing (`src/document_pipeline/qa_document.py`)

Use `python-docx` to iterate paragraphs. Q&A documents typically follow one of:
- "Question: ...\nAnswer: ..."
- Numbered questions with answers below
- Table format (question column, answer column)

```python
from docx import Document

def extract_qa_answers(docx_bytes: bytes) -> QAData:
    doc = Document(io.BytesIO(docx_bytes))
    raw_answers: dict[str, str] = {}

    # Strategy 1: table format
    for table in doc.tables:
        ...

    # Strategy 2: paragraph Q&A pattern
    for para in doc.paragraphs:
        ...

    return QAData(raw_answers=raw_answers)
```

The exact Q&A key mapping (e.g. `"journey_purpose"` ← `"What is the purpose of your visit?"`) must be defined as a mapping dict in this file. This is document-specific and will need adjustment per real document layout.

### Step 6 — Normaliser (`src/document_pipeline/normaliser.py`)

Takes `ExtractionResult` and maps fields into the flat JSON dict that
`input_client.json` / `FillRequest.data` expects:

```python
def normalise_to_fill_data(result: ExtractionResult) -> dict[str, Any]:
    data: dict[str, Any] = {}

    if result.passport:
        p = result.passport
        data["surname"] = p.surname.title()
        data["first_name"] = p.given_names.title()
        data["date_of_birth"] = _reformat_date(p.date_of_birth)
        data["passport_number"] = p.document_number
        data["passport_valid_until"] = _reformat_date(p.expiry_date)
        data["current_nationality"] = _map_country_code(p.nationality)
        data["nationality_at_birth"] = _map_country_code(p.nationality)
        data["sex"] = _normalise_sex(p.sex)

    if result.emirates_id:
        e = result.emirates_id
        data.setdefault("surname", e.full_name_en.split()[-1])
        data["national_identity_number"] = e.id_number
        # Do NOT overwrite passport name — passport is more reliable for Schengen

    if result.qa:
        data.update(_map_qa_answers(result.qa.raw_answers))

    return data
```

Note: passport data takes precedence over Emirates ID for name/DOB/nationality
because the MRZ is machine-printed and more reliable than OCR of Emirates ID text.

### Step 7 — Cross-validator (`src/document_pipeline/cross_validator.py`)

Returns a list of `ValidationWarning` (not errors — mismatches are warnings,
the user resolves them in the verification step):

```python
@dataclass
class ValidationWarning:
    field: str
    message: str
    source_a: str
    source_b: str

def cross_validate(result: ExtractionResult) -> list[ValidationWarning]:
    warnings = []

    # Name match (fuzzy — OCR introduces noise)
    if result.passport and result.emirates_id:
        passport_name = f"{result.passport.given_names} {result.passport.surname}"
        eid_name = result.emirates_id.full_name_en
        if not _names_match(passport_name, eid_name):
            warnings.append(ValidationWarning(
                field="name",
                message=f"Passport name '{passport_name}' vs Emirates ID '{eid_name}'",
                source_a="passport",
                source_b="emirates_id"
            ))

    # DOB match
    # Nationality match
    # Passport expiry must be > today + 6 months (Schengen requirement)
    # Emirates ID expiry must be > today
    # Required Q&A fields must have non-empty answers

    return warnings
```

### Step 8 — API schemas (`api/schemas/documents.py`)

```python
class ProcessDocumentsResponse(BaseModel):
    session_id: str
    extracted_data: dict[str, Any]
    validation_warnings: list[ValidationWarningSchema]

class VerifyAndFillRequest(BaseModel):
    session_id: str
    verified_data: dict[str, Any]
    template_id: str
```

### Step 9 — Document service (`api/services/document_service.py`)

Thin orchestrator. Does:
1. Read uploaded file bytes
2. Call `src/document_pipeline` functions
3. Store `session_id → extracted_data` in an in-memory dict
4. On verify: retrieve session data, call existing `PdfFillService`

```python
_sessions: dict[str, dict] = {}   # process-local, good enough for MVP

async def process_documents(
    emirates_id_bytes: bytes,
    passport_bytes: bytes,
    qa_bytes: bytes,
) -> ProcessDocumentsResponse:
    ...

async def verify_and_fill(
    request: VerifyAndFillRequest,
    templates_root: Path,
) -> tuple[bytes, FillResult]:
    ...
```

**Warning**: in-process session dict is lost on restart and does not work with
multiple workers. For production, replace with Redis or a temp file keyed by
session_id. This is explicitly a later concern.

### Step 10 — Route handlers (`api/routes/documents.py`)

```python
router = APIRouter(prefix="/api/v1/documents", tags=["documents"])

@router.post("/process", response_model=ProcessDocumentsResponse)
async def process_documents_route(
    emirates_id_file: UploadFile = File(...),
    passport_file: UploadFile = File(...),
    qa_document_file: UploadFile = File(...),
):
    ...

@router.post("/verify")
async def verify_and_fill_route(
    request: VerifyAndFillRequest,
    templates_root: Path = Depends(get_templates_root),
):
    ...
```

Register router in `api/main.py`.

### Step 11 — Wire into `api/main.py`

Add:
```python
from api.routes.documents import router as documents_router
app.include_router(documents_router)
```

### Step 12 — Add dependencies to `requirements.txt` / `pyproject.toml`

```
fastmrz>=1.0
python-docx>=1.1
Pillow>=10.0
pytesseract>=0.3.13
thefuzz>=0.22       # for fuzzy name matching in cross_validator
```

System dependency: Tesseract binary + language packs:
- Windows: `choco install tesseract` + download `ara.traineddata` to tessdata dir
- Ubuntu/Debian: `apt install tesseract-ocr tesseract-ocr-ara tesseract-ocr-eng`

---

## File Creation Checklist

```
src/document_pipeline/__init__.py
src/document_pipeline/models.py           # Pydantic extraction result models
src/document_pipeline/ocr.py              # PDF → image → OCR text
src/document_pipeline/mrz.py              # Passport MRZ via FastMRZ
src/document_pipeline/emirates_id.py      # Emirates ID field regex parsing
src/document_pipeline/qa_document.py      # DOCX Q&A parsing via python-docx
src/document_pipeline/normaliser.py       # ExtractionResult → fill JSON dict
src/document_pipeline/cross_validator.py  # Cross-document consistency checks
api/schemas/documents.py                  # Request/response schemas
api/services/document_service.py          # Orchestrator (calls pipeline, stores session)
api/routes/documents.py                   # Two route handlers
```

Modify:
```
api/main.py                               # Register new router
requirements.txt                          # Add new dependencies
pyproject.toml                            # Add to [project.optional-dependencies]
```

---

## Known Risks / Issues to Resolve Before Coding

1. **Emirates ID OCR accuracy**: Scanned quality varies wildly. The parsing regexes in `emirates_id.py` will need tuning against real samples. Build with real files, not assumptions.

2. **FastMRZ Windows compatibility**: FastMRZ uses OpenCV under the hood. Verify `pip install fastmrz` works in your `.venv` on Windows before committing to it. Alternative: `passporteye` library.

3. **Q&A document format is unknown**: `qa_document.py` parsing strategy depends entirely on the actual document layout. The step above shows two strategies; the real implementation must be driven by an actual sample file.

4. **Session storage is not production-ready**: The in-memory dict in `document_service.py` is intentionally minimal for the first iteration. Production needs Redis or disk-based temp storage with TTL.

5. **Tesseract on Windows**: Requires manual install of the binary and language data. Document this in README. EasyOCR is pure-Python but significantly heavier — worth reconsidering if Tesseract install is a blocker.

6. **File size limits**: Emirates ID and Passport PDFs are typically small (<2 MB). The existing `max_upload_bytes = 50 MB` in `api/core/config.py` is fine. No change needed.
