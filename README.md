# PDF Filler API

A production-ready FastAPI service that intelligently fills coordinate-based PDF templates with extracted document data. Upload passports, Emirates IDs, and Q&A documents → extract fields via OCR → AI-maps data → generates filled PDFs.

---

## About the Project

**PDF Filler** is an automated document processing system designed to:
- Extract structured data from unstructured documents (passports, ID cards, Q&A documents)
- Map extracted fields to PDF template coordinates using AI
- Generate completed PDFs by filling template coordinates with mapped data
- Validate cross-document consistency and flag discrepancies

### Why Coordinate-Based?

Many real-world forms are distributed as **printed/scanned, non-fillable PDFs**. They have no AcroForm or XFA fields, so traditional form-filling libraries can't help. This project treats the PDF as a **visual template** and stamps values at precise coordinates.

- No PDF form fields required
- Original template file never modified
- Output is a normal, flattened PDF where values are part of the page content

---

## MVP Workflow

The MVP uses a **3-step flow**:

```
1. POST /api/v1/documents/process
   ↓ [Upload: Passport PDF + Emirates ID PDF + Q&A .docx]
   ↓ [Extract: OCR passport MRZ, ID numbers, Q&A answers]
   ↓ [AI Map: Match extracted fields → template fields]
   → Returns: session_id + client_json (extracted data for review)

2. POST /api/v1/documents/verify
   ↓ [Send: session_id + user-corrected data]
   ↓ [Store: Lock session for final confirmation]
   → Returns: verified_data (confirmation)

3. POST /api/v1/templates/{template_id}/fill
   ↓ [Send: session_id + template_id]
   ↓ [Retrieve: Verified session data]
   ↓ [Fill: Place data at template coordinates]
   → Returns: Filled PDF binary
```

**Frontend Integration**: Client calls step 1 → displays extracted data for review → user corrects fields → calls step 2 → calls step 3 to download filled PDF.

---

## Tech Stack

| Layer | Technology | Purpose |
|-------|-----------|---------|
| **Framework** | FastAPI 0.111+ | Async REST API |
| **Server** | Uvicorn 0.29+ | ASGI application server |
| **PDF Engine** | PyMuPDF (fitz) 1.24+ | Read/write PDFs, coordinate mapping |
| **Validation** | Pydantic v2.6+ | Type-safe request/response models |
| **OCR** | Tesseract + pytesseract 0.3.10+ | Passport/ID field extraction |
| **MRZ Parsing** | FastMRZ | Machine Readable Zone (passport) parsing |
| **Document Parsing** | python-docx 1.1+ | Read .docx (Q&A answers) |
| **AI Mapping** | OpenAI GPT-4o-mini | Field mapping via LLM |
| **Fuzzy Matching** | thefuzz 0.22+ | Cross-document validation |
| **Image Processing** | Pillow 10.0+ | Image preprocessing for OCR |
| **Date Parsing** | python-dateutil | Flexible date parsing |
| **CLI Tool** | Typer | Command-line interface (dev only) |

---
## Folder Structure
<details>
<summary>Folder Structure</summary>

```text
pdf filler/
├── src/
│   ├── pdf_filler/                 # Core PDF filling engine
│   │   ├── engine.py              # Main PDF manipulation logic
│   │   ├── models.py              # Domain models (FieldCoord, etc.)
│   │   ├── logging_config.py      # Logging setup
│   │   └── ...
│   │
│   └── document_pipeline/          # NEW: Document extraction pipeline
│       ├── emirates_id.py         # Emirates ID OCR extraction
│       ├── mrz.py                 # Passport MRZ parsing
│       ├── qa_document.py         # Q&A .docx extraction
│       ├── cross_validator.py     # Validate across documents
│       ├── ocr.py                 # OCR wrapper (Tesseract)
│       ├── models.py              # Extraction result models
│       └── ...
│
├── api/                            # FastAPI application
│   ├── main.py                    # App factory, middleware, startup
│   ├── routes/
│   │   ├── health.py             # GET /health
│   │   ├── templates.py          # GET /templates, /templates/{id}
│   │   ├── submissions.py        # POST /submissions/fill
│   │   ├── admin_templates.py    # PUT /admin/templates
│   │   └── documents.py          # POST /documents/process, /verify
│   ├── services/
│   │   ├── document_service.py
│   │   ├── ai_mapping_service.py
│   │   ├── storage_service.py
│   │   └── pdf_service.py
│   ├── schemas/
│   ├── middleware/
│   │   ├── error_handler.py
│   │   └── request_id.py
│   └── core/
│       ├── config.py
│       └── logging.py
│
├── templates/
│   └── {template_id}/
│       ├── template.pdf
│       ├── template_hash.txt
│       ├── fields_config.json
│       └── .gitkeep
│
├── examples/
├── tests/
├── .env
├── .gitignore
├── requirements.txt
├── pyproject.toml
├── TASK.md
└── README.md
```

</details>


## Requirements & Installation

### System Requirements
- **Python**: 3.9+ (tested on 3.11)
- **Tesseract**: Installed separately (Windows/Linux/macOS)
- **OpenAI API Key**: For AI field mapping

### Step 1: Clone & Setup Environment

```bash
git clone <your-repo-url>
cd pdf\ filler

# Create virtual environment
python -m venv venv

# Activate (Windows)
venv\Scripts\activate

# Activate (macOS/Linux)
source venv/bin/activate
```

### Step 2: Install Tesseract (OCR Engine)

**Windows**:
```bash
# Download and run installer from:
https://github.com/UB-Mannheim/tesseract/wiki

# Default installs to: C:\Program Files\Tesseract-OCR\tesseract.exe
# Code auto-detects this path.
```

**macOS**:
```bash
brew install tesseract
```

**Linux (Ubuntu/Debian)**:
```bash
sudo apt-get install tesseract-ocr
```

### Step 3: Install Python Dependencies

```bash
pip install -r requirements.txt
```

**Key packages** (from `requirements.txt`):
```
fastapi>=0.111.0
uvicorn>=0.29.0
pymupdf>=1.24.0
pydantic>=2.6.0
pydantic-settings>=2.2.0
pytesseract>=0.3.10
python-docx>=1.1.0
openai>=1.0.0
thefuzz[speedup]>=0.22.0
Pillow>=10.0.0
python-dateutil>=2.8.0
typer[all]>=0.12.0
fastmrz>=0.3.0
```

### Step 4: Configure Environment

```bash
# Copy template and customize
cp .env.example .env

# Edit .env with your settings:
# - PDF_API_ADMIN_API_KEY: Strong random secret (generate one)
# - PDF_API_OPENAI_API_KEY: Your OpenAI API key
# - PDF_API_CORS_ORIGINS: Your frontend URL (production)
# - PDF_API_LOG_LEVEL: INFO, DEBUG, or WARNING
```

### Step 5: Run Locally

```bash
# Development mode (with auto-reload)
python -m api.main

# Server starts at http://localhost:8000
# API Docs: http://localhost:8000/docs
# ReDoc: http://localhost:8000/redoc
```

---

## Templates Folder & Requirements

### Structure
Each template is a **folder** under `templates/{template_id}/`:

```
templates/
├── visa_form_2024/
│   ├── template.pdf              # Source PDF (NOT committed to git)
│   ├── template_hash.txt         # SHA-256: "abc123..."
│   ├── fields_config.json        # Coordinate mappings
│   └── .gitkeep
│
└── kyc_application/
    ├── template.pdf
    ├── template_hash.txt
    ├── fields_config.json
    └── .gitkeep
```

### fields_config.json Format

Defines **which template fields map to which extracted data fields**:

```json
{
  "template_fields": [
    {
      "name": "applicant_full_name",
      "type": "text",
      "coordinates": {
        "page": 0,
        "x": 100,
        "y": 250,
        "width": 200,
        "height": 20,
        "font_size": 12
      },
      "required": true,
      "sources": ["passport.given_names", "passport.surname"]
    },
    {
      "name": "id_number",
      "type": "text",
      "coordinates": { ... },
      "required": true,
      "sources": ["emirates_id.id_number"]
    }
  ]
}
```

**Key Fields**:
- `coordinates`: Pixel location on PDF page (x, y = top-left)
- `sources`: Which extracted fields populate this (AI maps during `/process`)
- `required`: If true and missing, returns warning
- `type`: "text" (main type; extensible for "image", "date", etc.)

### Creating a New Template

1. **Get the PDF**: Have designer create or existing PDF form
2. **Generate coordinates**: Use PyMuPDF to identify field locations
3. **Create fields_config.json** with mappings
4. **Calculate SHA-256**:
   ```bash
   sha256sum template.pdf > template_hash.txt
   ```
5. **Upload** via `PUT /api/v1/admin/templates/{template_id}` (requires admin API key)

### Template Hash Validation

- Hash ensures PDF hasn't changed between template definition & fill-time
- If `template.pdf` changes but coordinates aren't updated → fills break
- Override via `PDF_API_IGNORE_TEMPLATE_HASH=true` (dev only)

---

## Sessions

### What is a Session?

A **session** is a **server-side in-memory container** holding:
- Extracted data (from `/process`)
- Verified/corrected data (from `/verify`)
- Session metadata (creation time, template_id, etc.)

### Session Lifecycle

```
1. /process called
   → New session created
   → session_id = UUID (returned to client)
   → _sessions[session_id] = extracted_dump

2. Client reviews data, corrects as needed

3. /verify called with corrected data
   → Session updated with verified_data
   → session_id added to _verified set (locked)
   → Session cannot be re-verified

4. /fill called with session_id
   → Retrieves session data
   → Fills PDF template
   → Returns PDF binary

5. Session expires
   → After ~1 hour (not yet implemented)
   → Can manually clear via admin endpoint (future)
```

### Session Storage (MVP Limitation)

⚠️ **Current**: Sessions stored in Python dict (`_sessions`) — **lost on server restart**

**Production workaround**: 
- Deploy single-worker (not multi-worker behind load balancer)
- Or implement Redis backend:
  ```python
  # Future: Replace _sessions dict with Redis client
  import redis
  r = redis.Redis(host='localhost', port=6379)
  r.set(session_id, json.dumps(data), ex=3600)  # 1 hour TTL
  ```

### Security
- Session IDs are UUIDs (cryptographically random)
- No sensitive data in session ID itself
- Sessions are server-side (not sent to client repeatedly)

---

## Running & Deployment

### Local Development

```bash
# Terminal 1: Run API server
python -m api.main
# Server: http://localhost:8000
# Docs: http://localhost:8000/docs

# Terminal 2: Test endpoints (optional)
curl http://localhost:8000/health
# {"status": "ok"}
```

### Deployment on AWS

#### Option A: EC2 + Systemd (Recommended for MVP)

1. **Launch EC2 Instance**
   - AMI: Ubuntu 22.04 LTS
   - Instance type: t3.medium (1GB RAM minimum for Tesseract)
   - Security groups: Allow HTTP (80), HTTPS (443), optionally SSH (22)
   - Storage: 30 GB (for templates + logs)

2. **SSH into Instance & Setup**
   ```bash
   sudo apt-get update && sudo apt-get upgrade -y
   sudo apt-get install -y python3.11 python3.11-venv git tesseract-ocr
   
   git clone <your-repo>
   cd pdf\ filler
   python3.11 -m venv venv
   source venv/bin/activate
   pip install -r requirements.txt
   ```

3. **Create Systemd Service** (`/etc/systemd/system/pdf-filler.service`)
   ```ini
   [Unit]
   Description=PDF Filler API
   After=network.target

   [Service]
   Type=notify
   User=ubuntu
   WorkingDirectory=/home/ubuntu/pdf\ filler
   Environment="PATH=/home/ubuntu/pdf\ filler/venv/bin"
   EnvironmentFile=/home/ubuntu/pdf\ filler/.env
   ExecStart=/home/ubuntu/pdf\ filler/venv/bin/python -m uvicorn api.main:app --host 0.0.0.0 --port 8000 --workers 4
   Restart=always
   RestartSec=10

   [Install]
   WantedBy=multi-user.target
   ```

4. **Start Service**
   ```bash
   sudo systemctl enable pdf-filler
   sudo systemctl start pdf-filler
   sudo systemctl status pdf-filler
   ```

5. **Nginx Reverse Proxy** (forward port 80 → 8000)
   ```nginx
   server {
       listen 80;
       server_name your-domain.com;

       location / {
           proxy_pass http://127.0.0.1:8000;
           proxy_set_header Host $host;
           proxy_set_header X-Real-IP $remote_addr;
           proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
           proxy_set_header X-Forwarded-Proto $scheme;
       }
   }
   ```

6. **SSL Certificate** (Let's Encrypt)
   ```bash
   sudo apt-get install certbot python3-certbot-nginx
   sudo certbot certonly --nginx -d your-domain.com
   # Update nginx config with SSL cert paths
   ```

#### Option B: ECS + Fargate (Container)

1. **Create Dockerfile**
   ```dockerfile
   FROM python:3.11-slim
   RUN apt-get update && apt-get install -y tesseract-ocr && rm -rf /var/lib/apt/lists/*
   WORKDIR /app
   COPY requirements.txt .
   RUN pip install --no-cache-dir -r requirements.txt
   COPY . .
   CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000"]
   ```

2. **Build & Push to ECR**
   ```bash
   aws ecr create-repository --repository-name pdf-filler
   docker build -t pdf-filler .
   docker tag pdf-filler:latest <account-id>.dkr.ecr.us-east-1.amazonaws.com/pdf-filler:latest
   docker push <account-id>.dkr.ecr.us-east-1.amazonaws.com/pdf-filler:latest
   ```

3. **Deploy to ECS Fargate**
   - Create cluster, task definition, service in AWS Console
   - Mount EFS for templates & output PDFs (persistent storage)
   - Set environment variables in task definition from `.env`

#### Option C: Elastic Beanstalk (Easiest)

```bash
pip install awsebcli
eb init -p python-3.11 pdf-filler
eb create production
eb deploy
```

---

## File Storage Details

### Templates Storage
- **Location**: `{PDF_API_TEMPLATES_DIR}` (default: `./templates`)
- **Structure**: Each template is a folder: `templates/{template_id}/`
- **Files**:
  - `template.pdf` (binary, gitignored)
  - `fields_config.json` (text, committed)
  - `template_hash.txt` (text, committed)

### Session Storage
- **Location**: In-memory Python dict (`_sessions` in `document_service.py`)
- **Lifetime**: Lost on server restart (MVP limitation)
- **Future**: Redis or database backend

### Output PDFs
- **Location**: `output/` folder (gitignored by default)
- **Naming**: `{session_id}_{timestamp}.pdf`
- **Cleanup**: Manual delete or add cron job to remove old files

### Logs
- **Location**: Stdout by default (captured by systemd journal or Docker)
- **Format**: Human-readable or JSON (via `PDF_API_LOG_JSON=true`)
- **Level**: Configurable via `PDF_API_LOG_LEVEL` (INFO, DEBUG, WARNING, ERROR)

---

## API Endpoints

### Health Check

**GET** `/health`

Check if API is running.

**Response** (200):
```json
{
  "status": "ok"
}
```

---

### Document Processing Pipeline

#### 1. Extract from Documents

**POST** `/api/v1/documents/process`

Upload three documents → extract raw data → AI-map to template fields → return session for review.

**Request** (multipart/form-data):
- `template_id` (string, required): Template folder name (e.g., `visa_form_2024`)
- `emirates_id_file` (file, required): PDF of Emirates ID
- `passport_file` (file, required): PDF of passport
- `qa_document_file` (file, required): DOCX with Q&A answers

**Example cURL**:
```bash
curl -X POST http://localhost:8000/api/v1/documents/process \
  -F "template_id=visa_form_2024" \
  -F "emirates_id_file=@emirates_id.pdf" \
  -F "passport_file=@passport.pdf" \
  -F "qa_document_file=@qa.docx"
```

**Response** (200):
```json
{
  "session_id": "550e8400-e29b-41d4-a716-446655440000",
  "client_json": {
    "applicant_full_name": "JOHN SMITH",
    "id_number": "123456789",
    "date_of_birth": "1990-05-15",
    ...
  }
}
```

**Errors**:
- `404` Template not found
- `413` File exceeds size limit (50 MB default)
- `422` Wrong file type or empty file
- `500` Extraction or AI mapping failed (check logs)

---

#### 2. Verify Extracted Data

**POST** `/api/v1/documents/verify`

Client submits corrected/verified data. Locks session for confirmation.

**Request** (application/json):
```json
{
  "session_id": "550e8400-e29b-41d4-a716-446655440000",
  "verified_data": {
    "applicant_full_name": "JOHN DOE",
    "id_number": "123456789",
    "date_of_birth": "1990-05-15",
    ...
  }
}
```

**Response** (200):
```json
{
  "session_id": "550e8400-e29b-41d4-a716-446655440000",
  "verified_data": {
    "applicant_full_name": "JOHN DOE",
    "id_number": "123456789",
    ...
  }
}
```

**Errors**:
- `404` Session not found or expired
- `409` Session already verified (can't update)

---

#### 3. Fill PDF Template

**POST** `/api/v1/templates/{template_id}/fill`

Retrieve verified session data → fill PDF → return binary PDF.

**Request** (application/json):
```json
{
  "session_id": "550e8400-e29b-41d4-a716-446655440000"
}
```

**Response** (200):
- Content-Type: `application/pdf`
- Binary PDF file

**Example cURL**:
```bash
curl -X POST http://localhost:8000/api/v1/templates/visa_form_2024/fill \
  -H "Content-Type: application/json" \
  -d '{"session_id": "550e8400-e29b-41d4-a716-446655440000"}' \
  -o filled_form.pdf
```

**Errors**:
- `404` Template or session not found
- `400` Verification failed (missing required fields)

---

### Template Management

#### List All Templates

**GET** `/api/v1/templates`

Retrieve all available templates.

**Response** (200):
```json
{
  "templates": [
    {
      "template_id": "visa_form_2024",
      "fields_count": 25,
      "hash": "abc123..."
    },
    {
      "template_id": "kyc_application",
      "fields_count": 18,
      "hash": "def456..."
    }
  ]
}
```

---

#### Get Template Details

**GET** `/api/v1/templates/{template_id}`

Retrieve template fields configuration.

**Response** (200):
```json
{
  "template_id": "visa_form_2024",
  "fields": [
    {
      "name": "applicant_full_name",
      "type": "text",
      "required": true,
      "coordinates": { ... }
    }
  ],
  "hash": "abc123..."
}
```

---

#### Upload/Update Template (Admin)

**PUT** `/api/v1/admin/templates/{template_id}`

Create or update a template. Requires `Authorization: Bearer {admin_api_key}` header.

**Request** (multipart/form-data):
- `pdf_file` (file, required): Template PDF
- `fields_config` (file, required): JSON config

**Example cURL**:
```bash
curl -X PUT http://localhost:8000/api/v1/admin/templates/visa_form_2024 \
  -H "Authorization: Bearer your-strong-secret-key" \
  -F "pdf_file=@template.pdf" \
  -F "fields_config=@fields_config.json"
```

**Response** (200):
```json
{
  "status": "ok",
  "template_id": "visa_form_2024",
  "hash": "abc123..."
}
```

**Errors**:
- `401` Missing or invalid API key
- `400` Invalid JSON config
- `422` Missing required files

---

### Legacy Endpoint (Batch Fill)

**POST** `/api/v1/submissions/fill`

Legacy endpoint for batch-filling (single request → multiple PDFs).

**Request** (application/json):
```json
{
  "template_id": "visa_form_2024",
  "records": [
    {
      "applicant_full_name": "JOHN SMITH",
      "id_number": "123456789",
      ...
    },
    {
      "applicant_full_name": "JANE DOE",
      "id_number": "987654321",
      ...
    }
  ]
}
```

**Response** (200):
- Content-Type: `application/zip`
- ZIP file containing all filled PDFs

---

## Configuration Reference

All settings are environment variables prefixed with `PDF_API_` (see `.env`):

| Env Var | Type | Default | Description |
|---------|------|---------|-------------|
| `PDF_API_ADMIN_API_KEY` | string | `change-me-in-production` | Bearer token for admin routes |
| `PDF_API_OPENAI_API_KEY` | string | (empty) | OpenAI API key for field mapping |
| `PDF_API_OPENAI_MODEL` | string | `gpt-4o-mini` | LLM model to use |
| `PDF_API_TEMPLATES_DIR` | path | `./templates` | Root directory for templates |
| `PDF_API_LOG_LEVEL` | string | `INFO` | Logging level (INFO, DEBUG, WARNING, ERROR) |
| `PDF_API_LOG_JSON` | bool | `false` | Emit JSON logs (true) or human-readable (false) |
| `PDF_API_DEBUG_BOXES` | bool | `false` | Draw debug bounding boxes on filled PDFs |
| `PDF_API_IGNORE_TEMPLATE_HASH` | bool | `false` | Skip PDF hash validation (dev only) |
| `PDF_API_CORS_ORIGINS` | list | `["*"]` | Allowed CORS origins (restrict in production) |
| `MRZ_DEBUG` | string | `0` | Enable MRZ OCR debug output (set to `1`) |

---

## Troubleshooting

### Tesseract Not Found
```
pytesseract.TesseractNotFoundError: tesseract is not installed or it's not in your PATH.
```
**Fix**: Install Tesseract (see "System Requirements" section) and verify:
```bash
# Windows
"C:\Program Files\Tesseract-OCR\tesseract.exe" --version

# macOS/Linux
tesseract --version
```

### OpenAI API Errors
```
openai.AuthenticationError: Error code: 401 – Invalid API key provided.
```
**Fix**: Check `PDF_API_OPENAI_API_KEY` in `.env`. Regenerate key from OpenAI dashboard if needed.

### Session Not Found
```
{"detail": "Session 'xyz' not found or expired. Re-upload documents."}
```
**Fix**: Sessions are lost on server restart (MVP limitation). Re-run `/process` to create a new session.

### File Too Large
```
{"detail": "File 'X' exceeds the 50 MB limit (75 MB uploaded)."}
```
**Fix**: Reduce file size or increase `PDF_API_MAX_UPLOAD_BYTES` in `.env`.

### Template Hash Mismatch
```
{"detail": "Template PDF hash does not match stored hash. PDF may have been corrupted or modified."}
```
**Fix**: Either regenerate `template_hash.txt` with the new PDF, or set `PDF_API_IGNORE_TEMPLATE_HASH=true` (dev only).

---

## Development & Testing

### Run Tests
```bash
pytest tests/ -v
```

### Type Checking (mypy)
```bash
mypy src/ api/ --strict
```

### Linting & Formatting
```bash
ruff check src/ api/
black src/ api/
```

### Pre-commit Hooks
Hooks are configured in `pyproject.toml`:
```bash
pre-commit run --all-files
```

---

## Future Roadmap

- [ ] Redis session backend (multi-worker deployment)
- [ ] OCR-based automatic field discovery (no manual coordinate entry)
- [ ] Image/photo placement in PDFs
- [ ] Database-backed template versioning
- [ ] Batch job monitoring UI
- [ ] Admin dashboard for template management
- [ ] Email delivery of filled PDFs
- [ ] Webhook notifications on completion

---

## Support

For issues, feature requests, or questions:
- Check **Troubleshooting** section above
- Review **API Docs**: http://localhost:8000/docs
- Check **server logs**: `sudo journalctl -u pdf-filler -f` (on EC2)

---

## License

[Add your license here]
