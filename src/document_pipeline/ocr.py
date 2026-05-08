"""PDF -> image -> OCR text extraction (Tesseract only).

Uses PyMuPDF to render PDF pages to images, then Tesseract (via pytesseract)
for recognition. Tesseract is the single OCR backend across the pipeline so
there are no extra ML runtimes (no ONNX, no Torch, no Rust toolchains).

Install Tesseract: https://github.com/UB-Mannheim/tesseract/wiki
For Arabic on the back of an Emirates ID, install the Arabic language data
("ara") via the Tesseract installer or `tesseract --list-langs` to verify.
"""

from __future__ import annotations

import io
import os

import fitz  # PyMuPDF
from PIL import Image, ImageEnhance, ImageOps

_RENDER_DPI = 300
_DEFAULT_TESSERACT_PATH = r"C:\Program Files\Tesseract-OCR\tesseract.exe"


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


def _import_pytesseract():  # type: ignore[no-untyped-def]
    try:
        import pytesseract
    except ImportError as exc:
        raise ImportError(
            "pytesseract is not installed. Run: pip install pytesseract\n"
            "Also ensure the Tesseract binary is installed: "
            "https://github.com/UB-Mannheim/tesseract/wiki"
        ) from exc

    custom_path = os.environ.get("TESSERACT_CMD")
    if custom_path and os.path.exists(custom_path):
        pytesseract.pytesseract.tesseract_cmd = custom_path
    elif os.name == "nt" and os.path.exists(_DEFAULT_TESSERACT_PATH):
        pytesseract.pytesseract.tesseract_cmd = _DEFAULT_TESSERACT_PATH
    return pytesseract


def _langs_to_tesseract(langs: tuple[str, ...]) -> str:
    """Map the pipeline's lang codes to Tesseract's traineddata names."""
    mapping = {"en": "eng", "ar": "ara", "eng": "eng", "ara": "ara"}
    resolved = [mapping.get(lang, lang) for lang in langs] or ["eng"]
    return "+".join(dict.fromkeys(resolved))


def ocr_image(
    img: Image.Image,
    langs: tuple[str, ...] = ("en",),
    psms: tuple[int, ...] = (6,),
) -> str:
    """Run Tesseract on a PIL Image and return the extracted text.

    `psms` accepts multiple page-segmentation modes; the outputs are concatenated.
    PSM 6 (uniform block) is the default. ID-card layouts with sparse fields
    benefit from also running PSM 11 (sparse text), which catches small fields
    like "Sex: F" that PSM 6 silently drops.
    """
    pytesseract = _import_pytesseract()
    prepped = _preprocess(img)
    lang = _langs_to_tesseract(langs)
    parts: list[str] = []
    for psm in psms:
        config = f"--oem 3 --psm {psm}"
        parts.append(pytesseract.image_to_string(prepped, lang=lang, config=config))
    return "\n".join(parts)


def extract_text_from_pdf(
    pdf_bytes: bytes,
    langs: tuple[str, ...] = ("en",),
    psms: tuple[int, ...] = (6,),
) -> str:
    """Extract text from every page of a PDF.

    Tries PyMuPDF direct text extraction first (fast, lossless for digital PDFs).
    Falls back to Tesseract for pages with no usable text layer (scanned images).
    `psms` is forwarded to `ocr_image` for the OCR fallback path.
    """
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    pages_text: list[str] = []

    for page in doc:
        direct_text = page.get_text("text").strip()
        if len(direct_text) > 20:
            pages_text.append(direct_text)
        else:
            scale = _RENDER_DPI / 72.0
            mat = fitz.Matrix(scale, scale)
            pix = page.get_pixmap(matrix=mat, colorspace=fitz.csRGB, alpha=False)
            img = Image.open(io.BytesIO(pix.tobytes("png"))).convert("RGB")
            pages_text.append(ocr_image(img, langs=langs, psms=psms))

    return "\n\n".join(pages_text)


def get_page_count(pdf_bytes: bytes) -> int:
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    return len(doc)
