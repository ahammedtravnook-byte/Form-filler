"""Thin async wrapper around the synchronous PdfFiller engine.

Runs the blocking fill operation in a thread pool so FastAPI's event loop
stays free.
"""

from __future__ import annotations

import asyncio
import io
import zipfile
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from api.core.config import settings
from api.core.logging import get_logger
from api.services import storage_service as store
from pdf_filler.coordinates import load_coordinate_map
from pdf_filler.exceptions import PdfFillerError
from pdf_filler.filler import FillResult, PdfFiller
from pdf_filler.models import CoordinateMap, TemplateMetadata
from pdf_filler.validators import load_template_metadata

_log = get_logger("api.pdf_fill")


# --------------------------------------------------------------------------- #
# Internal helpers                                                             #
# --------------------------------------------------------------------------- #


def _load_filler(
    template_path: Path,
    coord_map_path: Path,
    meta_path: Path | None,
) -> PdfFiller:
    """Build a PdfFiller; coord map and metadata are loaded once and reused."""
    coord_map: CoordinateMap = load_coordinate_map(coord_map_path)
    metadata: TemplateMetadata | None = load_template_metadata(meta_path)
    return PdfFiller(template_path, coord_map, metadata)


def _fill_sync(
    template_path: Path,
    coord_map_path: Path,
    meta_path: Path | None,
    data: dict[str, Any],
    out_path: Path,
) -> FillResult:
    filler = _load_filler(template_path, coord_map_path, meta_path)
    return filler.fill(
        data,
        out_path,
        overwrite=True,
        debug_boxes=settings.debug_boxes,
        ignore_template_hash=settings.ignore_template_hash,
    )


def _fill_many_sync(
    template_path: Path,
    coord_map_path: Path,
    meta_path: Path | None,
    records: list[dict[str, Any]],
    out_dir: Path,
    template_id: str,
) -> list[RecordResult]:
    """Fill all records sequentially in a worker thread; share one PdfFiller."""
    filler = _load_filler(template_path, coord_map_path, meta_path)
    results: list[RecordResult] = []

    for idx, data in enumerate(records):
        # Build a meaningful filename: use surname if available
        surname = _dig(data, "applicant", "surname") or ""
        label = f"{surname}_{idx + 1:03d}" if surname else f"{idx + 1:03d}"
        filename = f"{template_id}_{label}.pdf"
        out_path = out_dir / filename

        try:
            result = filler.fill(
                data,
                out_path,
                overwrite=True,
                debug_boxes=settings.debug_boxes,
                ignore_template_hash=settings.ignore_template_hash,
            )
            results.append(RecordResult(index=idx, filename=filename, result=result, error=None))
            _log.info("Record %d/%d filled → %s", idx + 1, len(records), filename)
        except PdfFillerError as exc:
            _log.warning("Record %d/%d failed: %s", idx + 1, len(records), exc)
            results.append(RecordResult(index=idx, filename=filename, result=None, error=str(exc)))

    return results


def _dig(data: dict[str, Any], *keys: str) -> str:
    """Safely walk nested dict keys; return empty string if missing."""
    node: Any = data
    for k in keys:
        if not isinstance(node, dict):
            return ""
        node = node.get(k, "")
    return str(node) if node else ""


def _build_zip(out_dir: Path, results: list[RecordResult]) -> bytes:
    """Pack all successfully filled PDFs into an in-memory ZIP."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
        for r in results:
            if r.result is not None:
                pdf_path = out_dir / r.filename
                if pdf_path.exists():
                    zf.write(pdf_path, arcname=r.filename)
    return buf.getvalue()


# --------------------------------------------------------------------------- #
# Public result type                                                           #
# --------------------------------------------------------------------------- #


@dataclass
class RecordResult:
    index: int
    filename: str
    result: FillResult | None
    error: str | None

    @property
    def ok(self) -> bool:
        return self.result is not None


@dataclass
class BatchResult:
    zip_bytes: bytes
    total: int
    succeeded: int
    failed: int
    errors: list[dict[str, Any]]  # [{index, filename, error}] for failed records


# --------------------------------------------------------------------------- #
# Public API                                                                   #
# --------------------------------------------------------------------------- #


async def fill_template(
    templates_root: Path,
    template_id: str,
    data: dict[str, Any],
) -> tuple[bytes, FillResult]:
    """Fill a single record; return (pdf_bytes, FillResult)."""
    t_pdf = store.require_pdf(templates_root, template_id)
    t_map = store.require_map(templates_root, template_id)
    t_meta_path = store.meta_path(templates_root, template_id)
    meta_arg = t_meta_path if t_meta_path.exists() else None

    _log.info("Filling template '%s' (%d data keys).", template_id, len(data))

    with tempfile.TemporaryDirectory() as tmpdir:
        out_path = Path(tmpdir) / "filled.pdf"

        result = await asyncio.get_event_loop().run_in_executor(
            None,
            _fill_sync,
            t_pdf,
            t_map,
            meta_arg,
            data,
            out_path,
        )

        pdf_bytes = out_path.read_bytes()

    _log.info(
        "Template '%s' filled: %d written, %d skipped, %d warnings.",
        template_id,
        len(result.fields_written),
        len(result.fields_skipped),
        len(result.warnings),
    )
    return pdf_bytes, result


async def fill_template_batch(
    templates_root: Path,
    template_id: str,
    records: list[dict[str, Any]],
) -> BatchResult:
    """Fill multiple records for one template; return a ZIP of all PDFs."""
    if not records:
        from fastapi import HTTPException
        raise HTTPException(422, "records list must not be empty.")

    t_pdf = store.require_pdf(templates_root, template_id)
    t_map = store.require_map(templates_root, template_id)
    t_meta_path = store.meta_path(templates_root, template_id)
    meta_arg = t_meta_path if t_meta_path.exists() else None

    _log.info("Batch fill: template '%s', %d records.", template_id, len(records))

    with tempfile.TemporaryDirectory() as tmpdir:
        out_dir = Path(tmpdir)

        record_results: list[RecordResult] = await asyncio.get_event_loop().run_in_executor(
            None,
            _fill_many_sync,
            t_pdf,
            t_map,
            meta_arg,
            records,
            out_dir,
            template_id,
        )

        zip_bytes = _build_zip(out_dir, record_results)

    succeeded = sum(1 for r in record_results if r.ok)
    failed = len(record_results) - succeeded
    errors = [
        {"index": r.index, "filename": r.filename, "error": r.error}
        for r in record_results
        if not r.ok
    ]

    _log.info(
        "Batch fill complete: %d succeeded, %d failed.",
        succeeded,
        failed,
    )
    return BatchResult(
        zip_bytes=zip_bytes,
        total=len(records),
        succeeded=succeeded,
        failed=failed,
        errors=errors,
    )
