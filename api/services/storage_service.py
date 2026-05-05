"""Disk I/O for template assets.

Layout on disk:
    templates/
        <template_id>/
            template.pdf
            fields_config.json
            template_metadata.json   (optional)
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

from fastapi import HTTPException

from api.core.logging import get_logger
from pdf_filler.exceptions import CoordinateMapError, TemplateNotFoundError
from pdf_filler.validators import load_template_metadata

_log = get_logger("api.storage")

_PDF_NAME = "template.pdf"
_MAP_NAME = "fields_config.json"
_META_NAME = "template_metadata.json"


def template_dir(templates_root: Path, template_id: str) -> Path:
    return templates_root / template_id


def pdf_path(templates_root: Path, template_id: str) -> Path:
    return template_dir(templates_root, template_id) / _PDF_NAME


def map_path(templates_root: Path, template_id: str) -> Path:
    return template_dir(templates_root, template_id) / _MAP_NAME


def meta_path(templates_root: Path, template_id: str) -> Path:
    return template_dir(templates_root, template_id) / _META_NAME


# --------------------------------------------------------------------------- #
# Read helpers                                                                 #
# --------------------------------------------------------------------------- #


def list_template_ids(templates_root: Path) -> list[str]:
    if not templates_root.exists():
        return []
    return sorted(
        d.name
        for d in templates_root.iterdir()
        if d.is_dir() and not d.name.startswith(".")
    )


def template_exists(templates_root: Path, template_id: str) -> bool:
    return template_dir(templates_root, template_id).is_dir()


def require_template(templates_root: Path, template_id: str) -> Path:
    """Return the template directory or raise 404."""
    tdir = template_dir(templates_root, template_id)
    if not tdir.is_dir():
        raise HTTPException(status_code=404, detail=f"Template '{template_id}' not found.")
    return tdir


def require_pdf(templates_root: Path, template_id: str) -> Path:
    p = pdf_path(templates_root, template_id)
    if not p.exists():
        raise TemplateNotFoundError(
            f"Template PDF missing for '{template_id}'. Contact admin."
        )
    return p


def require_map(templates_root: Path, template_id: str) -> Path:
    p = map_path(templates_root, template_id)
    if not p.exists():
        raise CoordinateMapError(
            f"Fields config missing for '{template_id}'. Contact admin."
        )
    return p


def load_raw_map(templates_root: Path, template_id: str) -> dict:  # type: ignore[type-arg]
    """Load fields_config.json as a plain dict (no Pydantic validation)."""
    p = require_map(templates_root, template_id)
    return json.loads(p.read_text(encoding="utf-8"))


def load_metadata_safe(templates_root: Path, template_id: str) -> object:
    """Load metadata if present; return None if missing (metadata is optional)."""
    p = meta_path(templates_root, template_id)
    if not p.exists():
        return None
    try:
        return load_template_metadata(p)
    except Exception as exc:  # noqa: BLE001
        _log.warning("Could not load metadata for '%s': %s", template_id, exc)
        return None


# --------------------------------------------------------------------------- #
# Write helpers (admin)                                                        #
# --------------------------------------------------------------------------- #


def save_template_files(
    templates_root: Path,
    template_id: str,
    *,
    pdf_bytes: bytes | None,
    map_bytes: bytes,
    meta_bytes: bytes | None,
) -> list[str]:
    """Persist uploaded files; return list of saved file names."""
    tdir = template_dir(templates_root, template_id)
    tdir.mkdir(parents=True, exist_ok=True)

    saved: list[str] = []

    if pdf_bytes is not None:
        (tdir / _PDF_NAME).write_bytes(pdf_bytes)
        saved.append(_PDF_NAME)
        _log.info("Saved PDF for template '%s' (%d bytes).", template_id, len(pdf_bytes))

    (tdir / _MAP_NAME).write_bytes(map_bytes)
    saved.append(_MAP_NAME)
    _log.info("Saved fields config for template '%s'.", template_id)

    if meta_bytes is not None:
        (tdir / _META_NAME).write_bytes(meta_bytes)
        saved.append(_META_NAME)
        _log.info("Saved metadata for template '%s'.", template_id)

    return saved


def delete_template(templates_root: Path, template_id: str) -> None:
    tdir = template_dir(templates_root, template_id)
    if not tdir.is_dir():
        raise HTTPException(status_code=404, detail=f"Template '{template_id}' not found.")
    shutil.rmtree(tdir)
    _log.info("Deleted template '%s'.", template_id)
