"""Passport MRZ extraction via FastMRZ.

FastMRZ accepts a PIL Image, detects and parses the Machine Readable Zone,
and returns a structured dict. We wrap it and map the output to PassportData.

FastMRZ result keys (TD3 / TD1 / TD2):
  mrz_type, document_type, country, surname, given_names,
  document_number, check_document_number,
  nationality, date_of_birth, check_date_of_birth, sex,
  expiry_date, check_expiry_date, optional_data,
  check_composite, valid_composite

Install: pip install fastmrz
"""

from __future__ import annotations

from document_pipeline.models import PassportData
from document_pipeline.ocr import pdf_page_to_pil


def extract_passport_mrz(pdf_bytes: bytes) -> PassportData:
    """Extract passport fields from MRZ on the first page of a PDF.

    Raises ValueError if no valid MRZ is detected.
    """
    try:
        from fastmrz import FastMRZ
    except ImportError as exc:
        raise ImportError(
            "fastmrz is not installed. Run: pip install fastmrz"
        ) from exc

    img = pdf_page_to_pil(pdf_bytes, page_index=0)
    mrz = FastMRZ()

    # FastMRZ accepts a numpy array (cv2-style) or file path.
    # Convert PIL → numpy for compatibility.
    import numpy as np

    result: dict = mrz.get_details(np.array(img), input_type="numpy")

    if not result or result.get("status") == "FAILURE":
        msg = result.get("status_message", "No valid MRZ detected") if result else "No valid MRZ detected"
        raise ValueError(
            f"FastMRZ: {msg}. "
            "Ensure the image is clear and the MRZ strip is visible."
        )

    return _map_mrz_result(result)


def _map_mrz_result(r: dict) -> PassportData:
    """Map raw FastMRZ dict to PassportData model.

    FastMRZ key reference (actual keys from _parse_mrz):
      surname, given_name, document_number, nationality_code,
      birth_date (YYYY-MM-DD), expiry_date (YYYY-MM-DD),
      issuer_code, sex, document_code, mrz_type
    """
    surname = (r.get("surname") or "").replace("<", " ").strip().title()
    given_names = (r.get("given_name") or "").replace("<", " ").strip().title()

    return PassportData(
        surname=surname,
        given_names=given_names,
        document_number=(r.get("document_number") or "").strip(),
        nationality=_iso3_to_country(r.get("nationality_code", "")),
        date_of_birth=r.get("birth_date", ""),
        expiry_date=r.get("expiry_date", ""),
        issuing_country=_iso3_to_country(r.get("issuer_code", "")),
        sex=_normalise_sex(r.get("sex", "")),
        document_type=(r.get("document_code") or "P").strip(),
    )


def _normalise_sex(raw: str) -> str:
    raw = raw.strip().upper()
    return "Male" if raw in ("M",) else "Female" if raw in ("F",) else raw


# ISO 3166-1 alpha-3 → country name (partial list covering common passport issuers)
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
}


def _iso3_to_country(code: str) -> str:
    code = code.strip().upper()
    return _ISO3_MAP.get(code, code)
