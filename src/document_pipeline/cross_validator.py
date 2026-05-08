"""Cross-document consistency checks.

Returns ValidationWarning objects — not exceptions. Mismatches surface as
warnings that the user resolves in the frontend verification step.

Checks performed:
  1. Name on passport vs Emirates ID (fuzzy — OCR noise)
  2. Date of birth: passport vs Emirates ID (exact)
  3. Nationality: passport vs Emirates ID (exact)
  4. Passport expiry: must be valid today (not expired)
  5. Passport expiry: must be > 6 months from today (Schengen requirement)
  6. Emirates ID expiry: must be valid today
  7. Required Q&A fields must have non-empty answers

Install: pip install thefuzz
"""

from __future__ import annotations

from datetime import date, timedelta

from document_pipeline.models import ExtractionResult, ValidationWarning

# Minimum Schengen validity margin in days (6 months ≈ 180 days)
_SCHENGEN_MARGIN_DAYS = 180


# Fuzzy name match threshold (0–100). Below this = warning.
_NAME_MATCH_THRESHOLD = 75


def cross_validate(result: ExtractionResult) -> list[ValidationWarning]:
    warnings: list[ValidationWarning] = []
    today = date.today()

    if result.passport and result.emirates_id:
        warnings.extend(_check_name_match(result))
        warnings.extend(_check_dob_match(result))
        warnings.extend(_check_nationality_match(result))

    if result.passport:
        warnings.extend(_check_passport_expiry(result.passport, today))

    if result.emirates_id:
        warnings.extend(_check_eid_expiry(result.emirates_id, today))

    if result.qa:
        warnings.extend(_check_required_qa(result.qa))

    return warnings


# --- Individual checks ---

def _check_name_match(result: ExtractionResult) -> list[ValidationWarning]:
    assert result.passport and result.emirates_id
    passport_name = f"{result.passport.given_names} {result.passport.surname}".strip()
    eid_name = result.emirates_id.full_name_en.strip()

    if not _names_match(passport_name, eid_name):
        return [
            ValidationWarning(
                field="name",
                message=(
                    f"Name mismatch: passport '{passport_name}' vs "
                    f"Emirates ID '{eid_name}'. "
                    "Verify which is correct before submitting."
                ),
                source_a="passport",
                source_b="emirates_id",
            )
        ]
    return []


def _check_dob_match(result: ExtractionResult) -> list[ValidationWarning]:
    assert result.passport and result.emirates_id
    p_dob = _parse_iso(result.passport.date_of_birth)
    e_dob = _parse_iso(result.emirates_id.date_of_birth)

    if p_dob and e_dob and p_dob != e_dob:
        return [
            ValidationWarning(
                field="date_of_birth",
                message=(
                    f"Date of birth mismatch: passport '{result.passport.date_of_birth}' vs "
                    f"Emirates ID '{result.emirates_id.date_of_birth}'."
                ),
                source_a="passport",
                source_b="emirates_id",
            )
        ]
    return []


def _check_nationality_match(result: ExtractionResult) -> list[ValidationWarning]:
    assert result.passport and result.emirates_id
    p_nat = result.passport.nationality.strip().lower()
    e_nat = result.emirates_id.nationality.strip().lower()

    if p_nat and e_nat and p_nat != e_nat:
        return [
            ValidationWarning(
                field="nationality",
                message=(
                    f"Nationality mismatch: passport '{result.passport.nationality}' vs "
                    f"Emirates ID '{result.emirates_id.nationality}'."
                ),
                source_a="passport",
                source_b="emirates_id",
            )
        ]
    return []


def _check_passport_expiry(passport: object, today: date) -> list[ValidationWarning]:
    from document_pipeline.models import PassportData

    assert isinstance(passport, PassportData)
    expiry = _parse_iso(passport.expiry_date)
    if not expiry:
        return [
            ValidationWarning(
                field="passport_valid_until",
                message="Could not parse passport expiry date. Verify manually.",
                source_a="passport",
                source_b="",
            )
        ]

    warnings: list[ValidationWarning] = []
    if expiry <= today:
        warnings.append(
            ValidationWarning(
                field="passport_valid_until",
                message=f"Passport expired on {passport.expiry_date}.",
                source_a="passport",
                source_b="",
            )
        )
    elif expiry < today + timedelta(days=_SCHENGEN_MARGIN_DAYS):
        warnings.append(
            ValidationWarning(
                field="passport_valid_until",
                message=(
                    f"Passport expires on {passport.expiry_date} — less than 6 months "
                    "from today. Schengen applications require at least 6 months validity."
                ),
                source_a="passport",
                source_b="",
            )
        )
    return warnings


def _check_eid_expiry(emirates_id: object, today: date) -> list[ValidationWarning]:
    from document_pipeline.models import EmiratesIdData

    assert isinstance(emirates_id, EmiratesIdData)
    expiry = _parse_iso(emirates_id.expiry_date)
    if not expiry:
        return [
            ValidationWarning(
                field="residence_permit_valid_until",
                message="Could not parse Emirates ID expiry date. Verify manually.",
                source_a="emirates_id",
                source_b="",
            )
        ]

    if expiry <= today:
        return [
            ValidationWarning(
                field="residence_permit_valid_until",
                message=f"Emirates ID expired on {emirates_id.expiry_date}.",
                source_a="emirates_id",
                source_b="",
            )
        ]
    return []


def _check_required_qa(qa: object) -> list[ValidationWarning]:
    from document_pipeline.models import QAData

    assert isinstance(qa, QAData)
    if not qa.raw_answers:
        return [
            ValidationWarning(
                field="qa_document",
                message="No Q&A answers could be extracted from the uploaded document.",
                source_a="qa_document",
                source_b="",
            )
        ]
    return []


# --- Helpers ---

def _names_match(a: str, b: str) -> bool:
    """Fuzzy name comparison using thefuzz. Falls back to startswith if not installed."""
    try:
        from thefuzz import fuzz  # type: ignore[import-untyped]

        score = fuzz.token_sort_ratio(a.lower(), b.lower())
        return score >= _NAME_MATCH_THRESHOLD
    except ImportError:
        # Graceful degradation — substring check
        a_l, b_l = a.lower(), b.lower()
        return a_l in b_l or b_l in a_l or a_l == b_l


def _parse_iso(date_str: str) -> date | None:
    """Parse ISO 8601 date string YYYY-MM-DD → date, or None on failure."""
    try:
        return date.fromisoformat(date_str.strip())
    except (ValueError, AttributeError):
        return None
