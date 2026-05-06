# pdf-filler

A production-quality, **coordinate-based** static PDF template filler written in
Python. Stamps text and checkbox marks onto a fixed visual template using a
flat JSON input data file and a JSON fields config.

The first packaged template is the Schengen visa application form (4 pages),
but the engine is template-agnostic.

---

## Why coordinate-based?

Many real-world forms — including the Schengen visa application — are
distributed as **printed/scanned, non-fillable PDFs**. They have no AcroForm
or XFA fields, so libraries that "fill PDFs" by looking up form-field names
can't help.

The only reliable approach is to treat the PDF as a *visual* template and stamp
values at precise coordinates. That's what this project does.

* No PDF form fields are required.
* The original template file is **never modified**.
* The output is a normal, flattened PDF where the values are part of the page
  content.

---

## Features

- Pydantic v2-validated fields config and template metadata.
- Discriminated-union field types: `text`, `multiline_text`, `checkbox`,
  `checkbox_group`, `date`, `image` (placeholder), `signature_text`.
- 1-based page numbers (PyMuPDF uses 0-based internally).
- Text alignment (`left` / `center` / `right`), font size, width, max
  characters.
- Overflow strategies: `error`, `shrink` (default), `truncate`.
- Checkboxes: standalone boolean / option style (`checked_when`), plus
  multi-option `checkbox_group` for sets like Sex, Civil status, Purpose of
  journey, etc. Drawn as `x`, `check`, or `filled_square`.
- **Flat input data** — fields reference values by `data_key` directly
  (e.g. `surname`, `passport_number`).
- Optional vs required fields with clear missing-data errors.
- SHA-256 template hash check against metadata.
- `--debug-boxes` overlay for visual coordinate calibration.
- `make-coordinate-guide` command renders PNGs with a coordinate grid.
- Typer CLI + clean Python API.

---

## Project layout

```
pdf_filler/
├── README.md
├── pyproject.toml
├── requirements.txt
├── .gitignore
├── src/pdf_filler/
│   ├── __init__.py
│   ├── __main__.py
│   ├── cli.py
│   ├── config.py
│   ├── coordinates.py
│   ├── exceptions.py
│   ├── filler.py
│   ├── logging_config.py
│   ├── models.py
│   ├── render_check.py
│   ├── utils.py
│   └── validators.py
├── templates/schengen/
│   ├── fields_config.json
│   └── template_metadata.json    # drop your template.pdf here
├── examples/
│   └── input_client.json
├── output/                       # generated PDFs land here (.gitkeep'd)
└── tests/
    ├── conftest.py
    ├── test_models.py
    ├── test_coordinates.py
    └── test_filler.py
```

> The template PDF (`templates/schengen/template.pdf`) is **not** committed.
> Drop your own copy in.

---

## Installation

Requires **Python 3.11+**.

```powershell
# create a venv
python -m venv .venv
.\.venv\Scripts\Activate.ps1

# install the package + dev tools
pip install -e ".[dev]"
```

Or just the runtime dependencies:

```powershell
pip install -r requirements.txt
```

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

## CLI usage

After installation the `pdf-filler` console script is on `PATH`. You can also
run the module directly via `python -m pdf_filler`.

All commands have **sensible defaults** pointing at the bundled Schengen
template, fields config, and example client data — so the simplest invocation
is just:

```powershell
python -m pdf_filler fill --output output/filled.pdf --overwrite
```

### Fill a template

Explicit form:

```powershell
python -m pdf_filler fill `
  --template templates/schengen/template.pdf `
  --data examples/input_client.json `
  --fields-config templates/schengen/fields_config.json `
  --metadata templates/schengen/template_metadata.json `
  --output output/filled_schengen.pdf
```

Equivalent installed-script form:

```powershell
pdf-filler fill --template ... --data ... --fields-config ... --output ...
```

Useful flags:

| Flag                     | Purpose                                                       |
| ------------------------ | ------------------------------------------------------------- |
| `--metadata <PATH>`      | Optional template metadata (page count + SHA-256 lock).       |
| `--ignore-template-hash` | Don't fail if SHA-256 mismatches the metadata.                |
| `--debug-boxes`          | Draw faint outlines around field areas for calibration.       |
| `--overwrite`            | Overwrite an existing output file.                            |
| `-v / --verbose`         | Enable debug logging.                                         |

> `--coordinates` is accepted as an alias of `--fields-config` for
> back-compatibility with older scripts.

### Inspect a template

```powershell
python -m pdf_filler inspect-template --template templates/schengen/template.pdf --page 1
```

Prints page count, the geometry of the selected page (or all pages), and a
recap of the PyMuPDF coordinate system.

### Render a coordinate guide

```powershell
python -m pdf_filler make-coordinate-guide `
  --template templates/schengen/template.pdf `
  --output output/page_guides/
```

Writes one PNG per page, with a coordinate grid overlaid (`x=…`, `y=…`
labels every 100 pt by default, minor lines every 25 pt). Open these in any
image viewer to read the (x, y) for each field.

Tunables: `--grid-step 25`, `--major-step 100`, `--zoom 2.0`.

### Validate a fields config

```powershell
python -m pdf_filler validate-fields-config --fields-config templates/schengen/fields_config.json
```

Loads the config and prints a JSON summary (field counts by type and page).
Exits non-zero on validation errors and lists every problem.

### Hash a template

```powershell
# Print the template's SHA-256:
python -m pdf_filler hash-template --template templates/schengen/template.pdf

# Or write it directly into the metadata file:
python -m pdf_filler hash-template `
  --template templates/schengen/template.pdf `
  --update-metadata templates/schengen/template_metadata.json
```

---

## JSON input data format

The input data is a **flat** JSON object — each key matches a `data_key` in
the fields config. There is no fixed schema; the fields config decides which
keys matter.

See [`examples/input_client.json`](examples/input_client.json) for a complete
Schengen sample.

```json
{
  "surname": "Al Rashidi",
  "first_name": "Ahmed",
  "date_of_birth": "15-03-1990",
  "place_of_birth": "Dubai",
  "country_of_birth": "UAE",
  "current_nationality": "Emirati",
  "sex": "Male",
  "civil_status": "Married",
  "passport_number": "A12345678",
  "passport_issue_date": "01-01-2020",
  "passport_valid_until": "01-01-2030",
  "home_address": "Villa 12, Al Barsha, Dubai, UAE",
  "email_address": "ahmed.alrashidi@email.com",
  "telephone": "+971 50 123 4567",
  "journey_purpose": "Tourism",
  "main_destination": "France",
  "number_of_entries": "Multiple entries",
  "arrival_date": "01-06-2025",
  "departure_date": "15-06-2025"
}
```

Empty strings, `null`, and missing keys are all treated as "no input
provided". `0` and `false` are treated as explicit values (so a boolean `false`
is valid input for an option-checkbox compared against `false`).

---

## JSON fields config format

Top-level shape:

```json
{
  "form_name": "Schengen Visa Application",
  "pages": [
    {"page_number": 1, "pdf_width": 595.32, "pdf_height": 841.92},
    {"page_number": 2, "pdf_width": 595.32, "pdf_height": 841.92}
  ],
  "fields": { ... }
}
```

Every entry under `fields` has a `data_key` (the input-data key), `page`
(1-based), and either `x` / `y` placement (most types) or an `options` map
(for `checkbox_group`). The `type` key defaults to `"text"` and may be
omitted for plain text fields.

### Field-type reference

#### `text` (default; `type` may be omitted)

```json
{
  "data_key": "surname",
  "page": 1,
  "x": 155, "y": 174,
  "width": 270,
  "height": 12,
  "font": "helv",
  "font_size": 9,
  "align": "left",
  "max_chars": 60,
  "overflow": "shrink",
  "min_font_size": 7,
  "color": [0, 0, 0],
  "required": true,
  "description": "Field 1: Surname (Family name)"
}
```

`width` is the visual bounding-box width; `height` is informational
(the engine adds vertical headroom internally so glyphs always render).

#### `multiline_text`

```json
{
  "type": "multiline_text",
  "data_key": "home_address",
  "page": 2,
  "x": 24, "y": 325,
  "width": 420,
  "font_size": 9,
  "line_height": 11,
  "max_lines": 5,
  "overflow": "shrink",
  "required": true
}
```

`width` is required; `line_height` defaults to `11`.

#### `checkbox`

Standalone boolean checkbox (`checked_when` omitted):

```json
{
  "type": "checkbox",
  "data_key": "agreed_to_terms",
  "page": 1,
  "x": 27, "y": 200,
  "box_size": 8,
  "check_style": "x"
}
```

Option-matching checkbox (`checked_when` matches the data value,
case-insensitive):

```json
{
  "type": "checkbox",
  "data_key": "sex",
  "page": 1,
  "x": 27, "y": 511,
  "box_size": 8,
  "checked_when": "male",
  "check_style": "x"
}
```

`check_style` is one of: `"x"`, `"check"`, `"filled_square"`.

#### `checkbox_group`

A set of mutually-exclusive (or selectable) options sharing one `data_key`.
The data value (or list of values) is matched case-insensitively against the
keys of `options`; matching boxes are checked.

```json
{
  "type": "checkbox_group",
  "data_key": "civil_status",
  "page": 1,
  "description": "Field 9: Civil status",
  "options": {
    "Single":   {"x": 209, "y": 410},
    "Married":  {"x": 271, "y": 410},
    "Divorced": {"x": 272, "y": 432}
  },
  "box_size": 8,
  "check_style": "x"
}
```

Pass a list (e.g. `["Tourism", "Business"]`) to tick more than one option.

#### `date`

```json
{
  "type": "date",
  "data_key": "date_of_birth",
  "page": 1,
  "x": 24, "y": 360,
  "format": "%d-%m-%Y",
  "width": 180,
  "overflow": "shrink",
  "required": true
}
```

`format` is a Python `strftime` string. Strings already in the desired output
format (e.g. `"15-03-1990"`) are passed through verbatim, so you don't have
to convert input dates ahead of time.

#### `signature_text`

Same options as `text`, with a larger default font size — handy for stamping
a typed signature line.

#### `image` (placeholder)

Reserved for future image/photo support. Currently raises
`UnsupportedFieldTypeError` so it can't be silently ignored.

---

## Coordinate system

`pdf-filler` uses PyMuPDF coordinates throughout:

- Origin is the **top-left** corner of each page.
- `x` increases to the **right**.
- `y` increases **downward**.
- Units are **PDF points** (1 inch = 72 pt).
- A4 page ≈ **595 × 842 pt**. US Letter ≈ **612 × 792 pt**.

Use `inspect-template` to confirm a specific template's per-page geometry.

---

## How to create a fields config

1. **Render a coordinate guide.**
   ```powershell
   python -m pdf_filler make-coordinate-guide --template templates/schengen/template.pdf --output output/page_guides/
   ```
2. **Open the PNG** (`output/page_guides/page_01_guide.png` etc.) in any
   image viewer. The grid has labelled major lines.
3. **Locate each field visually** and read its top-left (x, y) off the grid.
4. **Add the entry to `fields_config.json`** with the appropriate `data_key`,
   `page`, `x`, `y`, plus type-specific options (font size, width, etc.). For
   plain text fields you can omit `type` entirely.
5. **Run `fill`** with sample data:
   ```powershell
   python -m pdf_filler fill --output output/test.pdf --overwrite
   ```
6. **Open the output PDF** and check positioning.
7. **Nudge** if needed:
   - increase `x` to move text right
   - decrease `x` to move text left
   - increase `y` to move text down
   - decrease `y` to move text up
8. For checkboxes, pick (x, y) at the **top-left of the printed box**. The
   stamp is drawn inside an `box_size` × `box_size` square anchored there.
9. Once aligned, **commit the fields config together with the template
   version** so they evolve in lockstep.

### Debug boxes

Pass `--debug-boxes` to draw a faint red outline around every field's target
area (including each option box of a `checkbox_group`). Open the resulting
PDF to verify that text rectangles and checkbox target squares land where you
expect.

```powershell
python -m pdf_filler fill --output output/debug.pdf --overwrite --debug-boxes
```

---

## Programmatic API

```python
from pathlib import Path

from pdf_filler import PdfFiller
from pdf_filler.coordinates import load_fields_config
from pdf_filler.validators import load_template_metadata, validate_input_data

template = Path("templates/schengen/template.pdf")
config = load_fields_config(Path("templates/schengen/fields_config.json"))
metadata = load_template_metadata(Path("templates/schengen/template_metadata.json"))
data = validate_input_data(Path("examples/input_client.json"))

filler = PdfFiller(template, config, metadata=metadata)
result = filler.fill(data, Path("output/filled.pdf"), overwrite=True)
print(result.fields_written, result.fields_skipped)
```

The Pydantic models, exceptions, and engine are also re-exported from the
package root. `CoordinateMap` is kept as an alias of `FieldsConfig`, and
`load_coordinate_map` / `summarise_coordinate_map` are kept as aliases of the
`*_fields_config` functions, for back-compat.

---

## Production notes

- **Lock the template by SHA-256.** Run
  `pdf-filler hash-template --template ... --update-metadata templates/schengen/template_metadata.json`
  whenever you adopt a new official version, then check the metadata into
  source control. Filling will refuse to run against a different template
  unless `--ignore-template-hash` is passed.
- **Version your fields config** alongside the template — embassies *do*
  re-issue forms.
- **Validate input data** at the application boundary. The engine itself
  reads keys defensively (missing → skipped if optional, error if required).
- **Flatten output by stamping content directly.** That's already how this
  package works — values are part of the page content stream, not editable
  form fields.
- **Render output for QA.** Keep a folder of golden sample PDFs and diff them
  visually (or pixel-diff via `get_pixmap`) when changing coordinates or the
  engine.
- **Avoid logging PII.** The included logger logs field *names* and outcomes,
  not values. Don't add `logger.info(value)` lines without thinking.
- **Constrain output paths.** Use
  `pdf_filler.utils.safe_resolve_output_path` if accepting paths from
  untrusted callers.

---

## Running the tests

```powershell
pytest -q
```

Tests synthesise a 4-page A4 PDF on the fly, so you can run them without the
real Schengen template.

---

## Roadmap (intentionally not done yet)

- FastAPI wrapper around the engine.
- OCR-based field discovery.
- Image / photo placement (the `image` field type is reserved for this).
- Database-backed batch filling.

These are deliberately out of scope for the current local CLI engine.

---

## License

MIT.
