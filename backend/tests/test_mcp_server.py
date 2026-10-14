"""Tests for in-process MCP server mounting and tools."""

import pytest
from fastapi.testclient import TestClient


def test_mcp_endpoint_mounted(client: TestClient) -> None:
    """Verify that /mcp route is accessible and responds to MCP streamable requests."""
    response = client.get("/mcp", follow_redirects=True)
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_mcp_auth_parsing() -> None:
    """Test parse_mcp_api_key helper with various header combinations."""
    from app.mcp.auth import McpAuthError, parse_mcp_api_key

    assert parse_mcp_api_key({"X-Open-Wearables-API-Key": "sk-test"}) == "sk-test"
    assert parse_mcp_api_key({"authorization": "Bearer sk-test2"}) == "sk-test2"
    assert parse_mcp_api_key({"Authorization": "bearer sk-test3"}) == "sk-test3"
    assert parse_mcp_api_key({"authorization": "sk-raw"}) == "sk-raw"

    with pytest.raises(McpAuthError):
        parse_mcp_api_key({})


def test_mcp_server_creation() -> None:
    """Test creating FastMCP server instance and ASGI app."""
    from app.mcp.server import get_open_wearables_mcp, get_open_wearables_mcp_app

    mcp = get_open_wearables_mcp()
    assert mcp.name == "Open Wearables"

    app = get_open_wearables_mcp_app()
    assert app is not None
