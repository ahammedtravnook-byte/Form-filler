# PDF Filler API

A Python library, CLI, and FastAPI backend for filling static, coordinate-based PDF templates without requiring AcroForm or XFA fields.

It loads PDF templates, reads JSON field-coordinate schemas, stamps text or checkbox values onto exact PDF positions, and returns filled PDFs through the CLI or API.

---

## Features

- Fill static PDF templates using PyMuPDF coordinates
- Supports text, multiline text, dates, checkboxes, checkbox groups, and signature text
- FastAPI backend for single, batch, and Excel-based PDF generation
- CLI support for local PDF filling
- Template metadata validation with SHA-256 and page count checks
- Admin API for managing templates
- ZIP output for batch and Excel workflows

---

## Tech Stack

| Area | Technology |
|---|---|
| Language | Python 3.11+ |
| API Framework | FastAPI |
| ASGI Server | Uvicorn |
| PDF Engine | PyMuPDF |
| Validation | Pydantic v2 |
| Settings | pydantic-settings |
| CLI | Typer, Rich |
| Excel Parsing | OpenPyXL |
| Testing | pytest |
| Linting / Formatting | Ruff |
| Type Checking | mypy |
| Build Backend | Setuptools |

---

## Project Overview

### What This Project Does

This project fills static PDF templates using a coordinate-based field schema.

Each template lives under:

```txt
templates/<template_id>/
```

Expected files:

```txt
template.pdf
fields_config.json
template_metadata.json
```

The system:

1. Loads a PDF template.
2. Loads and validates field coordinates.
3. Reads flat JSON input data.
4. Stamps values onto the PDF.
5. Returns a filled PDF or ZIP archive.

---

## Architecture

### Application Type

This is a Python full-stack utility backend:

- Python library
- CLI tool
- FastAPI backend
- Template management API

It is not a frontend app and does not require a database.

### Main Flow

```txt
Request / CLI Input
        ↓
Select template_id
        ↓
Load fields_config.json
        ↓
Validate metadata and template.pdf
        ↓
Stamp values with PyMuPDF
        ↓
Return PDF or ZIP
```

### Core Modules

| File | Purpose |
|---|---|
| `src/pdf_filler/filler.py` | Core PDF rendering engine |
| `src/pdf_filler/models.py` | Pydantic schemas for field configs and metadata |
| `src/pdf_filler/validators.py` | Template, input, metadata, and date validation |
| `api/main.py` | FastAPI app setup, middleware, and routers |
| `api/services/pdf_fill_service.py` | Async wrapper around PDF filling |
| `api/services/storage_service.py` | Filesystem-backed template storage |
| `api/routes/submissions.py` | Public fill, batch, Excel, and validation routes |
| `api/routes/admin_templates.py` | Admin template management routes |

---

## API Endpoints

### Public Endpoints

| Method | Endpoint | Purpose |
|---|---|---|
| GET | `/api/v1/templates` | List available templates |
| GET | `/api/v1/templates/{template_id}` | Get template metadata |
| POST | `/api/v1/templates/{template_id}/validate` | Validate input data |
| POST | `/api/v1/templates/{template_id}/fill` | Generate one filled PDF |
| POST | `/api/v1/templates/{template_id}/fill/batch` | Generate multiple PDFs as ZIP |
| POST | `/api/v1/templates/{template_id}/fill/excel` | Generate PDFs from Excel rows |

### Admin Endpoints

Admin routes require a bearer API key.

| Method | Endpoint | Purpose |
|---|---|---|
| POST | `/api/v1/admin/templates/{template_id}` | Upload template |
| PUT | `/api/v1/admin/templates/{template_id}` | Replace template |
| PATCH | `/api/v1/admin/templates/{template_id}/fields-config` | Update field config |
| GET | `/api/v1/admin/templates/{template_id}/fields-config` | Read field config |
| DELETE | `/api/v1/admin/templates/{template_id}` | Delete template |

---

## Key Libraries

| Library | Used For |
|---|---|
| fastapi | API routes and request handling |
| uvicorn | Running the ASGI app |
| pymupdf | Opening and stamping PDF files |
| pydantic | Validating configs, metadata, and API models |
| pydantic-settings | Environment-based configuration |
| typer | CLI commands |
| rich | Better CLI output |
| openpyxl | Parsing Excel uploads |
| pytest | Testing |
| ruff | Linting and formatting |
| mypy | Static type checking |

---

## Important Configuration

### Critical Files

| File | Purpose |
|---|---|
| `pyproject.toml` | Dependencies, CLI entrypoint, test/lint/typecheck config |
| `api/core/config.py` | Runtime settings and environment variables |
| `api/main.py` | App setup, middleware, routers, CORS |
| `fields_config.json` | Field coordinate schema for each template |
| `template_metadata.json` | Optional template hash and page-count validation |
| `template.pdf` | Source PDF template |

### Environment Variables

| Variable | Purpose |
|---|---|
| `PDF_API_ADMIN_API_KEY` | Admin bearer token |
| `PDF_API_TEMPLATES_DIR` | Template storage directory |
| `PDF_API_MAX_UPLOAD_BYTES` | Max upload size |
| `PDF_API_LOG_LEVEL` | Logging level |
| `PDF_API_LOG_JSON` | JSON log output |
| `PDF_API_DEBUG_BOXES` | Debug PDF field boxes |
| `PDF_API_IGNORE_TEMPLATE_HASH` | Skip template hash validation |

`PDF_API_ADMIN_API_KEY` must be set in production.

---

## Known Issues and Improvement Scope

### Code Quality Issues

| Severity | Area | Issue | Suggested Fix |
|---|---|---|---|
| Critical | `src/pdf_filler/filler.py` | Debug `print(type(fcfg))` inside render loop | Remove or replace with debug logging |
| High | `src/pdf_filler/filler.py` | Text overflow behavior may be inconsistent | Consolidate overflow strategy and add tests |
| High | `api/services/pdf_fill_service.py` | `run_in_executor(None, ...)` uses default executor | Use a bounded thread pool |
| High | `api/services/storage_service.py` | `template_id` may be used directly in paths | Validate with strict regex |
| Medium | `api/main.py` | CORS allows all origins and headers | Restrict origins in production |
| Medium | Batch fill API | No clear max batch record limit | Add max record validation |
| Low | `api/services/excel_service.py` | Uses `__import__("io").BytesIO(...)` | Replace with normal `import io` |

---

## Security Review

### Security Issues

| Severity | Area | Risk | Fix |
|---|---|---|---|
| Critical | Template storage | Path traversal through `template_id` | Enforce `^[A-Za-z0-9_-]+$` |
| Critical | Admin API key | Unsafe default admin key | Fail startup if key is missing or default |
| High | CORS | Overly permissive browser access | Restrict allowed origins |
| High | PDF generation | Possible CPU exhaustion | Add rate limits and concurrency caps |
| High | Admin uploads | Unsafe or malformed uploads | Validate file type, size, and content |
| Medium | Excel parsing | XLSX resource exhaustion | Limit rows, columns, and file size |
| Medium | Error handling | Raw exception messages may leak details | Sanitize unexpected errors |

---

## Testing Gaps

### Existing Tests

Tests are present for:

- `tests/test_coordinates.py`
- `tests/test_filler.py`
- `tests/test_models.py`

### Recommended Tests

| Area | Tests |
|---|---|
| Security | Path traversal, admin auth, invalid template IDs |
| PDF Rendering | Overflow, truncation, shrink, multiline behavior |
| Checkbox Logic | Scalar and list input matching |
| API Integration | Fill, validate, batch ZIP, Excel upload |
| Error Handling | Missing fields, invalid metadata, invalid PDFs |
| Performance | Large batch limits and timeout behavior |

---

## Performance and Scalability

### Bottlenecks

- PDF stamping is CPU-bound
- Batch endpoints multiply rendering work
- Large Excel files can consume memory and CPU
- Repeated config parsing can add overhead

### Improvements

- Add max batch size
- Add max Excel rows and columns
- Use a bounded `ThreadPoolExecutor`
- Add request rate limiting
- Cache validated template configs
- Avoid caching PyMuPDF document objects unless thread-safety is proven

---

## Deployment Recommendation

### Recommended Deployment

Deploy as a Dockerized FastAPI service.

Best-fit platforms:

- Fly.io
- Render
- Railway
- GCP Cloud Run
- AWS ECS
- Docker VPS

### Why Docker

- Simple Python backend
- No database required
- Predictable runtime
- Easy CI/CD
- Works well with mounted template storage

### Start Command

```bash
uvicorn api.main:app --host 0.0.0.0 --port 8000
```

### Production Requirements

Set at minimum:

```env
PDF_API_ADMIN_API_KEY=<secure-random-secret>
PDF_API_TEMPLATES_DIR=/app/templates
PDF_API_LOG_LEVEL=INFO
PDF_API_LOG_JSON=true
PDF_API_DEBUG_BOXES=false
PDF_API_IGNORE_TEMPLATE_HASH=false
```

### Storage Options

| Use Case | Recommendation |
|---|---|
| Static templates only | Bake templates into Docker image |
| Admin upload support | Use persistent volume |
| Cloud-native setup | Store templates in object storage later |

### CI/CD Checklist

```bash
pytest
ruff check .
ruff format --check .
mypy .
```

Deploy only after all checks pass.

---

## Production Checklist

- [ ] Set a strong `PDF_API_ADMIN_API_KEY`
- [ ] Remove unsafe default admin key behavior
- [ ] Restrict CORS origins
- [ ] Validate all `template_id` values
- [ ] Add request rate limiting
- [ ] Add max batch size
- [ ] Add Excel row and column limits
- [ ] Sanitize ZIP filenames
- [ ] Remove debug prints
- [ ] Run tests, linting, and type checks in CI
- [ ] Use persistent storage if admin uploads are enabled
- [ ] Enable structured production logging
- [ ] Validate template metadata and SHA-256 hashes

---

## Quick Start

```bash
pip install -e .
uvicorn api.main:app --reload
```

Open:

```txt
http://localhost:8000/docs
```

---

## CLI Usage

```bash
pdf-filler --help
```

---

## Development Commands

```bash
pytest
ruff check .
ruff format .
mypy .
```

---

## License

Add your license here.
