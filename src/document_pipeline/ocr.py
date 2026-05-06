"""PDF → image → OCR text extraction.

Uses PyMuPDF to render PDF pages to images, then RapidOCR for recognition.
RapidOCR (rapidocr-onnxruntime) is pure Python with pre-built ONNX wheels —
no system binaries, no Rust compiler, no MSVC linker required.

Install: pip install rapidocr-onnxruntime

Arabic note: RapidOCR ships English + Chinese models out of the box.
For Arabic text on Emirates IDs (the Arabic name on the reverse side),
it will produce garbage — that field is treated as optional. The English
side of the Emirates ID (ID number, DOB, expiry, nationality) is reliably
extracted in English-only mode.
"""

from __future__ import annotations

import io
from functools import lru_cache

import fitz  # PyMuPDF
import numpy as np
from PIL import Image, ImageEnhance, ImageOps

_RENDER_DPI = 300


def pdf_page_to_pil(pdf_bytes: bytes, page_index: int = 0, dpi: int = _RENDER_DPI) -> Image.Image:
    """Render one PDF page to a PIL Image (RGB)."""
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    if page_index >= len(doc):
        raise ValueError(
            f"Page index {page_index} out of range — PDF has {len(doc)} page(s)"
        )
    page = doc[page_index]
    scale = dpi / 72.0
    mat = fitz.Matrix(scale, scale)
    pix = page.get_pixmap(matrix=mat, colorspace=fitz.csRGB, alpha=False)
    return Image.open(io.BytesIO(pix.tobytes("png"))).convert("RGB")


def _preprocess(img: Image.Image) -> Image.Image:
    """Greyscale + mild contrast boost before OCR."""
    grey = ImageOps.grayscale(img)
    return ImageEnhance.Contrast(grey).enhance(1.5)


@lru_cache(maxsize=1)
def _get_rapidocr() -> object:
    """Return a cached RapidOCR instance. Loaded once per process."""
    try:
        from rapidocr_onnxruntime import RapidOCR  # type: ignore[import-untyped]
    except ImportError as exc:
        raise ImportError(
            "rapidocr-onnxruntime is not installed. "
            "Run: pip install rapidocr-onnxruntime"
        ) from exc
    return RapidOCR()


def ocr_image(img: Image.Image) -> str:
    """Run RapidOCR on a PIL Image and return the full text as a single string.

    Results are sorted top-to-bottom by the y-coordinate of their bounding box
    so the output reads in natural reading order.
    """
    engine = _get_rapidocr()
    arr = np.array(_preprocess(img))
    result, _ = engine(arr)  # type: ignore[operator]

    if not result:
        return ""

    # Each item: [[x1,y1],[x2,y2],[x3,y3],[x4,y4]], text, confidence
    # Sort by top-left y coordinate for reading order
    sorted_results = sorted(result, key=lambda r: r[0][0][1])
    return "\n".join(text for (_bbox, text, _conf) in sorted_results if text.strip())


def extract_text_from_pdf(pdf_bytes: bytes, langs: tuple[str, ...] = ("en",)) -> str:
    """Extract text from every page of a PDF.

    Tries PyMuPDF direct text extraction first (fast, lossless for digital PDFs).
    Falls back to RapidOCR for pages with no selectable text layer (scanned images).

    The `langs` parameter is accepted for API compatibility but RapidOCR's bundled
    models cover English (and Chinese) regardless of what is passed.
    """
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    pages_text: list[str] = []

    for page in doc:
        direct_text = page.get_text("text").strip()
        if len(direct_text) > 20:
            # Digital PDF — use text layer directly
            pages_text.append(direct_text)
        else:
            # Scanned page — render at 300 DPI and OCR
            scale = _RENDER_DPI / 72.0
            mat = fitz.Matrix(scale, scale)
            pix = page.get_pixmap(matrix=mat, colorspace=fitz.csRGB, alpha=False)
            img = Image.open(io.BytesIO(pix.tobytes("png"))).convert("RGB")
            pages_text.append(ocr_image(img))

    return "\n\n".join(pages_text)


def get_page_count(pdf_bytes: bytes) -> int:
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    return len(doc)
