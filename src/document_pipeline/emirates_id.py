"""Emirates ID field extraction via Tesseract OCR + regex.

Emirates IDs are scanned PNG images inside a PDF. We render the PDF,
OCR it with Tesseract (English + Arabic via the "ara" traineddata),
then apply regex patterns to pull structured fields from the OCR output.

The Arabic-name field requires the Tesseract Arabic language pack. Install
it via the UB-Mannheim installer or by dropping `ara.traineddata` into the
Tesseract `tessdata` directory.

Field layout on the English side of an Emirates ID card:
  - ID Number  : 784-YYYY-XXXXXXX-X
  - Name       : line labelled "Name:" or immediately after it
  - Nationality: line labelled "Nationality:"
  - Date of Birth: labelled "Date of Birth:"
  - Expiry Date: labelled "Expiry Date:" or "Date of Expiry:"
  - Sex / Gender: "M" / "F" or "Male" / "Female"

Regex constants are module-level so they can be tuned against real samples
without touching the parsing logic.
"""

from __future__ import annotations

import re

from dateutil import parser as date_parser

from document_pipeline.models import EmiratesIdData
from document_pipeline.ocr import extract_text_from_pdf

# --- Regex patterns (tune these against real OCR output) ---

_RE_ID_NUMBER = re.compile(r"\b784[-\s]?\d{4}[-\s]?\d{7}[-\s]?\d\b")

_RE_NAME = re.compile(
    r"(?:Name|Full\s*Name)\s*[:\-]?\s*([A-Z][A-Za-z\-'\. ]+?)\s*(?:\n|$)",
    re.IGNORECASE,
)

_RE_NATIONALITY = re.compile(
    r"Nationality\s*[:\-]?\s*([A-Za-z][A-Za-z\s\-]+?)\s*(?:\n|$)",
    re.IGNORECASE,
)

_DATE_VALUE = r"(\d{1,2}[\/\-\.]\d{1,2}[\/\-\.]\d{2,4})"

# UAE OCR layout varies — date can appear before OR after its label.
# Pattern A: "Date of Birth: 01/01/1990"  (label then value, same line)
# Pattern B: "Date of Birth\n01/01/1990"  (label then value, next line)
# Pattern C: "01/01/1990\nDate of Birth"  (value then label — seen in practice)

_RE_DOB_AFTER = re.compile(
    r"(?:Date\s*of\s*Birth|D\.O\.B|DOB)\s*[:\-]?\s*" + _DATE_VALUE,
    re.IGNORECASE,
)
_RE_DOB_NEXT_LINE = re.compile(
    r"(?:Date\s*of\s*Birth|D\.O\.B|DOB)\s*[:\-]?\s*\n\s*" + _DATE_VALUE,
    re.IGNORECASE,
)
_RE_DOB_BEFORE = re.compile(
    _DATE_VALUE + r"\s*\n\s*(?:Date\s*of\s*Birth|D\.O\.B|DOB)\b",
    re.IGNORECASE,
)

_RE_EXPIRY_AFTER = re.compile(
    r"(?:Expiry\s*Date|Date\s*of\s*Expiry|Expiry)\s*[:\-]?\s*" + _DATE_VALUE,
    re.IGNORECASE,
)
_RE_EXPIRY_NEXT_LINE = re.compile(
    r"(?:Expiry\s*Date|Date\s*of\s*Expiry|Expiry)\s*[:\-]?\s*\n\s*" + _DATE_VALUE,
    re.IGNORECASE,
)
_RE_EXPIRY_SKIP = re.compile(
    r"(?:Expiry\s*Date|Date\s*of\s*Expiry)[^\n]*\n(?:[^\n]*\n){0,3}\s*" + _DATE_VALUE,
    re.IGNORECASE,
)

_RE_ISSUE_AFTER = re.compile(
    r"(?:Issuing\s*Date|Issue\s*Date|Date\s*of\s*Issue)\s*[:\-\/]?\s*(?:[^\n]*?\s*)?" + _DATE_VALUE,
    re.IGNORECASE,
)
_RE_ISSUE_NEXT_LINE = re.compile(
    r"(?:Issuing\s*Date|Issue\s*Date|Date\s*of\s*Issue)\s*[:\-\/]?[^\n]*\n\s*" + _DATE_VALUE,
    re.IGNORECASE,
)
_RE_ISSUE_BEFORE = re.compile(
    _DATE_VALUE + r"\s*\n\s*(?:Issuing\s*Date|Issue\s*Date|Date\s*of\s*Issue)\b",
    re.IGNORECASE,
)

_RE_GENDER = re.compile(
    r"(?:Sex|Gender)\s*[:\-]?\s*(Male|Female|M|F)\b",
    re.IGNORECASE,
)

# Arabic name block: consecutive Arabic unicode characters on a line
_RE_ARABIC_LINE = re.compile(r"[؀-ۿݐ-ݿ\s]{4,}")


def extract_emirates_id(pdf_bytes: bytes) -> tuple[EmiratesIdData, list[str]]:
    """Extract fields from an Emirates ID PDF using OCR.

    Returns (data, errors). Errors are non-fatal field-extraction failures.
    """
    # PSM 6 (uniform block) reads the bulk of the card; PSM 11 (sparse text)
    # catches small isolated fields like "Sex: F" that PSM 6 silently drops.
    text = extract_text_from_pdf(pdf_bytes, langs=("en", "ar"), psms=(6, 11))
    return parse_emirates_id_text(text)


def parse_emirates_id_text(text: str) -> tuple[EmiratesIdData, list[str]]:
    """Parse OCR text from an Emirates ID card into EmiratesIdData.

    Returns (data, errors). Never raises — missing fields are recorded in errors
    and left as empty strings so the caller can surface them as warnings.
    """
    errors: list[str] = []

    id_number = _safe_extract(_extract_id_number, text, errors)
    full_name_en = _safe_extract(_extract_name, text, errors)
    nationality = _extract_nationality(text)
    dob = _safe_extract_date(
        [_RE_DOB_AFTER, _RE_DOB_NEXT_LINE, _RE_DOB_BEFORE], text, "Date of Birth", errors
    )
    # Try labelled patterns first; suppress per-pattern errors so we can fall
    # back to positional date recovery without polluting the error list.
    label_errors: list[str] = []
    issue_date = _safe_extract_date(
        [_RE_ISSUE_AFTER, _RE_ISSUE_NEXT_LINE, _RE_ISSUE_BEFORE], text, "Issue Date", label_errors
    )
    expiry = _safe_extract_date(
        [_RE_EXPIRY_AFTER, _RE_EXPIRY_NEXT_LINE, _RE_EXPIRY_SKIP], text, "Expiry Date", label_errors
    )

    # Fallback: when OCR mangled the labels, recover issue/expiry by position.
    # Find all dates in the text, drop the DOB, then take earliest=issue,
    # latest=expiry. UAE EIDs always show issue (past) and expiry (future).
    if issue_date is None or not expiry:
        issue_date, expiry = _fallback_dates(text, dob, issue_date, expiry)

    if issue_date is None:
        errors.append("Could not extract 'Issue Date' from Emirates ID OCR output.")
    if not expiry:
        errors.append("Could not extract 'Expiry Date' from Emirates ID OCR output.")
    gender = _extract_gender(text)
    full_name_ar = _extract_arabic_name(text)

    return EmiratesIdData(
        full_name_en=full_name_en or "",
        full_name_ar=full_name_ar,
        id_number=id_number or "",
        nationality=nationality,
        date_of_birth=dob,
        issue_date=issue_date,
        expiry_date=expiry or "",
        gender=gender,
    ), errors


# --- Private helpers ---

def _extract_id_number(text: str) -> str:
    m = _RE_ID_NUMBER.search(text)
    if not m:
        raise ValueError(
            "Could not find Emirates ID number (pattern: 784-YYYY-XXXXXXX-X) in OCR output."
        )
    # Normalise separators to dashes
    raw = re.sub(r"[\s]", "-", m.group())
    return raw


def _extract_name(text: str) -> str:
    m = _RE_NAME.search(text)
    if not m:
        raise ValueError("Could not extract name from Emirates ID OCR output.")
    name = m.group(1).split("\n")[0].strip()
    name = _strip_trailing_noise(name)
    return _title_case_name(name)


def _extract_nationality(text: str) -> str:
    m = _RE_NATIONALITY.search(text)
    if not m:
        return ""
    raw = m.group(1).split("\n")[0].strip()
    # Drop OCR bleed-through (e.g. "TURKEY OE SRS A" -> "TURKEY").
    cleaned = _strip_trailing_noise(raw)
    return cleaned.title()


def _strip_trailing_noise(value: str) -> str:
    """Remove short trailing tokens that look like OCR bleed from adjacent Arabic text.

    Tesseract often reads stray Arabic glyphs as 1-3 letter capitalised tokens
    after a real value. We iteratively trim them off the end while leaving the
    real word intact (which is typically >=4 chars).
    """
    parts = value.split()
    while len(parts) > 1 and len(parts[-1]) <= 3:
        parts.pop()
    return " ".join(parts)


def _safe_extract(fn: object, text: str, errors: list[str]) -> str | None:
    """Call a raising extractor; on ValueError append the message and return None."""
    assert callable(fn)
    try:
        return fn(text)  # type: ignore[operator]
    except ValueError as exc:
        errors.append(str(exc))
        return None


def _safe_extract_date(
    patterns: list[re.Pattern[str]],
    text: str,
    label: str,
    errors: list[str],
) -> str | None:
    """Try each pattern in order; parse the first match as a date.

    Returns ISO date string, or None (with error appended) if nothing matches.
    """
    for pat in patterns:
        m = pat.search(text)
        if m:
            raw = m.group(1).strip()
            try:
                return date_parser.parse(raw, dayfirst=True).strftime("%Y-%m-%d")
            except Exception as exc:
                errors.append(f"Could not parse date '{raw}' for '{label}': {exc}")
                return None
    errors.append(f"Could not extract '{label}' from Emirates ID OCR output.")
    return None


_RE_ANY_DATE = re.compile(r"\b(\d{1,2}[\/\-\.]\d{1,2}[\/\-\.]\d{2,4})\b")


def _fallback_dates(
    text: str,
    dob: str | None,
    issue_date: str | None,
    expiry: str | None,
) -> tuple[str | None, str | None]:
    """Recover issue/expiry by picking the earliest/latest date that isn't DOB.

    Used when label-anchored patterns failed (typical when Arabic noise corrupts
    the labels). UAE EIDs reliably show DOB, issue, and expiry dates — three
    distinct values — so positional ordering is well-defined.
    """
    iso_dates: list[str] = []
    for m in _RE_ANY_DATE.finditer(text):
        try:
            iso = date_parser.parse(m.group(1), dayfirst=True).strftime("%Y-%m-%d")
        except (ValueError, TypeError):
            continue
        if iso != dob and iso not in iso_dates:
            iso_dates.append(iso)

    if not iso_dates:
        return issue_date, expiry

    iso_dates.sort()
    if issue_date is None:
        issue_date = iso_dates[0]
    if not expiry and len(iso_dates) >= 2:
        expiry = iso_dates[-1]
    elif not expiry:
        # Only one non-DOB date — assume it's the expiry (issue is sometimes
        # absent on older cards but expiry is always printed).
        expiry = iso_dates[0]
        if issue_date == expiry:
            issue_date = None
    return issue_date, expiry


def _extract_gender(text: str) -> str:
    m = _RE_GENDER.search(text)
    if not m:
        return ""
    raw = m.group(1).strip().upper()
    return "Male" if raw in ("M", "MALE") else "Female"


def _extract_arabic_name(text: str) -> str | None:
    matches = _RE_ARABIC_LINE.findall(text)
    if not matches:
        return None
    # Pick the longest Arabic line as the most likely name
    longest = max(matches, key=len).strip()
    return longest if longest else None


def _title_case_name(name: str) -> str:
    """Title-case a name while preserving compound separators like Al-, Bin-, Bint-."""
    return " ".join(
        part[0].upper() + part[1:].lower() if part else part
        for part in name.split()
    )
