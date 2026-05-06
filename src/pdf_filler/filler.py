"""Core PDF filling engine.

The :class:`PdfFiller` class loads a static template PDF and stamps text and
checkbox marks at coordinates declared in a :class:`FieldsConfig`. It treats
the PDF as a fixed visual template — it does *not* use AcroForm/XFA APIs.

Design:
    * One :class:`PdfFiller` per template.
    * :py:meth:`PdfFiller.fill` is pure with respect to the template (the
      template file on disk is never modified — we open it, copy via
      ``insert_pdf`` into a fresh document, stamp into the copy, and save).
    * Errors short-circuit the operation; partial PDFs are not written.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import fitz  # PyMuPDF

from .config import SETTINGS
from .exceptions import (
    DataValidationError,
    MissingRequiredFieldError,
    PdfFillerError,
    TemplateNotFoundError,
    TextOverflowError,
    UnsupportedFieldTypeError,
)
from .logging_config import get_logger
from .models import (
    CheckboxFieldConfig,
    CheckboxGroupFieldConfig,
    DateFieldConfig,
    FieldsConfig,
    ImageFieldConfig,
    MultilineTextFieldConfig,
    SignatureTextFieldConfig,
    TemplateMetadata,
    TextFieldConfig,
)
from .utils import is_empty_value
from .validators import (
    parse_date_value,
    validate_metadata_page_count,
    validate_pages_in_range,
    validate_template_hash,
    validate_template_path,
)

_LOGGER = get_logger("filler")


# --------------------------------------------------------------------------- #
# Result type                                                                  #
# --------------------------------------------------------------------------- #


@dataclass
class FillResult:
    """Summary returned by :py:meth:`PdfFiller.fill`."""

    output_path: Path
    fields_written: list[str] = field(default_factory=list)
    fields_skipped: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    page_count: int = 0
    template_sha256: str | None = None


# --------------------------------------------------------------------------- #
# Engine                                                                       #
# --------------------------------------------------------------------------- #


class PdfFiller:
    """Stamps coordinate-mapped values onto a static template PDF."""

    def __init__(
        self,
        template_path: Path,
        fields_config: FieldsConfig,
        metadata: TemplateMetadata | None = None,
    ) -> None:
        self.template_path = validate_template_path(Path(template_path))
        self.fields_config = fields_config
        self.metadata = metadata
        self._template_sha: str | None = None

    # ----- public API ----------------------------------------------------- #

    def fill(
        self,
        data: dict[str, Any],
        output_path: Path,
        *,
        debug_boxes: bool = False,
        ignore_template_hash: bool = False,
        overwrite: bool = False,
    ) -> FillResult:
        """Fill the template with ``data`` and write to ``output_path``."""
        output_path = Path(output_path)
        if output_path.exists() and not overwrite:
            raise PdfFillerError(
                f"Output file already exists: {output_path}. Pass overwrite=True / --overwrite."
            )
        output_path.parent.mkdir(parents=True, exist_ok=True)

        self._template_sha = validate_template_hash(
            self.template_path, self.metadata, ignore=ignore_template_hash
        )

        result = FillResult(output_path=output_path, template_sha256=self._template_sha)

        with fitz.open(self.template_path) as src_doc:
            if src_doc.is_encrypted:
                if not SETTINGS.allow_encrypted_pdfs:
                    raise TemplateNotFoundError(
                        "Template PDF is encrypted; encrypted PDFs are not supported."
                    )
                if not src_doc.authenticate(""):
                    raise TemplateNotFoundError("Encrypted template requires a password.")

            page_count = src_doc.page_count
            result.page_count = page_count

            validate_metadata_page_count(self.metadata, page_count)
            validate_pages_in_range(self.fields_config, page_count)

            out_doc = fitz.open()  # empty document
            try:
                out_doc.insert_pdf(src_doc)

                for name, fcfg in self.fields_config.fields.items():
                    self._render_field(out_doc, name, fcfg, data, result, debug_boxes)

                out_doc.save(
                    str(output_path),
                    garbage=3,
                    deflate=True,
                    clean=True,
                )
            finally:
                out_doc.close()

        _LOGGER.info(
            "Fill complete: %d written, %d skipped -> %s",
            len(result.fields_written),
            len(result.fields_skipped),
            output_path,
        )
        return result

    # ----- field dispatch ------------------------------------------------- #

    def _render_field(
        self,
        doc: fitz.Document,
        name: str,
        cfg: Any,
        data: dict[str, Any],
        result: FillResult,
        debug_boxes: bool,
    ) -> None:
        """Resolve the value for ``cfg.data_key`` and dispatch by field type."""
        value = data.get(cfg.data_key)
        page = doc[cfg.page - 1]  # 1-based → 0-based

        if is_empty_value(value):
            if isinstance(cfg, (CheckboxFieldConfig, CheckboxGroupFieldConfig)):
                result.fields_skipped.append(name)
                _LOGGER.debug("Field '%s' (checkbox): empty value, leaving unchecked.", name)
                return
            if cfg.required:
                raise MissingRequiredFieldError(name, cfg.data_key)
            result.fields_skipped.append(name)
            warning = f"Optional field '{name}' has no value (data_key '{cfg.data_key}'); skipped."
            result.warnings.append(warning)
            _LOGGER.info(warning)
            return

        if debug_boxes:
            self._draw_debug_box(page, cfg)

        try:
            if isinstance(cfg, TextFieldConfig):
                self._render_text(page, name, cfg, str(value))
            elif isinstance(cfg, MultilineTextFieldConfig):
                self._render_multiline(page, name, cfg, str(value))
            elif isinstance(cfg, CheckboxFieldConfig):
                self._render_checkbox(page, name, cfg, value)
            elif isinstance(cfg, CheckboxGroupFieldConfig):
                self._render_checkbox_group(page, name, cfg, value)
            elif isinstance(cfg, DateFieldConfig):
                self._render_date(page, name, cfg, value)
            elif isinstance(cfg, ImageFieldConfig):
                raise UnsupportedFieldTypeError(
                    f"Field '{name}': image field type is not yet implemented."
                )
            elif isinstance(cfg, SignatureTextFieldConfig):
                self._render_text_like(page, name, cfg, str(value))
            else:
                raise UnsupportedFieldTypeError(
                    f"Field '{name}' has unsupported type {type(cfg).__name__}."
                )
        except PdfFillerError:
            raise
        except Exception as exc:  # pragma: no cover — defensive guard
            raise PdfFillerError(f"Failed to render field '{name}': {exc}") from exc

        result.fields_written.append(name)
        _LOGGER.debug("Field '%s' rendered on page %d.", name, cfg.page)

    # ----- per-type renderers --------------------------------------------- #

    def _render_text(
        self,
        page: fitz.Page,
        name: str,
        cfg: TextFieldConfig,
        value: str,
    ) -> None:
        text = self._truncate_chars(value, cfg.max_chars)
        font_size = cfg.font_size

        if cfg.width is None:
            page.insert_text(
                fitz.Point(cfg.x, cfg.y),
                text,
                fontname=cfg.font,
                fontsize=font_size,
                color=cfg.color,
            )
            return

        font_size = self._fit_text_width(
            name=name,
            text=text,
            font_name=cfg.font,
            font_size=font_size,
            min_font_size=cfg.min_font_size,
            max_width=cfg.width,
            overflow=cfg.overflow,
        )
        if cfg.overflow == "truncate" and cfg.max_chars is None:
            text = self._truncate_to_width(text, cfg.font, font_size, cfg.width)

        # PyMuPDF's insert_textbox needs noticeably more vertical room than the
        # font size; tight heights (e.g. height=12 with font_size=9) silently
        # drop the glyph. Always give it generous headroom — the text is
        # baselined at the top of the rect, so an oversized rect doesn't shift
        # the visual position.
        rect_height = max(font_size * 4.0, (cfg.height or 0))
        rect = fitz.Rect(cfg.x, cfg.y, cfg.x + cfg.width, cfg.y + rect_height)
        rc = page.insert_textbox(
            rect,
            text,
            fontname=cfg.font,
            fontsize=font_size,
            align=_align_to_fitz(cfg.align),
            color=cfg.color,
        )
        if rc < 0 and cfg.overflow == "error":
            raise TextOverflowError(name, len(text), cfg.width)

    def _render_text_like(
        self,
        page: fitz.Page,
        name: str,
        cfg: SignatureTextFieldConfig,
        value: str,
    ) -> None:
        font_size = cfg.font_size
        if cfg.width is None:
            page.insert_text(
                fitz.Point(cfg.x, cfg.y),
                value,
                fontname=cfg.font,
                fontsize=font_size,
                color=cfg.color,
            )
            return

        font_size = self._fit_text_width(
            name=name,
            text=value,
            font_name=cfg.font,
            font_size=font_size,
            min_font_size=cfg.min_font_size,
            max_width=cfg.width,
            overflow=cfg.overflow,
        )
        if cfg.overflow == "truncate":
            value = self._truncate_to_width(value, cfg.font, font_size, cfg.width)

        rect = fitz.Rect(cfg.x, cfg.y, cfg.x + cfg.width, cfg.y + font_size * 4.0)
        rc = page.insert_textbox(
            rect,
            value,
            fontname=cfg.font,
            fontsize=font_size,
            align=_align_to_fitz(cfg.align),
            color=cfg.color,
        )
        if rc < 0 and cfg.overflow == "error":
            raise TextOverflowError(name, len(value), cfg.width)

    def _render_multiline(
        self,
        page: fitz.Page,
        name: str,
        cfg: MultilineTextFieldConfig,
        value: str,
    ) -> None:
        height = cfg.height if cfg.height is not None else cfg.line_height * cfg.max_lines + 2
        rect = fitz.Rect(cfg.x, cfg.y, cfg.x + cfg.width, cfg.y + height)
        rc = page.insert_textbox(
            rect,
            value,
            fontname=cfg.font,
            fontsize=cfg.font_size,
            align=_align_to_fitz(cfg.align),
            color=cfg.color,
        )
        if rc < 0:
            if cfg.overflow == "error":
                raise TextOverflowError(name, len(value), cfg.width)
            if cfg.overflow == "shrink":
                fitted = False
                for fs in _shrink_steps(cfg.font_size, floor=6.0):
                    rc = page.insert_textbox(
                        rect,
                        value,
                        fontname=cfg.font,
                        fontsize=fs,
                        align=_align_to_fitz(cfg.align),
                        color=cfg.color,
                    )
                    if rc >= 0:
                        fitted = True
                        break
                if not fitted:
                    raise TextOverflowError(name, len(value), cfg.width)
            elif cfg.overflow == "truncate":
                truncated = value
                while truncated and (
                    rc := page.insert_textbox(
                        rect,
                        truncated,
                        fontname=cfg.font,
                        fontsize=cfg.font_size,
                        align=_align_to_fitz(cfg.align),
                        color=cfg.color,
                    )
                ) < 0:
                    truncated = truncated[:-1]
                if not truncated:
                    raise TextOverflowError(name, len(value), cfg.width)

    def _render_date(
        self,
        page: fitz.Page,
        name: str,
        cfg: DateFieldConfig,
        value: Any,
    ) -> None:
        # Accept already-formatted date strings. Only attempt structured parsing
        # if it's not already in the desired output format (e.g. "01-01-2020").
        text: str
        if isinstance(value, str) and value.strip():
            try:
                date_obj = parse_date_value(value)
                text = date_obj.strftime(cfg.format)
            except DataValidationError:
                # Pass through verbatim — the user may have pre-formatted it.
                text = value.strip()
        else:
            date_obj = parse_date_value(value)
            try:
                text = date_obj.strftime(cfg.format)
            except ValueError as exc:
                raise DataValidationError(
                    f"Field '{name}': invalid date format string '{cfg.format}': {exc}"
                ) from exc

        synthesised = TextFieldConfig(
            type="text",
            data_key=cfg.data_key,
            page=cfg.page,
            x=cfg.x,
            y=cfg.y,
            required=cfg.required,
            font=cfg.font,
            font_size=cfg.font_size,
            align=cfg.align,
            width=cfg.width,
            overflow=cfg.overflow,
            color=cfg.color,
        )
        self._render_text(page, name, synthesised, text)

    def _render_checkbox(
        self,
        page: fitz.Page,
        name: str,
        cfg: CheckboxFieldConfig,
        value: Any,
    ) -> None:
        if not _checkbox_should_check(cfg.checked_when, value):
            _LOGGER.debug("Checkbox '%s' resolved to unchecked.", name)
            return
        self._draw_check_mark(
            page,
            x=cfg.x,
            y=cfg.y,
            size=cfg.box_size,
            style=cfg.check_style,
            color=cfg.color,
            line_width=cfg.line_width,
        )

    def _render_checkbox_group(
        self,
        page: fitz.Page,
        name: str,
        cfg: CheckboxGroupFieldConfig,
        value: Any,
    ) -> None:
        """Tick the option(s) whose key matches ``value`` (case-insensitive)."""
        # Normalise the value(s) to a list of lowercased strings.
        if isinstance(value, (list, tuple, set)):
            wanted = {str(v).strip().lower() for v in value if not is_empty_value(v)}
        else:
            wanted = {str(value).strip().lower()}

        # Build a case-insensitive lookup of options.
        lookup = {key.strip().lower(): (key, opt) for key, opt in cfg.options.items()}

        matched_any = False
        for w in wanted:
            if w not in lookup:
                _LOGGER.warning(
                    "Checkbox group '%s': value '%s' does not match any option (%s).",
                    name, w, ", ".join(cfg.options.keys()),
                )
                continue
            _key, opt = lookup[w]
            self._draw_check_mark(
                page,
                x=opt.x,
                y=opt.y,
                size=cfg.box_size,
                style=cfg.check_style,
                color=cfg.color,
                line_width=cfg.line_width,
            )
            matched_any = True

        if not matched_any:
            _LOGGER.debug("Checkbox group '%s': no option ticked.", name)

    # ----- helpers -------------------------------------------------------- #

    @staticmethod
    def _draw_check_mark(
    page: fitz.Page,
    *,
    x: float,
    y: float,
    size: float,
    style: str,
    color: tuple[float, float, float],
    line_width: float,
) -> None:
        x0, y0 = x, y
        x1, y1 = x0 + size, y0 + size
        rect = fitz.Rect(x0, y0, x1, y1)
        
        if style == "filled_square":
            page.draw_rect(rect, color=color, fill=color, width=line_width, overlay=True)
        elif style == "x":
            page.draw_line(fitz.Point(x0, y0), fitz.Point(x1, y1), color=color, width=line_width, overlay=True)
            page.draw_line(fitz.Point(x1, y0), fitz.Point(x0, y1), color=color, width=line_width, overlay=True)
        elif style == "check":
            # Draw a ✓ shape with two line segments: short left stroke + long right stroke.
            # Proportions are relative to the box so it scales with any size.
            p1 = fitz.Point(x0 + size * 0.14, y0 + size * 0.67)  # left tip
            p2 = fitz.Point(x0 + size * 0.27, y0 + size * 1.00)  # bottom valley
            p3 = fitz.Point(x0 + size * 1.00, y0 + size * 0.00)  # right tip
            page.draw_line(p1, p2, color=color, width=line_width, overlay=True)
            page.draw_line(p2, p3, color=color, width=line_width, overlay=True)
   
    @staticmethod
    def _truncate_chars(text: str, max_chars: int | None) -> str:
        if max_chars is None or len(text) <= max_chars:
            return text
        return text[:max_chars]

    @staticmethod
    def _fit_text_width(
        *,
        name: str,
        text: str,
        font_name: str,
        font_size: float,
        min_font_size: float,
        max_width: float,
        overflow: str,
    ) -> float:
        width = fitz.get_text_length(text, fontname=font_name, fontsize=font_size)
        if width <= max_width:
            return font_size
        if overflow == "shrink":
            for fs in _shrink_steps(font_size, floor=min_font_size):
                if fitz.get_text_length(text, fontname=font_name, fontsize=fs) <= max_width:
                    return fs
            raise TextOverflowError(name, len(text), max_width)
        if overflow == "truncate":
            return font_size
        raise TextOverflowError(name, len(text), max_width)

    @staticmethod
    def _truncate_to_width(
        text: str, font_name: str, font_size: float, max_width: float
    ) -> str:
        result = text
        while result and fitz.get_text_length(
            result, fontname=font_name, fontsize=font_size
        ) > max_width:
            result = result[:-1]
        return result

    @staticmethod
    def _draw_debug_box(page: fitz.Page, cfg: Any) -> None:
        """Draw a faint outline around the field's target area for visual debugging."""
        debug_color = (1.0, 0.4, 0.4)  # light red
        if isinstance(cfg, CheckboxFieldConfig):
            rect = fitz.Rect(cfg.x, cfg.y, cfg.x + cfg.box_size, cfg.y + cfg.box_size)
            page.draw_rect(rect, color=debug_color, width=0.4, overlay=True)
        elif isinstance(cfg, CheckboxGroupFieldConfig):
            for opt in cfg.options.values():
                rect = fitz.Rect(opt.x, opt.y, opt.x + cfg.box_size, opt.y + cfg.box_size)
                page.draw_rect(rect, color=debug_color, width=0.4, overlay=True)
        elif isinstance(cfg, MultilineTextFieldConfig):
            height = cfg.height if cfg.height is not None else cfg.line_height * cfg.max_lines
            rect = fitz.Rect(cfg.x, cfg.y, cfg.x + cfg.width, cfg.y + height)
            page.draw_rect(rect, color=debug_color, width=0.4, overlay=True)
        else:
            width = getattr(cfg, "width", None) or 80.0
            font_size = getattr(cfg, "font_size", 10.0)
            height = getattr(cfg, "height", None) or font_size * 1.6
            rect = fitz.Rect(cfg.x, cfg.y, cfg.x + width, cfg.y + height)
            page.draw_rect(rect, color=debug_color, width=0.4, overlay=True)


# --------------------------------------------------------------------------- #
# Module-level helpers                                                         #
# --------------------------------------------------------------------------- #


def _align_to_fitz(align: str) -> int:
    return {
        "left": fitz.TEXT_ALIGN_LEFT,
        "center": fitz.TEXT_ALIGN_CENTER,
        "right": fitz.TEXT_ALIGN_RIGHT,
    }[align]


def _shrink_steps(start: float, floor: float, step: float = 0.5) -> list[float]:
    sizes: list[float] = []
    current = start - step
    while current >= floor:
        sizes.append(round(current, 2))
        current -= step
    return sizes


def _checkbox_should_check(checked_when: Any, value: Any) -> bool:
    """Decide whether a checkbox should be marked given its ``checked_when`` rule.

    * If ``checked_when`` is None → boolean checkbox: truthy ``value`` checks it.
    * Otherwise → option checkbox: case-insensitive string equality.
    """
    if checked_when is None:
        return bool(value)
    if isinstance(value, bool):
        if isinstance(checked_when, bool):
            return value == checked_when
        return False
    return str(value).strip().lower() == str(checked_when).strip().lower()
