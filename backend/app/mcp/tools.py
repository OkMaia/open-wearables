"""FastMCP tool definitions for Open Wearables in-process MCP server."""

from __future__ import annotations

import contextlib
import logging
from typing import Any, Literal
from uuid import UUID

from fastmcp import FastMCP
from fastmcp.server.context import Context

from app.database import SessionLocal
from app.integrations.celery.tasks import sync_vendor_data
from app.mcp.auth import McpAuthError, authenticate_context
from app.repositories.provider_settings_repository import ProviderSettingsRepository
from app.schemas.enums import Resolution, SeriesType, WorkoutType
from app.schemas.model_crud.activities import EventRecordQueryParams, TimeSeriesQueryParams, WorkoutInclude
from app.schemas.model_crud.user_management import UserQueryParams
from app.services.event_record_service import event_record_service
from app.services.providers.factory import ProviderFactory
from app.services.summaries_service import summaries_service
from app.services.timeseries_service import timeseries_service
from app.services.user_connection_service import user_connection_service
from app.services.user_service import user_service
from app.utils.dates import parse_query_datetime, parse_query_end_datetime
from app.utils.exceptions import UnsupportedProviderError

logger = logging.getLogger(__name__)
provider_factory = ProviderFactory()
provider_settings_repo = ProviderSettingsRepository()


def _parse_uuid(val: str, field_name: str = "user_id") -> UUID:
    try:
        return UUID(str(val).strip())
    except (ValueError, TypeError, AttributeError) as exc:
        raise ValueError(f"Invalid UUID for {field_name}: {val}") from exc


def register_tools(mcp: FastMCP) -> None:
    """Register all Open Wearables health and sync tools with the FastMCP instance."""

    @mcp.tool
    async def get_users(ctx: Context, search: str | None = None, limit: int = 10) -> dict[str, Any]:
        """Get users accessible via the configured API key."""
        try:
            authenticate_context(ctx)
        except McpAuthError as e:
            return {"error": str(e), "status_code": e.status_code, "users": [], "total": 0}

        with SessionLocal() as db:
            params = UserQueryParams(search=search, limit=limit)
            result = user_service.get_users_paginated(db, params)
            users = [
                {
                    "id": str(u.id),
                    "first_name": u.first_name,
                    "last_name": u.last_name,
                    "email": u.email,
                }
                for u in result.items
            ]
            return {
                "users": users,
                "total": result.total,
            }

    @mcp.tool
    async def list_user_connections(ctx: Context, user_id: str) -> dict[str, Any]:
        """List all connected wearable devices and provider services for a user."""
        try:
            authenticate_context(ctx)
            uid = _parse_uuid(user_id)
        except McpAuthError as e:
            return {"error": str(e), "status_code": e.status_code}
        except ValueError as e:
            return {"error": str(e)}

        with SessionLocal() as db:
            user = user_service.get(db, uid)
            if not user:
                return {"error": f"User not found: {user_id}"}

            connections = user_connection_service.get_connections_by_user(db, uid)
            settings_map = provider_settings_repo.get_all(db)

            result = []
            for c in connections:
                strategy = None
                with contextlib.suppress(Exception):
                    strategy = provider_factory.get_provider(c.provider)

                live_mode = None
                max_days = None
                if strategy:
                    caps = strategy.capabilities
                    max_days = caps.max_historical_days
                    setting = settings_map.get(c.provider)
                    live_mode = (
                        setting.live_sync_mode
                        if (setting and setting.live_sync_mode is not None)
                        else strategy.default_live_sync_mode
                    )

                result.append(
                    {
                        "provider": c.provider,
                        "status": c.status.value if hasattr(c.status, "value") else str(c.status),
                        "created_at": c.created_at.isoformat() if c.created_at else None,
                        "last_synced_at": c.last_synced_at.isoformat() if c.last_synced_at else None,
                        "live_sync_mode": str(live_mode) if live_mode else None,
                        "max_historical_days": max_days,
                    }
                )

            return {
                "user": {"id": str(user.id), "first_name": user.first_name, "last_name": user.last_name},
                "connections": result,
                "total": len(result),
            }

    @mcp.tool
    async def sync_provider_data(
        ctx: Context,
        user_id: str,
        provider: str,
        data_type: Literal["workouts", "247", "all"] = "all",
        run_async: bool = True,
    ) -> dict[str, Any]:
        """Trigger on-demand data synchronization from a connected wearable provider."""
        try:
            authenticate_context(ctx)
            uid = _parse_uuid(user_id)
        except McpAuthError as e:
            return {"error": str(e), "status_code": e.status_code}
        except ValueError as e:
            return {"error": str(e)}

        with SessionLocal() as db:
            user = user_service.get(db, uid)
            if not user:
                return {"error": f"User not found: {user_id}"}

            provider_norm = provider.lower().strip()
            conn = user_connection_service.get_connection(db, uid, provider_norm)
            if not conn:
                return {"error": f"User is not connected to provider: {provider_norm}"}

            # Enqueue pull sync task via Celery
            task = sync_vendor_data.delay(
                user_id=str(uid),
                start_date=None,
                end_date=None,
                providers=[provider_norm],
                is_historical=False,
            )

            return {
                "success": True,
                "provider": provider_norm,
                "user_id": str(uid),
                "status": "Sync task dispatched",
                "task_id": str(task.id) if task else None,
            }

    @mcp.tool
    async def sync_historical_data(
        ctx: Context,
        user_id: str,
        provider: str,
        days: int = 90,
    ) -> dict[str, Any]:
        """Trigger a historical backfill sync from a connected wearable provider."""
        try:
            authenticate_context(ctx)
            uid = _parse_uuid(user_id)
        except McpAuthError as e:
            return {"error": str(e), "status_code": e.status_code}
        except ValueError as e:
            return {"error": str(e)}

        with SessionLocal() as db:
            user = user_service.get(db, uid)
            if not user:
                return {"error": f"User not found: {user_id}"}

            provider_norm = provider.lower().strip()
            try:
                strategy = provider_factory.get_provider(provider_norm)
                result = strategy.start_historical_sync(uid, days)
                return {
                    "success": True,
                    "provider": provider_norm,
                    "user_id": str(uid),
                    "method": result.method,
                    "task_id": result.task_id,
                    "message": result.message,
                    **({"days": result.days} if result.days is not None else {}),
                }
            except UnsupportedProviderError as exc:
                return {"error": f"Provider does not support historical sync: {exc}"}
            except Exception as exc:
                return {"error": f"Historical sync failed: {exc}"}

    @mcp.tool
    async def get_activity_summary(
        ctx: Context,
        user_id: str,
        start_date: str,
        end_date: str,
    ) -> dict[str, Any]:
        """Get daily activity summaries for a user within a date range."""
        try:
            authenticate_context(ctx)
            uid = _parse_uuid(user_id)
        except McpAuthError as e:
            return {"error": str(e), "status_code": e.status_code}
        except ValueError as e:
            return {"error": str(e)}

        with SessionLocal() as db:
            user = user_service.get(db, uid)
            if not user:
                return {"error": f"User not found: {user_id}"}

            start_dt = parse_query_datetime(start_date)
            end_dt = parse_query_end_datetime(end_date)
            paginated = summaries_service.get_activity_summaries(
                db, uid, start_dt, end_dt, cursor=None, limit=100, sort_order="asc"
            )

            records = [item.model_dump(mode="json") for item in paginated.data]
            return {
                "user": {"id": str(user.id), "first_name": user.first_name, "last_name": user.last_name},
                "period": {"start": start_date, "end": end_date},
                "records": records,
                "total": len(records),
            }

    @mcp.tool
    async def get_sleep_summary(
        ctx: Context,
        user_id: str,
        start_date: str,
        end_date: str,
    ) -> dict[str, Any]:
        """Get daily sleep summaries for a user within a date range."""
        try:
            authenticate_context(ctx)
            uid = _parse_uuid(user_id)
        except McpAuthError as e:
            return {"error": str(e), "status_code": e.status_code}
        except ValueError as e:
            return {"error": str(e)}

        with SessionLocal() as db:
            user = user_service.get(db, uid)
            if not user:
                return {"error": f"User not found: {user_id}"}

            start_dt = parse_query_datetime(start_date)
            end_dt = parse_query_end_datetime(end_date)
            paginated = summaries_service.get_sleep_summaries(db, uid, start_dt, end_dt, cursor=None, limit=100)
            records = [item.model_dump(mode="json") for item in paginated.data]

            return {
                "user": {"id": str(user.id), "first_name": user.first_name, "last_name": user.last_name},
                "period": {"start": start_date, "end": end_date},
                "records": records,
                "total": len(records),
            }

    @mcp.tool
    async def get_workout_events(
        ctx: Context,
        user_id: str,
        start_date: str,
        end_date: str,
        workout_type: str | None = None,
    ) -> dict[str, Any]:
        """Get workout events for a user within a date range."""
        try:
            authenticate_context(ctx)
            uid = _parse_uuid(user_id)
        except McpAuthError as e:
            return {"error": str(e), "status_code": e.status_code}
        except ValueError as e:
            return {"error": str(e)}

        with SessionLocal() as db:
            user = user_service.get(db, uid)
            if not user:
                return {"error": f"User not found: {user_id}"}

            start_dt = parse_query_datetime(start_date)
            end_dt = parse_query_end_datetime(end_date)

            type_enum = None
            if workout_type:
                with contextlib.suppress(ValueError):
                    type_enum = WorkoutType(workout_type.lower().strip())

            event_params = EventRecordQueryParams(
                start_datetime=start_dt,
                end_datetime=end_dt,
                workout_type=type_enum,
                limit=100,
            )
            paginated = event_record_service.get_workouts(
                db,
                uid,
                event_params,
                include=[WorkoutInclude.ZONES, WorkoutInclude.SEGMENTS],
            )
            records = [item.model_dump(mode="json") for item in paginated.data]

            return {
                "user": {"id": str(user.id), "first_name": user.first_name, "last_name": user.last_name},
                "period": {"start": start_date, "end": end_date},
                "records": records,
                "total": len(records),
            }

    @mcp.tool
    async def get_timeseries(
        ctx: Context,
        user_id: str,
        start_time: str,
        end_time: str,
        types: list[str],
        resolution: str = "raw",
    ) -> dict[str, Any]:
        """Get granular time-series samples for a user within a time range."""
        try:
            authenticate_context(ctx)
            uid = _parse_uuid(user_id)
        except McpAuthError as e:
            return {"error": str(e), "status_code": e.status_code}
        except ValueError as e:
            return {"error": str(e)}

        with SessionLocal() as db:
            user = user_service.get(db, uid)
            if not user:
                return {"error": f"User not found: {user_id}"}

            series_types = []
            for t in types:
                try:
                    series_types.append(SeriesType(t.strip()))
                except ValueError:
                    continue

            res_enum = Resolution.RAW
            with contextlib.suppress(ValueError):
                res_enum = Resolution(resolution)

            params = TimeSeriesQueryParams(
                start_datetime=parse_query_datetime(start_time),
                end_datetime=parse_query_end_datetime(end_time),
                limit=100,
                resolution=res_enum,
            )
            paginated = timeseries_service.get_timeseries(db, uid, series_types, params)
            samples = [item.model_dump(mode="json") for item in paginated.data]

            return {
                "user": {"id": str(user.id), "first_name": user.first_name, "last_name": user.last_name},
                "period": {"start": start_time, "end": end_time, "resolution": resolution},
                "samples": samples,
                "total": len(samples),
            }
