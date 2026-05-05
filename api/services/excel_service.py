"""Parse an uploaded Excel file into a list of nested data dicts.

Column header convention
------------------------
Headers must match the ``source`` dotted paths declared in the template's
coordinate map — e.g. ``applicant.surname``, ``travel.purpose.tourism``.

The parser reconstructs the nested dict structure that PdfFiller expects:

    applicant.surname  → data["applicant"]["surname"]
    travel.purpose.tourism → data["travel"]["purpose"]["tourism"]

Boolean columns (checkbox sources like ``travel.purpose.tourism``) accept:
  - Excel TRUE/FALSE booleans
  - Strings: "true"/"false", "yes"/"no", "1"/"0" (case-insensitive)
  - Numeric: 1 / 0

Empty cells are written as empty string "".
"""

from __future__ import annotations

from typing import Any

import openpyxl
from fastapi import HTTPException


def _set_nested(data: dict[str, Any], dotted_key: str, value: Any) -> None:
    """Write ``value`` into ``data`` at the path described by ``dotted_key``."""
    parts = dotted_key.split(".")
    node = data
    for part in parts[:-1]:
        node = node.setdefault(part, {})
    node[parts[-1]] = value


def _coerce(value: Any) -> Any:
    """Normalise cell values coming from openpyxl."""
    if value is None:
        return ""
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value
    text = str(value).strip()
    if text.lower() in ("true", "yes", "1"):
        return True
    if text.lower() in ("false", "no", "0"):
        return False
    return text


def parse_excel(file_bytes: bytes) -> list[dict[str, Any]]:
    """Parse an Excel workbook and return one dict per data row.

    Args:
        file_bytes: Raw bytes of the uploaded .xlsx file.

    Returns:
        List of nested dicts, one per non-empty row (header row excluded).

    Raises:
        HTTPException 422: If the file cannot be parsed or has no header row.
    """
    try:
        wb = openpyxl.load_workbook(filename=__import__("io").BytesIO(file_bytes), read_only=True, data_only=True)
    except Exception as exc:
        raise HTTPException(422, f"Could not parse Excel file: {exc}") from exc

    ws = wb.active
    if ws is None:
        raise HTTPException(422, "Excel file has no active sheet.")

    rows = list(ws.iter_rows(values_only=True))
    if not rows:
        raise HTTPException(422, "Excel file is empty.")

    # First row = headers (dotted source paths)
    headers: list[str] = [str(h).strip() if h is not None else "" for h in rows[0]]
    if not any(headers):
        raise HTTPException(422, "Excel header row is empty.")

    # Validate headers are non-empty strings (skip blank columns silently)
    valid_cols: list[tuple[int, str]] = [
        (i, h) for i, h in enumerate(headers) if h
    ]
    if not valid_cols:
        raise HTTPException(422, "No valid column headers found in Excel file.")

    records: list[dict[str, Any]] = []
    for row_idx, row in enumerate(rows[1:], start=2):
        # Skip rows that are entirely empty
        if all(cell is None or str(cell).strip() == "" for cell in row):
            continue

        data: dict[str, Any] = {}
        for col_idx, header in valid_cols:
            raw = row[col_idx] if col_idx < len(row) else None
            _set_nested(data, header, _coerce(raw))

        records.append(data)

    if not records:
        raise HTTPException(422, "Excel file has headers but no data rows.")

    return records
