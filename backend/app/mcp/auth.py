"""MCP Auth utilities for Open Wearables in-process MCP server."""

from __future__ import annotations

import logging
from typing import Any
from uuid import UUID

from fastmcp.server.context import Context
from starlette.datastructures import Headers

from app.database import SessionLocal
from app.models import ApiKey
from app.services.api_key_service import api_key_service

logger = logging.getLogger(__name__)


class McpAuthError(Exception):
    """Authentication failure for MCP tools."""

    def __init__(self, message: str = "Invalid or missing API key", *, status_code: int = 401):
        super().__init__(message)
        self.status_code = status_code
        self.message = message


def _header_value(headers: Headers | dict[str, Any], name: str) -> str | None:
    if isinstance(headers, Headers):
        return headers.get(name)
    lowered = {str(k).lower(): v for k, v in headers.items()}
    return lowered.get(name.lower())


def parse_mcp_api_key(headers: Headers | dict[str, Any]) -> str:
    """Extract API key from X-Open-Wearables-API-Key or Authorization Bearer header."""
    custom_header = _header_value(headers, "x-open-wearables-api-key")
    if custom_header and custom_header.strip():
        return custom_header.strip()

    auth_header = _header_value(headers, "authorization")
    if auth_header and auth_header.strip():
        val = auth_header.strip()
        if val.lower().startswith("bearer "):
            return val[7:].strip()
        return val

    raise McpAuthError("Missing API key in Authorization or X-Open-Wearables-API-Key header")


def authenticate_context(ctx: Context | None) -> UUID:
    """Authenticate incoming FastMCP Context against the database API keys."""
    if ctx is None:
        raise McpAuthError("Request context missing")

    try:
        request_context = ctx.request_context
    except (ValueError, AttributeError) as exc:
        raise McpAuthError("HTTP request context is required") from exc

    request = getattr(request_context, "request", None)
    if request is None:
        raise McpAuthError("HTTP request context is required")

    api_key_val = parse_mcp_api_key(request.headers)

    with SessionLocal() as db:
        try:
            api_key_obj: ApiKey = api_key_service.validate_api_key(db, api_key_val)
            return api_key_obj.id
        except Exception as exc:
            raise McpAuthError("Invalid or missing API key") from exc
