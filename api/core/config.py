"""API-level configuration, loaded from environment variables."""

from __future__ import annotations

from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="PDF_API_",
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    # Auth
    admin_api_key: str = Field(
        default="change-me-in-production",
        description="Bearer token required for all /admin routes.",
    )

    # Storage
    templates_dir: Path = Field(
        default=Path("templates"),
        description="Root directory where template folders live.",
    )

    # Runtime behaviour
    log_level: str = Field(default="INFO")
    log_json: bool = Field(
        default=False,
        description="Emit JSON logs (True) or human-readable (False).",
    )
    max_upload_bytes: int = Field(
        default=50 * 1024 * 1024,
        description="Max PDF upload size in bytes.",
    )
    max_batch_records: int = Field(
        default=500,
        description="Maximum number of records allowed in a single batch fill request.",
    )
    fill_worker_threads: int = Field(
        default=4,
        description="Size of the bounded thread pool used for PDF fill operations.",
    )
    # Passed through to the pdf_filler engine
    debug_boxes: bool = Field(
        default=False,
        description="Draw debug bounding boxes on filled PDFs.",
    )
    ignore_template_hash: bool = Field(
        default=False,
        description="Skip SHA-256 hash check when filling.",
    )
    mrz_debug: bool = Field(
        default=False,
        description="Enable MRZ OCR debug output (prints all OCR attempts).",
    )

    @field_validator("templates_dir", mode="before")
    @classmethod
    def _resolve_templates_dir(cls, v: object) -> Path:
        return Path(str(v)).resolve()


settings = Settings()
