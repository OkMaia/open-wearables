"""Open Wearables in-process MCP Server (Streamable HTTP).

Mountable directly onto the FastAPI application at ``/mcp``.
"""

from __future__ import annotations

import logging
from datetime import date

from fastmcp import FastMCP
from starlette.applications import Starlette

from app.mcp.tools import register_tools

logger = logging.getLogger(__name__)

_mcp: FastMCP | None = None
_mcp_app: Starlette | None = None


def create_open_wearables_mcp() -> FastMCP:
    """Build the FastMCP server instance with all tools registered."""
    mcp = FastMCP(
        name="Open Wearables",
        instructions=f"""
        Today's date is {date.today().isoformat()}.

        Enables the assistant to query health, sleep, workout and biometrics data from wearable devices
        aggregated across providers (Garmin, Whoop, Polar, Suunto, Apple Health, Oura, etc.), as well as
        listing user connections and triggering synchronization on demand.

        Authenticate using the deployment API key via HTTP headers:
          - X-Open-Wearables-API-Key: <api_key>
          - or Authorization: Bearer <api_key>

        Available tools:
        - get_users: List or search users accessible via your API key
        - list_user_connections: List all connected wearable devices and provider services for a user
        - sync_provider_data: Trigger on-demand sync from a connected provider for a user
        - sync_historical_data: Trigger a historical backfill sync from a connected provider
        - get_activity_summary: Daily activity data (steps, calories, heart rate, intensity minutes)
        - get_sleep_summary: Daily sleep data for a user within a date range
        - get_workout_events: Workout and exercise sessions for a user within a date range
        - get_timeseries: Granular time-series samples (weight, SpO2, HRV, intraday heart rate)
        """,
    )
    register_tools(mcp)
    return mcp


def get_open_wearables_mcp() -> FastMCP:
    global _mcp
    if _mcp is None:
        _mcp = create_open_wearables_mcp()
    return _mcp


def get_open_wearables_mcp_app() -> Starlette:
    """Return the ASGI application for the MCP server using Streamable HTTP transport."""
    global _mcp_app
    if _mcp_app is None:
        mcp = get_open_wearables_mcp()
        # Transport 'streamable-http' with stateless_http=True for multi-tenant and agent environments
        _mcp_app = mcp.http_app(transport="streamable-http", stateless_http=True)
    return _mcp_app
