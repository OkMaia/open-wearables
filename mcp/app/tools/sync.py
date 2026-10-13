"""MCP tools for provider connections and data synchronization."""

import logging
from typing import Literal

from fastmcp import FastMCP

from app.services.api_client import client
from app.services.exceptions import NotFoundError, OpenWearablesError

logger = logging.getLogger(__name__)

# Create router for sync and connection tools
sync_router = FastMCP(name="Sync and Connection Tools")


@sync_router.tool
async def list_user_connections(user_id: str) -> dict:
    """
    List all connected wearable devices and provider services for a user.

    Use this tool to discover which providers (Garmin, Polar, Suunto, Whoop, Oura,
    Apple Health, etc.) a user has paired, their connection status, and whether they
    are ready to be synced.

    Args:
        user_id: UUID of the user. Use get_users to discover available users.

    Returns:
        A dictionary containing:
        - user: Information about the user (id, first_name, last_name)
        - connections: List of connection objects with provider, status, and capabilities
        - total: Number of connected providers

    Example response:
        {
            "user": {"id": "uuid-1", "first_name": "John", "last_name": "Doe"},
            "connections": [
                {
                    "provider": "garmin",
                    "status": "active",
                    "created_at": "2026-01-10T10:00:00Z",
                    "last_synced_at": "2026-02-01T12:00:00Z",
                    "live_sync_mode": "webhook_stream"
                }
            ],
            "total": 1
        }
    """
    try:
        # Fetch user details
        try:
            user_data = await client.get_user(user_id)
            user = {
                "id": str(user_data.get("id")),
                "first_name": user_data.get("first_name"),
                "last_name": user_data.get("last_name"),
            }
        except NotFoundError as e:
            return {"error": f"User not found: {user_id}", "details": str(e)}

        raw_connections = await client.get_user_connections(user_id)
        connections = []
        for conn in raw_connections:
            if isinstance(conn, dict):
                connections.append(
                    {
                        "provider": conn.get("provider"),
                        "status": conn.get("status"),
                        "created_at": conn.get("created_at"),
                        "last_synced_at": conn.get("last_synced_at"),
                        "live_sync_mode": conn.get("live_sync_mode"),
                        "max_historical_days": conn.get("max_historical_days"),
                    }
                )

        return {
            "user": user,
            "connections": connections,
            "total": len(connections),
        }
    except OpenWearablesError as e:
        logger.error(f"Error fetching connections for user {user_id}: {e}")
        return {"error": "Failed to retrieve user connections", "details": str(e)}


@sync_router.tool
async def sync_provider_data(
    user_id: str,
    provider: str,
    data_type: Literal["workouts", "247", "all"] = "all",
    run_async: bool = True,
) -> dict:
    """
    Trigger on-demand data synchronization from a connected wearable provider.

    This tool triggers a pull sync from the provider's API (e.g. Garmin, Polar,
    Suunto, Whoop, Oura) to import the user's latest data into Open Wearables.

    Args:
        user_id: UUID of the user. Use get_users to discover available users.
        provider: Name of the provider to sync (e.g., "garmin", "polar", "suunto", "whoop", "oura").
                  Use list_user_connections first to see which providers are active.
        data_type: Type of data to sync:
                   - "workouts": Exercises, runs, workouts
                   - "247": Daily activity, sleep, HRV, recovery metrics
                   - "all": All available data types (default)
        run_async: Whether to dispatch sync to background Celery worker (default: True).
                   Running async returns immediately with a task ID and avoids timeouts.

    Returns:
        A dictionary containing:
        - success: Whether the sync request was accepted
        - provider: Name of the synced provider
        - user_id: The user's ID
        - status: Status message or task information

    Example response:
        {
            "success": True,
            "provider": "garmin",
            "user_id": "uuid-1",
            "status": "Sync task dispatched",
            "task_id": "celery-task-uuid"
        }
    """
    try:
        # Check user existence
        try:
            await client.get_user(user_id)
        except NotFoundError as e:
            return {"error": f"User not found: {user_id}", "details": str(e)}

        result = await client.sync_provider_data(
            user_id=user_id,
            provider=provider.lower().strip(),
            data_type=data_type,
            run_async=run_async,
        )

        return {
            "success": True,
            "provider": provider.lower().strip(),
            "user_id": user_id,
            "result": result,
        }
    except OpenWearablesError as e:
        logger.error(f"Error triggering sync for user {user_id} on {provider}: {e}")
        return {"error": f"Failed to sync data from {provider}", "details": str(e)}


@sync_router.tool
async def sync_historical_data(
    user_id: str,
    provider: str,
    days: int = 90,
) -> dict:
    """
    Trigger a historical backfill sync from a connected wearable provider.

    Use this tool to backfill past data (up to 90 or 365 days depending on the provider)
    for a user when they first connect or when historical data is missing.

    Args:
        user_id: UUID of the user.
        provider: Provider name (e.g. "garmin", "whoop", "oura").
        days: Number of days of history to fetch (1 to 365, default 90).

    Returns:
        A dictionary containing the dispatched backfill details.
    """
    try:
        try:
            await client.get_user(user_id)
        except NotFoundError as e:
            return {"error": f"User not found: {user_id}", "details": str(e)}

        result = await client.sync_historical_data(
            user_id=user_id,
            provider=provider.lower().strip(),
            days=days,
        )

        return {
            "success": True,
            "provider": provider.lower().strip(),
            "user_id": user_id,
            "result": result,
        }
    except OpenWearablesError as e:
        logger.error(f"Error triggering historical sync for user {user_id} on {provider}: {e}")
        return {"error": f"Failed to trigger historical sync from {provider}", "details": str(e)}
