"""Passport MRZ extraction via Tesseract OCR.

Pipeline:
  PDF page -> high-DPI render -> MRZ-strip crop -> preprocess -> Tesseract (MRZ config)
  -> line filter -> field parse -> PassportData

ICAO 9303 MRZ formats (renamed for readability):
  - PASSPORT_BOOK (TD3): 2 x 44 chars   <- primary target
  - TRAVEL_DOC    (TD2): 2 x 36 chars
  - ID_CARD       (TD1): 3 x 30 chars

Tesseract is invoked with PSM 6 (uniform block of text), OEM 3 (default), and a
character whitelist of A-Z0-9< — the only legal MRZ characters per ICAO 9303.
This dramatically reduces substitution errors (e.g. avoiding lowercase letters,
punctuation, and "smart" quotes).

Install Tesseract: https://github.com/UB-Mannheim/tesseract/wiki
"""

from __future__ import annotations

import os
import re

import fitz  # PyMuPDF
from PIL import Image, ImageOps

from document_pipeline.models import PassportData
from document_pipeline.ocr import _import_pytesseract, pdf_page_to_pil

# --- MRZ format names (ICAO 9303 calls these TD1/TD2/TD3) ---
MRZ_PASSPORT_BOOK = "PASSPORT_BOOK"  # ICAO TD3
MRZ_TRAVEL_DOC = "TRAVEL_DOC"        # ICAO TD2
MRZ_ID_CARD = "ID_CARD"              # ICAO TD1

# --- Tesseract configuration ---

# MRZ strip uses a fixed-width font (OCR-B). Restrict the character set so
# Tesseract cannot output characters that don't exist in valid MRZ.
_MRZ_CHARS = "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789<"
# OEM 3 (default) keeps the whitelist effective on Tesseract 5 builds where
# pure LSTM silently ignores tessedit_char_whitelist.
_TESS_CONFIG_PRIMARY = (
    f"--oem 3 --psm 6 -c tessedit_char_whitelist={_MRZ_CHARS} "
    "-c load_system_dawg=0 -c load_freq_dawg=0"
)
_TESS_CONFIG_FALLBACKS = [
    f"--oem 3 --psm 7 -c tessedit_char_whitelist={_MRZ_CHARS}",
    f"--oem 3 --psm 11 -c tessedit_char_whitelist={_MRZ_CHARS}",
    "--oem 3 --psm 6",  # last resort: no whitelist, accept anything
]


def extract_passport_mrz(pdf_bytes: bytes) -> PassportData:
    """Extract passport fields from the MRZ on a passport PDF.

    Tries each page until a valid MRZ is found (passport scans sometimes
    place the bio-data on page 2). Raises ValueError if none match.
    """
    pytesseract = _import_pytesseract()
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")

    last_err: str | None = None
    for page_index in range(len(doc)):
        try:
            img = pdf_page_to_pil(pdf_bytes, page_index=page_index)
            mrz_data = _ocr_and_parse(img, pytesseract)
            if mrz_data:
                return _map_mrz_result(mrz_data)
        except ValueError as exc:
            last_err = str(exc)
            continue

    raise ValueError(
        f"No valid MRZ detected in any page of the PDF. {last_err or ''} "
        "Ensure the passport bio-data page is included and the MRZ strip is legible."
    )


def _ocr_and_parse(img: Image.Image, pytesseract) -> dict | None:  # type: ignore[no-untyped-def]
    """OCR the image with several configs and parse the MRZ.

    Tries a matrix of (image variant) x (Tesseract config) until something
    parses. Real passport scans vary wildly in DPI, contrast, and where the
    MRZ sits in the page — one config is never enough.

    Set MRZ_DEBUG=1 in the environment to print every OCR attempt.
    """
    debug = os.environ.get("MRZ_DEBUG") == "1"
    image_variants = [
        ("strip", _preprocess(_crop_mrz_strip(img))),
        ("full", _preprocess(img)),
        ("strip_bin", _preprocess_strong(_crop_mrz_strip(img))),
    ]
    configs = [
        ("primary", _TESS_CONFIG_PRIMARY),
        *[(f"fallback{i}", c) for i, c in enumerate(_TESS_CONFIG_FALLBACKS)],
    ]

    for variant_name, prepped in image_variants:
        for config_name, config in configs:
            text = pytesseract.image_to_string(prepped, config=config)
            if debug:
                print(f"--- MRZ_DEBUG variant={variant_name} config={config_name} ---")
                print(text)
                print("--- END ---")
            parsed = _parse_mrz(text)
            if parsed:
                return parsed
    return None


def _crop_mrz_strip(img: Image.Image) -> Image.Image:
    """Crop the bottom ~30 % of the image — where the MRZ sits on a passport page."""
    w, h = img.size
    return img.crop((0, int(h * 0.70), w, h))


def _preprocess(img: Image.Image) -> Image.Image:
    """Greyscale + auto-contrast for better OCR on scanned passports."""
    grey = ImageOps.grayscale(img)
    return ImageOps.autocontrast(grey, cutoff=2)


def _preprocess_strong(img: Image.Image) -> Image.Image:
    """Aggressive preprocessing: greyscale, autocontrast, then binarise."""
    grey = ImageOps.grayscale(img)
    contrasted = ImageOps.autocontrast(grey, cutoff=4)
    return contrasted.point(lambda px: 255 if px > 140 else 0, mode="L")


# --- MRZ parsing ---

_MRZ_ONLY_RE = re.compile(r"[A-Z0-9<]")


def _parse_mrz(text: str) -> dict | None:
    """Locate and parse an MRZ block from raw OCR text."""
    candidates: list[str] = []
    for raw in text.splitlines():
        cleaned = _line_to_mrz_chars(raw)
        if len(cleaned) >= 25:
            candidates.append(cleaned)

    if len(candidates) < 2:
        joined = _line_to_mrz_chars(text.replace("\n", ""))
        candidates = _split_joined_mrz(joined)

    if len(candidates) < 2:
        return None

    # Passport book (2 lines of 44) — most common case.
    passport_lines = [line for line in candidates if 40 <= len(line) <= 48]
    if len(passport_lines) >= 2:
        # 'P' is the document code for passport books.
        p_line = next(
            (i for i, line in enumerate(passport_lines) if line.startswith("P")), None
        )
        if p_line is not None and p_line + 1 < len(passport_lines):
            return _parse_passport_book(
                _pad(passport_lines[p_line], 44),
                _pad(passport_lines[p_line + 1], 44),
            )
        return _parse_passport_book(
            _pad(passport_lines[0], 44), _pad(passport_lines[1], 44)
        )

    # Travel document (2 lines of 36)
    travel_doc_lines = [line for line in candidates if 33 <= len(line) <= 39]
    if len(travel_doc_lines) >= 2:
        return _parse_travel_doc(
            _pad(travel_doc_lines[0], 36), _pad(travel_doc_lines[1], 36)
        )

    # ID card (3 lines of 30)
    id_card_lines = [line for line in candidates if 27 <= len(line) <= 33]
    if len(id_card_lines) >= 3:
        return _parse_id_card(
            _pad(id_card_lines[0], 30),
            _pad(id_card_lines[1], 30),
            _pad(id_card_lines[2], 30),
        )

    # Fallback: assume passport book from the first two MRZ-ish lines.
    return _parse_passport_book(_pad(candidates[0], 44), _pad(candidates[1], 44))


def _line_to_mrz_chars(line: str) -> str:
    """Reduce a raw OCR line to MRZ-legal characters only."""
    line = _normalize_mrz_chars(line)
    return "".join(c for c in line if _MRZ_ONLY_RE.match(c))


def _split_joined_mrz(joined: str) -> list[str]:
    """Try to split a single concatenated MRZ string back into 2-3 lines.

    A passport-book MRZ has total length 88; travel-doc 72; ID-card 90.
    Tolerates +/-4 chars of OCR drift.
    """
    n = len(joined)
    if joined.startswith("P") and 84 <= n <= 92:
        return [joined[:44], joined[44:88]]
    if 86 <= n <= 92:
        return [joined[i:i + 30] for i in (0, 30, 60)]
    if 70 <= n <= 74:
        return [joined[:36], joined[36:72]]
    return []


def _pad(line: str, length: int) -> str:
    """Right-pad with '<' to the expected MRZ length so slice indices are safe."""
    return line.ljust(length, "<")[:length]


def _normalize_mrz_chars(line: str) -> str:
    """Reverse common Tesseract substitutions before parsing."""
    if not line:
        return line
    line = line.upper()
    return (
        line.replace("«", "<")
            .replace("»", "<")
            .replace("“", "<")
            .replace("”", "<")
            .replace("—", "<")
            .replace("–", "<")
    )


# --- Per-format parsers ---

def _parse_passport_book(line1: str, line2: str) -> dict:
    """ICAO 9303 TD3 (passport book) — 2 lines x 44 chars.

    Line 1:
      [0]      P (document code)
      [1]      passport-type sub-code (often <)
      [2:5]    issuing country (ISO 3166 alpha-3)
      [5:44]   surname << given_names (filled with <)

    Line 2:
      [0:9]    document number
      [9]      check digit for document number
      [10:13]  nationality
      [13:19]  birth date YYMMDD
      [19]     check digit for birth date
      [20]     sex M/F/<
      [21:27]  expiry date YYMMDD
      [27]     check digit for expiry date
      [28:42]  personal number
      [42]     check digit for personal number
      [43]     composite check digit
    """
    name_block = line1[5:44]
    surname, given = _split_name(name_block)
    return {
        "document_code": line1[0],
        "issuer_code": _strip_filler(line1[2:5]),
        "surname": surname,
        "given_name": given,
        "document_number": _clean_doc_number(line2[0:9]),
        "nationality_code": _strip_filler(line2[10:13]),
        "birth_date": _format_date(line2[13:19]),
        "sex": line2[20],
        "expiry_date": _format_date(line2[21:27]),
        "mrz_type": MRZ_PASSPORT_BOOK,
    }


def _parse_travel_doc(line1: str, line2: str) -> dict:
    """ICAO 9303 TD2 (travel document) — 2 lines x 36 chars."""
    name_block = line1[5:36]
    surname, given = _split_name(name_block)
    return {
        "document_code": line1[0],
        "issuer_code": _strip_filler(line1[2:5]),
        "surname": surname,
        "given_name": given,
        "document_number": _clean_doc_number(line2[0:9]),
        "nationality_code": _strip_filler(line2[10:13]),
        "birth_date": _format_date(line2[13:19]),
        "sex": line2[20],
        "expiry_date": _format_date(line2[21:27]),
        "mrz_type": MRZ_TRAVEL_DOC,
    }


def _parse_id_card(line1: str, line2: str, line3: str) -> dict:
    """ICAO 9303 TD1 (ID card) — 3 lines x 30 chars.

    Line 1: [0:2] doc code, [2:5] issuer, [5:14] doc no, [14] check, [15:30] optional
    Line 2: [0:6] DOB, [6] check, [7] sex, [8:14] expiry, [14] check, [15:18] nationality
    Line 3: surname << given (full 30 chars)
    """
    surname, given = _split_name(line3)
    return {
        "document_code": line1[0:2].rstrip("<"),
        "issuer_code": _strip_filler(line1[2:5]),
        "surname": surname,
        "given_name": given,
        "document_number": _clean_doc_number(line1[5:14]),
        "nationality_code": _strip_filler(line2[15:18]),
        "birth_date": _format_date(line2[0:6]),
        "sex": line2[7],
        "expiry_date": _format_date(line2[8:14]),
        "mrz_type": MRZ_ID_CARD,
    }


# --- Field cleanup ---

def _split_name(block: str) -> tuple[str, str]:
    """Split MRZ name block (SURNAME<<GIVEN<NAMES) into (surname, given)."""
    if "<<" in block:
        surname, _, given = block.partition("<<")
    else:
        surname, given = block, ""
    return _clean_name_part(surname), _clean_name_part(given)


def _clean_name_part(part: str) -> str:
    """'<' -> space; collapse whitespace; trim trailing fill."""
    return re.sub(r"\s+", " ", part.replace("<", " ")).strip()


def _strip_filler(s: str) -> str:
    """Remove '<' fill characters from a fixed-width MRZ field."""
    return s.replace("<", "").strip()


def _clean_doc_number(s: str) -> str:
    return s.replace("<", "").strip()


def _format_date(date_str: str) -> str:
    """YYMMDD -> YYYY-MM-DD with century inference (<= 50 -> 20xx else 19xx)."""
    cleaned = re.sub(r"[^0-9]", "", date_str)
    if len(cleaned) != 6:
        return ""
    yy, mm, dd = cleaned[:2], cleaned[2:4], cleaned[4:6]
    century = "20" if int(yy) <= 50 else "19"
    iso = f"{century}{yy}-{mm}-{dd}"
    if not (1 <= int(mm) <= 12 and 1 <= int(dd) <= 31):
        return ""
    return iso


# --- PassportData mapping ---

def _map_mrz_result(r: dict) -> PassportData:
    return PassportData(
        surname=_title_name(r.get("surname", "")),
        given_names=_title_name(r.get("given_name", "")),
        document_number=(r.get("document_number") or "").strip(),
        nationality=_iso3_to_country(r.get("nationality_code", "")),
        date_of_birth=r.get("birth_date", ""),
        expiry_date=r.get("expiry_date", ""),
        issuing_country=_iso3_to_country(r.get("issuer_code", "")),
        sex=_normalise_sex(r.get("sex", "")),
        document_type=_map_document_type(r.get("document_code", "")),
    )


def _map_document_type(code: str) -> str:
    """Map ICAO 9303 document codes to human-readable names."""
    code = (code or "").strip().upper()
    mapping = {
        "P": "Passport",
        "PP": "Passport",
        "PT": "Passport",
        "V": "Visa",
        "I": "ID Card",
        "ID": "ID Card",
        "AC": "Crew Member Certificate",
    }
    return mapping.get(code, "Passport")


def _title_name(name: str) -> str:
    """Title-case a name, preserving hyphenated parts."""
    if not name:
        return ""
    return " ".join(
        "-".join(w.capitalize() for w in part.split("-"))
        for part in name.split()
    )


def _normalise_sex(raw: str) -> str:
    raw = (raw or "").strip().upper()
    if raw == "M":
        return "Male"
    if raw == "F":
        return "Female"
    return ""


# ISO 3166-1 alpha-3 -> country name (common passport issuers)
_ISO3_MAP: dict[str, str] = {
    "ARE": "United Arab Emirates",
    "USA": "United States of America",
    "GBR": "United Kingdom",
    "FRA": "France",
    "DEU": "Germany",
    "IND": "India",
    "PAK": "Pakistan",
    "BGD": "Bangladesh",
    "PHL": "Philippines",
    "EGY": "Egypt",
    "JOR": "Jordan",
    "LBN": "Lebanon",
    "SAU": "Saudi Arabia",
    "KWT": "Kuwait",
    "QAT": "Qatar",
    "BHR": "Bahrain",
    "OMN": "Oman",
    "IRN": "Iran",
    "IRQ": "Iraq",
    "SYR": "Syria",
    "MAR": "Morocco",
    "TUN": "Tunisia",
    "DZA": "Algeria",
    "NGA": "Nigeria",
    "KEN": "Kenya",
    "ETH": "Ethiopia",
    "ZAF": "South Africa",
    "RUS": "Russia",
    "CHN": "China",
    "CAN": "Canada",
    "AUS": "Australia",
    "NZL": "New Zealand",
    "TUR": "Turkey",
    "UKR": "Ukraine",
    "POL": "Poland",
    "ITA": "Italy",
    "ESP": "Spain",
    "PRT": "Portugal",
    "NLD": "Netherlands",
    "BEL": "Belgium",
    "CHE": "Switzerland",
    "AUT": "Austria",
    "SWE": "Sweden",
    "NOR": "Norway",
    "DNK": "Denmark",
    "FIN": "Finland",
    "GRC": "Greece",
    "CZE": "Czech Republic",
    "HUN": "Hungary",
    "ROU": "Romania",
    "BGR": "Bulgaria",
    "HRV": "Croatia",
    "SRB": "Serbia",
    "SVK": "Slovakia",
    "SVN": "Slovenia",
    "LTU": "Lithuania",
    "LVA": "Latvia",
    "EST": "Estonia",
    "LUX": "Luxembourg",
    "MLT": "Malta",
    "CYP": "Cyprus",
    "ISL": "Iceland",
    "LIE": "Liechtenstein",
    "MCO": "Monaco",
    "AND": "Andorra",
    "SMR": "San Marino",
    "VAT": "Vatican City",
    "JPN": "Japan",
    "KOR": "South Korea",
    "IDN": "Indonesia",
    "MYS": "Malaysia",
    "SGP": "Singapore",
    "THA": "Thailand",
    "VNM": "Vietnam",
    "LKA": "Sri Lanka",
    "NPL": "Nepal",
    "AFG": "Afghanistan",
    "MEX": "Mexico",
    "BRA": "Brazil",
    "ARG": "Argentina",
    "COL": "Colombia",
    "CHL": "Chile",
    "PER": "Peru",
    "VEN": "Venezuela",
    "IRL": "Ireland",
    "ISR": "Israel",
    "PSE": "Palestine",
    "YEM": "Yemen",
    "SDN": "Sudan",
    "SOM": "Somalia",
}


def _iso3_to_country(code: str) -> str:
    code = (code or "").strip().upper()
    return _ISO3_MAP.get(code, code)
