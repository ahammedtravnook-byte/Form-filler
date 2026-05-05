"""Typer-based command-line interface for ``pdf_filler``.

Five commands are exposed:

* ``fill`` — fill a template with input data and write a new PDF.
* ``inspect-template`` — print page count and per-page geometry.
* ``make-coordinate-guide`` — render PNGs with a coordinate grid for calibration.
* ``validate-fields-config`` — load and validate a fields config.
* ``hash-template`` — print the SHA-256 hash of a template PDF.
"""

from __future__ import annotations

import json
import logging
import sys
from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from .coordinates import load_fields_config, summarise_fields_config
from .exceptions import PdfFillerError
from .filler import PdfFiller
from .logging_config import configure_logging
from .render_check import inspect_template, render_coordinate_guide
from .utils import sha256_file
from .validators import load_template_metadata, validate_input_data

app = typer.Typer(
    name="pdf-filler",
    help="Coordinate-based static PDF template filler.",
    no_args_is_help=True,
    add_completion=False,
)
console = Console()


# --------------------------------------------------------------------------- #
# Default file locations                                                       #
# --------------------------------------------------------------------------- #

# All paths are relative to the project root (current working directory).
DEFAULT_TEMPLATE = Path("templates/schengen/template.pdf")
DEFAULT_FIELDS_CONFIG = Path("templates/schengen/fields_config.json")
DEFAULT_DATA = Path("examples/input_client.json")
DEFAULT_METADATA = Path("templates/schengen/template_metadata.json")


# --------------------------------------------------------------------------- #
# Common option type aliases                                                   #
# --------------------------------------------------------------------------- #

VerboseOpt = Annotated[
    bool,
    typer.Option("--verbose", "-v", help="Enable debug logging."),
]


def _bootstrap_logging(verbose: bool) -> None:
    configure_logging(level=logging.DEBUG if verbose else logging.INFO, force=True)


def _abort(msg: str, *, code: int = 1) -> None:
    console.print(f"[red]Error:[/red] {msg}")
    raise typer.Exit(code=code)


# --------------------------------------------------------------------------- #
# fill                                                                         #
# --------------------------------------------------------------------------- #


@app.command("fill")
def fill_cmd(
    template: Annotated[
        Path,
        typer.Option("--template", help="Path to template PDF."),
    ] = DEFAULT_TEMPLATE,
    data: Annotated[
        Path,
        typer.Option("--data", help="Path to input data JSON."),
    ] = DEFAULT_DATA,
    fields_config: Annotated[
        Path,
        typer.Option(
            "--fields-config",
            "--coordinates",
            help="Path to fields config JSON.",
        ),
    ] = DEFAULT_FIELDS_CONFIG,
    output: Annotated[
        Path,
        typer.Option("--output", help="Path to write filled PDF."),
    ] = Path("output/filled.pdf"),
    metadata: Annotated[
        Path | None,
        typer.Option("--metadata", help="Optional template metadata JSON."),
    ] = None,
    ignore_template_hash: Annotated[
        bool,
        typer.Option(
            "--ignore-template-hash",
            help="Skip SHA-256 hash check against metadata.",
        ),
    ] = False,
    debug_boxes: Annotated[
        bool,
        typer.Option(
            "--debug-boxes",
            help="Draw faint outlines around field target areas.",
        ),
    ] = False,
    overwrite: Annotated[
        bool,
        typer.Option("--overwrite", help="Overwrite existing output file."),
    ] = False,
    verbose: VerboseOpt = False,
) -> None:
    """Fill a template PDF with values from a JSON data file."""
    _bootstrap_logging(verbose)

    try:
        config = load_fields_config(fields_config)
        meta = load_template_metadata(metadata)
        input_data = validate_input_data(data)

        filler = PdfFiller(template, config, metadata=meta)
        result = filler.fill(
            data=input_data,
            output_path=output,
            debug_boxes=debug_boxes,
            ignore_template_hash=ignore_template_hash,
            overwrite=overwrite,
        )
    except PdfFillerError as exc:
        _abort(str(exc))
    except FileNotFoundError as exc:
        _abort(f"File not found: {exc}")

    table = Table(title="Fill result")
    table.add_column("Output")
    table.add_column("Pages")
    table.add_column("Written")
    table.add_column("Skipped")
    table.add_row(
        str(result.output_path),
        str(result.page_count),
        str(len(result.fields_written)),
        str(len(result.fields_skipped)),
    )
    console.print(table)
    if result.warnings:
        console.print(Panel("\n".join(result.warnings), title="Warnings", style="yellow"))
    console.print(f"[green]Wrote[/green] {result.output_path}")


# --------------------------------------------------------------------------- #
# inspect-template                                                             #
# --------------------------------------------------------------------------- #


@app.command("inspect-template")
def inspect_template_cmd(
    template: Annotated[
        Path,
        typer.Option("--template", help="Path to template PDF."),
    ] = DEFAULT_TEMPLATE,
    page: Annotated[
        int | None,
        typer.Option("--page", help="1-based page number to inspect (default: all)."),
    ] = None,
    verbose: VerboseOpt = False,
) -> None:
    """Print page count and geometry for a template PDF."""
    _bootstrap_logging(verbose)
    try:
        info = inspect_template(template, page=page)
    except PdfFillerError as exc:
        _abort(str(exc))
    except ValueError as exc:
        _abort(str(exc))

    console.print(
        Panel(
            f"[bold]{info.template_path}[/bold]\n"
            f"page count: {info.page_count}\n\n"
            f"{info.coordinate_system}",
            title="Template",
        )
    )

    table = Table(title="Pages")
    table.add_column("Page", justify="right")
    table.add_column("Width (pt)", justify="right")
    table.add_column("Height (pt)", justify="right")
    for p in info.pages:
        table.add_row(str(p.page_number), f"{p.width:.2f}", f"{p.height:.2f}")
    console.print(table)


# --------------------------------------------------------------------------- #
# make-coordinate-guide                                                        #
# --------------------------------------------------------------------------- #


@app.command("make-coordinate-guide")
def make_coordinate_guide_cmd(
    template: Annotated[
        Path,
        typer.Option("--template", help="Path to template PDF."),
    ] = DEFAULT_TEMPLATE,
    output: Annotated[
        Path,
        typer.Option("--output", help="Output directory for guide PNGs."),
    ] = Path("output/guide"),
    grid_step: Annotated[
        float,
        typer.Option("--grid-step", help="Minor grid spacing in points."),
    ] = 25.0,
    major_step: Annotated[
        float,
        typer.Option("--major-step", help="Major grid spacing in points."),
    ] = 100.0,
    zoom: Annotated[
        float,
        typer.Option("--zoom", help="Output rasterisation zoom factor."),
    ] = 2.0,
    verbose: VerboseOpt = False,
) -> None:
    """Render PNGs with a coordinate grid overlay for visual calibration."""
    _bootstrap_logging(verbose)
    try:
        written = render_coordinate_guide(
            template_path=template,
            output_dir=output,
            grid_step=grid_step,
            major_step=major_step,
            zoom=zoom,
        )
    except PdfFillerError as exc:
        _abort(str(exc))
    console.print(f"[green]Wrote[/green] {len(written)} guide page(s) to {output}")
    for path in written:
        console.print(f"  - {path}")


# --------------------------------------------------------------------------- #
# validate-fields-config                                                       #
# --------------------------------------------------------------------------- #


@app.command("validate-fields-config")
def validate_fields_config_cmd(
    fields_config: Annotated[
        Path,
        typer.Option(
            "--fields-config",
            "--coordinates",
            help="Path to fields config JSON.",
        ),
    ] = DEFAULT_FIELDS_CONFIG,
    verbose: VerboseOpt = False,
) -> None:
    """Validate a fields config JSON file and print a summary."""
    _bootstrap_logging(verbose)
    try:
        config = load_fields_config(fields_config)
    except PdfFillerError as exc:
        _abort(str(exc))

    summary = summarise_fields_config(config)
    console.print(Panel(json.dumps(summary, indent=2), title="Fields config summary"))


# --------------------------------------------------------------------------- #
# hash-template                                                                #
# --------------------------------------------------------------------------- #


@app.command("hash-template")
def hash_template_cmd(
    template: Annotated[
        Path,
        typer.Option("--template", help="Path to template PDF."),
    ] = DEFAULT_TEMPLATE,
    update_metadata: Annotated[
        Path | None,
        typer.Option(
            "--update-metadata",
            help="Optional metadata JSON path to write the computed hash into.",
        ),
    ] = None,
    verbose: VerboseOpt = False,
) -> None:
    """Print the SHA-256 hash of a template PDF, optionally updating metadata."""
    _bootstrap_logging(verbose)
    if not template.exists():
        _abort(f"Template not found: {template}")
    digest = sha256_file(template)
    console.print(f"[green]SHA-256[/green] {digest}  {template}")

    if update_metadata is not None:
        if not update_metadata.exists():
            _abort(f"Metadata file not found: {update_metadata}")
        try:
            with update_metadata.open("r", encoding="utf-8") as fh:
                meta = json.load(fh)
            if not isinstance(meta, dict):
                _abort("Metadata JSON must be an object.")
            meta["sha256"] = digest
            with update_metadata.open("w", encoding="utf-8") as fh:
                json.dump(meta, fh, indent=2)
                fh.write("\n")
            console.print(f"[green]Updated[/green] {update_metadata}")
        except json.JSONDecodeError as exc:
            _abort(f"Invalid JSON in {update_metadata}: {exc}")


# Allow `python -m pdf_filler.cli ...`
def main() -> None:  # pragma: no cover
    app()


if __name__ == "__main__":  # pragma: no cover
    sys.exit(app())
