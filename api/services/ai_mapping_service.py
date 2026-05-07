"""AI field-mapping service.

Calls OpenAI with extracted document data + template fields_config and
returns a client_json whose keys come from fields_config and values are
populated from the extracted data.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from openai import AsyncOpenAI

from api.core.config import settings
from api.core.logging import get_logger

_log = get_logger("api.ai_mapping_service")

_PROMPT_PATH = Path(__file__).parent.parent / "prompts" / "mapping_prompt.txt"
_system_prompt: str | None = None


def _get_system_prompt() -> str:
    global _system_prompt
    if _system_prompt is None:
        _system_prompt = _PROMPT_PATH.read_text(encoding="utf-8").strip()
    return _system_prompt


async def map_fields(
    extracted_data: dict[str, Any],
    fields_config: dict[str, Any],
) -> dict[str, Any]:
    """Call the OpenAI model to map extracted_data onto fields_config keys.

    Returns a flat dict (client_json) ready to send to the frontend.
    Raises HTTPException 502 on AI errors, 500 on JSON parse failure.
    """
    from fastapi import HTTPException

    if not settings.openai_api_key:
        raise HTTPException(
            status_code=500,
            detail="OPENAI_API_KEY is not configured on the server.",
        )

    client = AsyncOpenAI(api_key=settings.openai_api_key)

    user_message = json.dumps(
        {
            "extracted_data": extracted_data,
            "fields_config": fields_config,
        },
        ensure_ascii=False,
        indent=2,
    )

    _log.info(
        "Calling OpenAI model '%s' to map %d fields.",
        settings.openai_model,
        len(fields_config.get("fields", fields_config)),
    )

    try:
        response = await client.chat.completions.create(
            model=settings.openai_model,
            messages=[
                {"role": "system", "content": _get_system_prompt()},
                {"role": "user", "content": user_message},
            ],
            temperature=0,
            response_format={"type": "json_object"},
        )
    except Exception as exc:
        _log.error("OpenAI call failed: %s", exc)
        raise HTTPException(status_code=502, detail=f"AI mapping service error: {exc}") from exc

    raw = response.choices[0].message.content or ""
    _log.debug("AI raw response: %s", raw[:500])

    try:
        client_json: dict[str, Any] = json.loads(raw)
    except json.JSONDecodeError as exc:
        _log.error("AI returned non-JSON: %s", raw[:200])
        raise HTTPException(
            status_code=500,
            detail="AI returned invalid JSON. Cannot parse mapping result.",
        ) from exc

    return client_json
