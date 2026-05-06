"""Admin API key authentication dependency."""

from __future__ import annotations

from fastapi import HTTPException, Security
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from api.core.config import settings

_bearer = HTTPBearer(auto_error=False)


def require_admin(
    credentials: HTTPAuthorizationCredentials | None = Security(_bearer),
) -> None:
    """FastAPI dependency — raises 401/403 if the admin key is wrong."""
    if credentials is None:
        raise HTTPException(
            status_code=401,
            detail="Missing Authorization header.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    if credentials.credentials != settings.admin_api_key:
        raise HTTPException(status_code=403, detail="Invalid admin API key.")
