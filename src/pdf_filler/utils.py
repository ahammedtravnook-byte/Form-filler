"""Pure utility helpers used across the package.

These helpers contain no PDF-specific logic so they're easy to unit-test.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

_MISSING = object()


def resolve_path(data: dict[str, Any], dotted_path: str) -> Any:
    """Resolve a dotted path like ``applicant.surname`` against nested dict data.

    Returns the special sentinel ``MISSING`` if any segment of the path is
    absent. Distinguishes between "key not present" (MISSING) and "key present
    with falsy value" (returns the falsy value). This distinction matters for
    optional fields: an empty string is *present*, but a missing key is not.

    Args:
        data: The root data dict.
        dotted_path: A path like ``"a.b.c"``.

    Returns:
        The resolved value, or :data:`MISSING` if any segment doesn't exist.
    """
    if not dotted_path:
        return _MISSING

    current: Any = data
    for segment in dotted_path.split("."):
        if isinstance(current, dict) and segment in current:
            current = current[segment]
        else:
            return _MISSING
    return current


def is_missing(value: Any) -> bool:
    """Check whether a value is the special MISSING sentinel."""
    return value is _MISSING


# Public alias for the sentinel — callers shouldn't import the underscore name.
MISSING = _MISSING


def is_empty_value(value: Any) -> bool:
    """Return True if value should be treated as "no input provided".

    Treats MISSING, None, and empty/whitespace-only strings as empty. Numeric
    zero and boolean False are *not* empty — they are explicit values.
    """
    if value is _MISSING or value is None:
        return True
    return isinstance(value, str) and value.strip() == ""


def sha256_file(path: Path, chunk_size: int = 1024 * 1024) -> str:
    """Compute the SHA-256 hex digest of a file streamed in chunks."""
    hasher = hashlib.sha256()
    with path.open("rb") as fh:
        while True:
            chunk = fh.read(chunk_size)
            if not chunk:
                break
            hasher.update(chunk)
    return hasher.hexdigest()


def load_json(path: Path) -> Any:
    """Load JSON from a file with a clear error message on parse failure."""
    with path.open("r", encoding="utf-8") as fh:
        try:
            return json.load(fh)
        except json.JSONDecodeError as exc:
            raise ValueError(f"Invalid JSON in {path}: {exc}") from exc


def safe_resolve_output_path(output: Path, allowed_root: Path | None = None) -> Path:
    """Resolve an output path and optionally constrain it to a root directory.

    Prevents accidental writes outside the project tree when ``allowed_root``
    is supplied (defence-in-depth against attacker-controlled output paths).
    """
    resolved = output.expanduser().resolve()
    if allowed_root is not None:
        root = allowed_root.expanduser().resolve()
        try:
            resolved.relative_to(root)
        except ValueError as exc:
            raise ValueError(
                f"Output path {resolved} is outside the allowed root {root}."
            ) from exc
    return resolved
