"""HTTP client for Open Wearables backend API."""

import logging
from typing import Any

import httpx

from app.config import settings
from app.services.exceptions import AuthenticationError, ConfigurationError, NotFoundError

logger = logging.getLogger(__name__)


class OpenWearablesClient:
    """Client for interacting with Open Wearables REST API."""

    def __init__(self) -> None:
        self.base_url = settings.open_wearables_api_url.rstrip("/")
        self.timeout = settings.request_timeout
        self._api_key = settings.open_wearables_api_key.get_secret_value()

    def _ensure_configured(self) -> None:
        """Raise an error if the API key is not configured."""
        if not self._api_key:
            from app.config import Settings

            env_file = Settings.model_config.get("env_file")
            raise ConfigurationError(f"OPEN_WEARABLES_API_KEY is not configured. Please set it in: {env_file}")

    @property
    def headers(self) -> dict[str, str]:
        """Get headers for API requests."""
        return {
            "X-Open-Wearables-API-Key": self._api_key,
            "Content-Type": "application/json",
        }

    async def _request(self, method: str, path: str, **kwargs: Any) -> dict[str, Any]:
        """Make an HTTP request to the backend API."""
        self._ensure_configured()
        url = f"{self.base_url}{path}"
        logger.debug(f"Making {method} request to {url}")

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.request(
                method=method,
                url=url,
                headers=self.headers,
                **kwargs,
            )

            if response.status_code == 401:
                raise AuthenticationError("Invalid API key. Check your OPEN_WEARABLES_API_KEY configuration.")
            if response.status_code == 404:
                raise NotFoundError(f"Resource not found: {path}")

            response.raise_for_status()
            return response.json()

    async def get_users(self, search: str | None = None, limit: int = 100) -> dict[str, Any]:
        """
        List users accessible via the configured API key.

        Args:
            search: Optional search term to filter users by name/email
            limit: Maximum number of users to return

        Returns:
            Paginated response with users list
        """
        params = {"limit": limit}
        if search:
            params["search"] = search

        return await self._request("GET", "/api/v1/users", params=params)

    async def get_user(self, user_id: str) -> dict[str, Any]:
        """
        Get a specific user by ID.

        Args:
            user_id: UUID of the user

        Returns:
            User details
        """
        return await self._request("GET", f"/api/v1/users/{user_id}")

    async def get_sleep_summaries(
        self,
        user_id: str,
        start_date: str,
        end_date: str,
        limit: int = 100,
    ) -> dict[str, Any]:
        """
        Get sleep summaries for a user within a date range.

        Args:
            user_id: UUID of the user
            start_date: Start date (YYYY-MM-DD format)
            end_date: End date (YYYY-MM-DD format)
            limit: Maximum number of records to return

        Returns:
            Paginated response with sleep summaries
        """
        params = {
            "start_date": start_date,
            "end_date": end_date,
            "limit": limit,
        }
        return await self._request("GET", f"/api/v1/users/{user_id}/summaries/sleep", params=params)

    async def get_workouts(
        self,
        user_id: str,
        start_date: str,
        end_date: str,
        record_type: str | None = None,
        limit: int = 100,
    ) -> dict[str, Any]:
        """
        Get workouts for a user within a date range.

        Args:
            user_id: UUID of the user
            start_date: Start date (YYYY-MM-DD format)
            end_date: End date (YYYY-MM-DD format)
            record_type: Optional workout type filter (e.g., "running", "cycling")
            limit: Maximum number of records to return

        Returns:
            Paginated response with workout records
        """
        params: dict[str, Any] = {
            "start_date": start_date,
            "end_date": end_date,
            "limit": limit,
        }
        if record_type:
            params["record_type"] = record_type
        return await self._request("GET", f"/api/v1/users/{user_id}/events/workouts", params=params)

    async def get_activity_summaries(
        self,
        user_id: str,
        start_date: str,
        end_date: str,
        limit: int = 100,
    ) -> dict[str, Any]:
        """
        Get activity summaries for a user within a date range.

        Args:
            user_id: UUID of the user
            start_date: Start date (YYYY-MM-DD format)
            end_date: End date (YYYY-MM-DD format)
            limit: Maximum number of records to return

        Returns:
            Paginated response with activity summaries
        """
        params = {
            "start_date": start_date,
            "end_date": end_date,
            "limit": limit,
        }
        return await self._request("GET", f"/api/v1/users/{user_id}/summaries/activity", params=params)

    async def get_timeseries(
        self,
        user_id: str,
        start_time: str,
        end_time: str,
        types: list[str],
        resolution: str = "raw",
        limit: int = 100,
        cursor: str | None = None,
    ) -> dict[str, Any]:
        """
        Get granular time-series samples for a user within a time range.

        Args:
            user_id: UUID of the user
            start_time: Start of the window (ISO-8601, e.g. "2026-04-05T00:00:00Z")
            end_time: End of the window (ISO-8601, e.g. "2026-04-05T23:59:59Z")
            types: SeriesType codes to include (e.g. ["heart_rate", "oxygen_saturation"])
            resolution: One of "raw", "1min", "5min", "15min", "1hour"
            limit: Page size (1-100)
            cursor: Opaque pagination cursor returned by a previous call

        Returns:
            Paginated response with time-series samples
        """
        params: dict[str, Any] = {
            "start_time": start_time,
            "end_time": end_time,
            "types": types,
            "resolution": resolution,
            "limit": limit,
        }
        if cursor:
            params["cursor"] = cursor
        return await self._request("GET", f"/api/v1/users/{user_id}/timeseries", params=params)

    async def get_menstrual_cycles(
        self,
        user_id: str,
        start_date: str,
        end_date: str,
        limit: int = 100,
        cursor: str | None = None,
    ) -> dict[str, Any]:
        """
        Get menstrual cycle records for a user within a date range.

        Args:
            user_id: UUID of the user
            start_date: Start date (YYYY-MM-DD format)
            end_date: End date (YYYY-MM-DD format)
            limit: Page size (1-100)
            cursor: Opaque pagination cursor returned by a previous call

        Returns:
            Paginated response with menstrual cycle records
        """
        params: dict[str, Any] = {
            "start_date": start_date,
            "end_date": end_date,
            "limit": limit,
        }
        if cursor:
            params["cursor"] = cursor
        return await self._request("GET", f"/api/v1/users/{user_id}/events/menstrual-cycles", params=params)

    async def get_user_connections(self, user_id: str) -> list[dict[str, Any]]:
        """
        Get all provider connections for a user.

        Args:
            user_id: UUID of the user

        Returns:
            List of connection objects with status and provider capability metadata
        """
        response = await self._request("GET", f"/api/v1/users/{user_id}/connections")
        if isinstance(response, list):
            return response
        if isinstance(response, dict) and "data" in response:
            return response["data"]
        return []

    async def sync_provider_data(
        self,
        user_id: str,
        provider: str,
        data_type: str = "all",
        run_async: bool = True,
        summary_start_time: str | None = None,
        summary_end_time: str | None = None,
    ) -> dict[str, Any]:
        """
        Trigger a data synchronization for a user from a connected provider.

        Args:
            user_id: UUID of the user
            provider: Provider name (e.g., "garmin", "polar", "suunto", "whoop", "oura")
            data_type: "workouts", "247", or "all"
            run_async: Run sync asynchronously via Celery (default: True)
            summary_start_time: Optional activity start time (Unix timestamp or ISO 8601 date, Garmin only)
            summary_end_time: Optional activity end time (Unix timestamp or ISO 8601 date, Garmin only)

        Returns:
            Sync response containing task status or result
        """
        params: dict[str, Any] = {
            "data_type": data_type,
            "async": run_async,
        }
        if summary_start_time:
            params["summary_start_time"] = summary_start_time
        if summary_end_time:
            params["summary_end_time"] = summary_end_time

        return await self._request(
            "POST",
            f"/api/v1/providers/{provider}/users/{user_id}/sync",
            params=params,
        )

    async def sync_historical_data(
        self,
        user_id: str,
        provider: str,
        days: int = 90,
    ) -> dict[str, Any]:
        """
        Trigger a historical data sync for a user from a connected provider.

        Args:
            user_id: UUID of the user
            provider: Provider name (e.g., "garmin", "whoop", "oura")
            days: Days of historical data to fetch (1-365)

        Returns:
            Sync result details
        """
        params = {"days": days}
        return await self._request(
            "POST",
            f"/api/v1/providers/{provider}/users/{user_id}/sync/historical",
            params=params,
        )


# Singleton instance
client = OpenWearablesClient()
