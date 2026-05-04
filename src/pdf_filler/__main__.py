"""Allow ``python -m pdf_filler`` to invoke the Typer CLI."""

from __future__ import annotations

from .cli import app

if __name__ == "__main__":
    app()
