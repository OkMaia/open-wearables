from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

from app.config import settings
from app.constants.entry_source import get_unified_strava_entry_source
from app.constants.workout_types import get_unified_strava_workout_type
from app.database import DbSession
from app.schemas.enums import SeriesType, WorkoutType
from app.schemas.model_crud.activities import (
    EventRecordCreate,
    EventRecordDetailCreate,
    EventRecordMetrics,
    TimeSeriesSampleCreate,
)
from app.schemas.model_crud.activities.zones import HRZone, HRZones, PowerZone, PowerZones
from app.schemas.providers.strava import (
    ActivityJSON as StravaActivityJSON,
)
from app.schemas.providers.strava import (
    StravaStreamSet,
)
from app.services.event_record_service import event_record_service
from app.services.providers.strava.coverage import STREAM_KEY_SERIES_TYPE, STREAM_KEYS_PARAM
from app.services.providers.templates.base_workouts import BaseWorkoutsTemplate
from app.services.timeseries_service import timeseries_service
from app.utils.conversion import kilojoules_to_kcal
from app.utils.dates import offset_to_iso
from app.utils.sentry_helpers import log_and_capture_error
from app.utils.structured_logging import log_structured


class StravaWorkouts(BaseWorkoutsTemplate):
    """Strava implementation of workouts template."""

    @property
    def events_per_page(self) -> int:
        """Get the number of events per page."""
        return settings.strava_events_per_page

    def get_workouts(
        self,
        db: DbSession,
        user_id: UUID,
        start_date: datetime,
        end_date: datetime,
    ) -> list[Any]:
        """Get activities from Strava API with page-based pagination.

        Strava API uses epoch timestamps for after/before parameters
        and supports up to 200 activities per page.
        """
        all_activities: list[Any] = []
        page = 1
        per_page = self.events_per_page

        after = int(start_date.timestamp())
        before = int(end_date.timestamp())

        while True:
            params: dict[str, Any] = {
                "after": after,
                "before": before,
                "page": page,
                "per_page": per_page,
            }

            try:
                response = self._make_api_request(
                    db,
                    user_id,
                    # hard-coded value - update with base template changes
                    "/api/v3/athlete/activities",
                    params=params,
                )

                if not isinstance(response, list):
                    break

                all_activities.extend(response)

                # Stop if fewer results than page size (last page)
                if len(response) < per_page:
                    break

                page += 1

            except Exception as e:
                log_structured(
                    self.logger,
                    "error",
                    "Error fetching Strava activities page",
                    provider="strava",
                    action="strava_fetch_page_error",
                    page=page,
                    user_id=str(user_id),
                    error=str(e),
                )
                if all_activities:
                    log_structured(
                        self.logger,
                        "warning",
                        "Returning partial activity data due to error",
                        provider="strava",
                        action="strava_partial_data",
                        activities_count=len(all_activities),
                        user_id=str(user_id),
                        error=str(e),
                    )
                    break
                raise

        return all_activities

    def get_workouts_from_api(self, db: DbSession, user_id: UUID, **kwargs: Any) -> Any:
        """Get activities from Strava API with specific options."""
        page = kwargs.get("page", 1)
        per_page = self.events_per_page

        params: dict[str, Any] = {
            "page": page,
            "per_page": per_page,
        }

        after = kwargs.get("after")
        before = kwargs.get("before")
        if after:
            params["after"] = int(after)
        if before:
            params["before"] = int(before)

        # hard-coded value - update with base template changes
        return self._make_api_request(db, user_id, "/api/v3/athlete/activities", params=params)

    def get_workout_detail_from_api(self, db: DbSession, user_id: UUID, workout_id: str, **kwargs: Any) -> Any:
        """Get detailed activity data from Strava API."""
        # hard-coded value - update with base template changes
        return self._make_api_request(db, user_id, f"/api/v3/activities/{workout_id}")

    def _extract_dates_from_iso(self, start_iso: str, elapsed_time: int) -> tuple[datetime, datetime]:
        """Extract start and end dates from ISO string and elapsed time."""
        start_date = datetime.fromisoformat(start_iso.replace("Z", "+00:00"))
        if start_date.tzinfo is None:
            start_date = start_date.replace(tzinfo=timezone.utc)
        end_date = start_date + timedelta(seconds=elapsed_time)
        return start_date, end_date

    def _build_metrics(self, raw_workout: StravaActivityJSON) -> EventRecordMetrics:
        """Build metrics from Strava activity data."""
        metrics: EventRecordMetrics = {}

        # Heart rate
        if raw_workout.average_heartrate is not None:
            metrics["heart_rate_avg"] = Decimal(raw_workout.average_heartrate)
        if raw_workout.max_heartrate is not None:
            metrics["heart_rate_max"] = int(raw_workout.max_heartrate)

        # Distance (meters)
        if raw_workout.distance is not None:
            metrics["distance"] = Decimal(raw_workout.distance)

        # Speed (m/s)
        if raw_workout.average_speed is not None:
            metrics["average_speed"] = Decimal(raw_workout.average_speed)
        if raw_workout.max_speed is not None:
            metrics["max_speed"] = Decimal(raw_workout.max_speed)

        # Cadence (rpm)
        if raw_workout.average_cadence is not None:
            metrics["average_cadence"] = Decimal(str(raw_workout.average_cadence))
        elif raw_workout.laps:
            cadence_laps = [
                (float(lap["average_cadence"]), float(lap.get("moving_time") or lap.get("elapsed_time") or 1))
                for lap in raw_workout.laps
                if lap.get("average_cadence") is not None
            ]
            if cadence_laps:
                total_time = sum(t for _, t in cadence_laps)
                if total_time > 0:
                    avg_cadence = sum(c * t for c, t in cadence_laps) / total_time
                    metrics["average_cadence"] = Decimal(str(round(avg_cadence, 2)))

        # Power (watts)
        if raw_workout.average_watts is not None:
            metrics["average_watts"] = Decimal(raw_workout.average_watts)
        if raw_workout.max_watts is not None:
            metrics["max_watts"] = Decimal(raw_workout.max_watts)

        # Elevation
        if raw_workout.total_elevation_gain is not None:
            metrics["total_elevation_gain"] = Decimal(raw_workout.total_elevation_gain)
        if raw_workout.elev_high is not None:
            metrics["elev_high"] = Decimal(raw_workout.elev_high)
        if raw_workout.elev_low is not None:
            metrics["elev_low"] = Decimal(raw_workout.elev_low)

        # Energy: prefer calories (if available and non-zero), fallback to kilojoules.
        # Strava's list endpoint often returns calories=None, so we fall back to kilojoules.
        # Standard exercise approximation: kcal ≈ kJ (human efficiency ~25% cancels the unit factor).
        if raw_workout.calories is not None and raw_workout.calories > 0:
            metrics["energy_burned"] = Decimal(raw_workout.calories)
        elif raw_workout.kilojoules is not None:
            metrics["energy_burned"] = kilojoules_to_kcal(raw_workout.kilojoules)

        # Moving time
        if raw_workout.moving_time is not None:
            metrics["moving_time_seconds"] = raw_workout.moving_time

        entry_source = get_unified_strava_entry_source(raw_workout.manual)
        if entry_source is not None:
            metrics["entry_source"] = entry_source

        if raw_workout.name:
            metrics["label"] = raw_workout.name

        return metrics

    def _build_segments(self, raw_workout: StravaActivityJSON) -> list[dict[str, Any]] | None:
        """Extract laps and metric splits as workout segments."""
        segments: list[dict[str, Any]] = []

        if raw_workout.laps:
            for idx, lap in enumerate(raw_workout.laps):
                seg: dict[str, Any] = {
                    "kind": "lap",
                    "index": lap.get("lap_index") if lap.get("lap_index") is not None else idx,
                }
                if lap.get("name"):
                    seg["name"] = str(lap["name"])
                if lap.get("start_date"):
                    seg["start_time"] = str(lap["start_date"])
                if lap.get("elapsed_time") is not None:
                    seg["elapsed_seconds"] = float(lap["elapsed_time"])
                if lap.get("moving_time") is not None:
                    seg["moving_time_seconds"] = float(lap["moving_time"])
                if lap.get("distance") is not None:
                    seg["distance_meters"] = float(lap["distance"])
                if lap.get("average_speed") is not None:
                    seg["avg_speed"] = float(lap["average_speed"])
                if lap.get("max_speed") is not None:
                    seg["max_speed"] = float(lap["max_speed"])
                if lap.get("average_cadence") is not None:
                    seg["avg_cadence"] = float(lap["average_cadence"])
                if lap.get("average_heartrate") is not None:
                    seg["avg_heart_rate"] = float(lap["average_heartrate"])
                if lap.get("max_heartrate") is not None:
                    seg["max_heart_rate"] = float(lap["max_heartrate"])
                if lap.get("average_watts") is not None:
                    seg["avg_power"] = float(lap["average_watts"])
                if lap.get("total_elevation_gain") is not None:
                    seg["total_elevation_gain"] = float(lap["total_elevation_gain"])

                dist = seg.get("distance_meters")
                sec = seg.get("moving_time_seconds") or seg.get("elapsed_seconds")
                if dist and sec and dist > 0:
                    seg["pace_sec_per_km"] = round(sec / (dist / 1000), 1)

                segments.append(seg)

        if raw_workout.splits_metric:
            for idx, split in enumerate(raw_workout.splits_metric):
                seg = {
                    "kind": "split",
                    "index": split.get("split") if split.get("split") is not None else idx,
                }
                if split.get("elapsed_time") is not None:
                    seg["elapsed_seconds"] = float(split["elapsed_time"])
                if split.get("moving_time") is not None:
                    seg["moving_time_seconds"] = float(split["moving_time"])
                if split.get("distance") is not None:
                    seg["distance_meters"] = float(split["distance"])
                if split.get("average_speed") is not None:
                    seg["avg_speed"] = float(split["average_speed"])
                if split.get("elevation_difference") is not None:
                    seg["elevation_difference"] = float(split["elevation_difference"])
                if split.get("pace_zone") is not None:
                    seg["pace_zone"] = int(split["pace_zone"])
                if split.get("average_heartrate") is not None:
                    seg["avg_heart_rate"] = float(split["average_heartrate"])

                dist = seg.get("distance_meters")
                sec = seg.get("moving_time_seconds") or seg.get("elapsed_seconds")
                if dist and sec and dist > 0:
                    seg["pace_sec_per_km"] = round(sec / (dist / 1000), 1)

                segments.append(seg)

        if raw_workout.best_efforts:
            for idx, effort in enumerate(raw_workout.best_efforts):
                raw_dist = effort.get("distance")
                dist = float(raw_dist) if raw_dist is not None else None
                raw_sec = effort.get("elapsed_time") or effort.get("moving_time") or 0
                sec = float(raw_sec)
                seg = {
                    "kind": "best_effort",
                    "index": idx,
                    "name": str(effort.get("name") or f"Effort {idx}"),
                    "distance_meters": dist,
                    "elapsed_seconds": sec,
                }
                if effort.get("start_date"):
                    seg["start_time"] = str(effort["start_date"])
                if effort.get("pr_rank") is not None:
                    seg["pr_rank"] = int(effort["pr_rank"])
                if dist and sec and dist > 0:
                    seg["pace_sec_per_km"] = round(sec / (dist / 1000), 1)
                segments.append(seg)

        return segments if segments else None

    def _parse_activity_zones(self, raw_zones: list[dict[str, Any]]) -> tuple[HRZones | None, PowerZones | None]:
        """Parse raw Strava activity zones response into HRZones and PowerZones."""
        hr_zones: HRZones | None = None
        power_zones: PowerZones | None = None

        for item in raw_zones:
            if not isinstance(item, dict):
                continue
            zone_type = item.get("type")
            buckets = item.get("distribution_buckets")
            if not isinstance(buckets, list):
                continue

            if zone_type == "heartrate":
                parsed_hr: list[HRZone] = []
                for i, b in enumerate(buckets):
                    if not isinstance(b, dict):
                        continue
                    time_secs = float(b.get("time") or 0)
                    max_bpm = b.get("max")
                    if max_bpm is not None and max_bpm < 0:
                        max_bpm = None
                    parsed_hr.append(HRZone(zone=i, seconds=time_secs, max_bpm=max_bpm))
                if parsed_hr:
                    max_hr = item.get("max")
                    hr_zones = HRZones(
                        zones=parsed_hr,
                        max_hr=int(max_hr) if max_hr is not None and max_hr > 0 else None,
                    )

            elif zone_type == "power":
                parsed_power: list[PowerZone] = []
                for i, b in enumerate(buckets):
                    if not isinstance(b, dict):
                        continue
                    time_secs = float(b.get("time") or 0)
                    max_watts = b.get("max")
                    if max_watts is not None and max_watts < 0:
                        max_watts = None
                    parsed_power.append(PowerZone(zone=i, seconds=time_secs, max_watts=max_watts))
                if parsed_power:
                    power_zones = PowerZones(zones=parsed_power)

        return hr_zones, power_zones

    def _fetch_workout_zones(
        self,
        db: DbSession,
        user_id: UUID,
        activity: StravaActivityJSON,
    ) -> tuple[HRZones | None, PowerZones | None]:
        """Fetch heart rate and power zones from Strava API if available."""
        has_hr = bool(activity.has_heartrate or activity.average_heartrate)
        has_power = bool(activity.device_watts or activity.average_watts)
        if not (has_hr or has_power):
            return None, None

        try:
            raw = self._make_api_request(
                db,
                user_id,
                f"/api/v3/activities/{activity.id}/zones",
            )
            if isinstance(raw, list):
                return self._parse_activity_zones(raw)
        except Exception as exc:
            log_structured(
                self.logger,
                "debug",
                "Could not fetch Strava activity zones",
                provider="strava",
                action="strava_fetch_zones_failed",
                activity_id=str(activity.id),
                user_id=str(user_id),
                error=str(exc),
            )
        return None, None

    def _normalize_workout(
        self,
        raw_workout: StravaActivityJSON,
        user_id: UUID,
        hr_zones: HRZones | None = None,
        power_zones: PowerZones | None = None,
    ) -> tuple[EventRecordCreate, EventRecordDetailCreate]:
        """Normalize Strava activity to EventRecordCreate and EventRecordDetailCreate."""
        workout_id = uuid4()

        # Use sport_type for more specific mapping, fallback to type
        workout_type = get_unified_strava_workout_type(raw_workout.sport_type)
        if workout_type is WorkoutType.OTHER:
            workout_type = get_unified_strava_workout_type(raw_workout.type)

        duration_seconds = raw_workout.elapsed_time
        start_date, end_date = self._extract_dates_from_iso(raw_workout.start_date, duration_seconds)

        zone_offset = None
        if raw_workout.utc_offset is not None:
            zone_offset = offset_to_iso(int(raw_workout.utc_offset))

        metrics = self._build_metrics(raw_workout)
        segments = self._build_segments(raw_workout)

        source_name = raw_workout.device_name or "Strava"
        device_model = raw_workout.device_name or ""

        record = EventRecordCreate(
            category="workout",
            type=workout_type.value,
            source_name=source_name,
            device_model=device_model,
            duration_seconds=duration_seconds,
            start_datetime=start_date,
            end_datetime=end_date,
            zone_offset=zone_offset,
            id=workout_id,
            external_id=str(raw_workout.id),
            source="strava",
            user_id=user_id,
        )

        detail = EventRecordDetailCreate(
            record_id=workout_id,
            segments=segments,
            hr_zones=hr_zones,
            power_zones=power_zones,
            **metrics,
        )

        return record, detail

    def _build_workout_samples(
        self,
        db: DbSession,
        user_id: UUID,
        strava_activity_id: int | str,
        start_dt: datetime,
        zone_offset: str | None,
        device_model: str | None,
    ) -> list[TimeSeriesSampleCreate]:
        """Fetch full-fidelity Strava streams and normalize to TimeSeriesSampleCreate rows."""
        raw = self._make_api_request(
            db,
            user_id,
            f"/api/v3/activities/{strava_activity_id}/streams",
            params={"keys": STREAM_KEYS_PARAM, "key_by_type": "true"},
        )

        # key_by_type=true returns an object keyed by stream type, not a list.
        if not isinstance(raw, dict):
            return []

        streams = StravaStreamSet.model_validate(raw)

        time_data = streams.time.data if streams.time else []
        if not time_data:
            return []

        mapped: list[tuple[list[Any], SeriesType]] = []
        for key, series_type in STREAM_KEY_SERIES_TYPE.items():
            stream = getattr(streams, key)
            if stream and stream.data:
                mapped.append((stream.data, series_type))

        if not mapped:
            return []

        result: list[TimeSeriesSampleCreate] = []
        for i, offset in enumerate(time_data):
            if offset is None:
                continue
            recorded_at = start_dt + timedelta(seconds=int(offset))
            for data, series_type in mapped:
                if i >= len(data):
                    continue
                value = data[i]
                if value is None:
                    continue
                result.append(
                    TimeSeriesSampleCreate(
                        id=uuid4(),
                        user_id=user_id,
                        source="strava",
                        device_model=device_model,
                        recorded_at=recorded_at,
                        zone_offset=zone_offset,
                        value=Decimal(str(value)),
                        series_type=series_type,
                    )
                )
        return result

    def _ingest_workout_streams(
        self,
        db: DbSession,
        activity: StravaActivityJSON,
        user_id: UUID,
        record: EventRecordCreate,
    ) -> int:
        """Fetch + persist per-sample streams on workout arrival, flag-gated and failure-isolated."""
        if not settings.ingest_workout_samples:
            return 0
        if activity.manual:
            return 0
        try:
            samples = self._build_workout_samples(
                db,
                user_id,
                activity.id,
                record.start_datetime,
                record.zone_offset,
                activity.device_name or "",
            )
        except Exception as exc:
            if getattr(exc, "status_code", None) == 404 or "404" in str(exc):
                log_structured(
                    self.logger,
                    "debug",
                    "Strava activity has no streams (404), skipping samples",
                    provider="strava",
                    action="strava_streams_not_found",
                    activity_id=str(activity.id),
                )
                return 0
            log_and_capture_error(
                exc,
                self.logger,
                "Failed to fetch Strava workout streams, skipping samples",
                extra={"activity_id": activity.id},
            )
            return 0
        if not samples:
            return 0
        # Savepoint so a failed bulk insert rolls back only the samples and
        # leaves the workout's outer transaction usable (no PendingRollbackError).
        nested = db.begin_nested()
        try:
            timeseries_service.bulk_create_samples(db, samples)
            nested.commit()
            return len(samples)
        except Exception as exc:
            nested.rollback()
            log_and_capture_error(
                exc,
                self.logger,
                "Strava workout sample ingestion failed; continuing",
                extra={"activity_id": activity.id, "sample_count": len(samples)},
            )
            return 0

    def load_data(
        self,
        db: DbSession,
        user_id: UUID,
        **kwargs: Any,
    ) -> int:
        """Load data from Strava API (historical backfill).

        Fetches all activities in a date range using page-based pagination.
        """
        # Get start/end dates from kwargs
        start = kwargs.get("start") or kwargs.get("start_date")
        end = kwargs.get("end") or kwargs.get("end_date")

        # Default to last 30 days if no dates provided
        if not start:
            start_dt = datetime.now(timezone.utc) - timedelta(days=30)
        elif isinstance(start, datetime):
            start_dt = start
        elif isinstance(start, str):
            start_dt = datetime.fromisoformat(start.replace("Z", "+00:00"))
        else:
            start_dt = datetime.now(timezone.utc) - timedelta(days=30)

        if not end:
            end_dt = datetime.now(timezone.utc)
        elif isinstance(end, datetime):
            end_dt = end
        elif isinstance(end, str):
            end_dt = datetime.fromisoformat(end.replace("Z", "+00:00"))
        else:
            end_dt = datetime.now(timezone.utc)

        # Fetch all activities
        raw_activities = self.get_workouts(db, user_id, start_dt, end_dt)

        # Parse and save
        parsed_activities = []
        for raw in raw_activities:
            try:
                activity = StravaActivityJSON(**raw) if isinstance(raw, dict) else raw
                parsed_activities.append(activity)
            except Exception as e:
                log_structured(
                    self.logger,
                    "warning",
                    "Failed to parse Strava activity",
                    provider="strava",
                    action="strava_parse_error",
                    user_id=str(user_id),
                    error=str(e),
                )

        count = 0
        for activity in parsed_activities:
            # If the activity came from the summary list, attempt to fetch the detailed activity
            # so calories, laps, and splits are populated. Fall back to summary on error.
            detailed_activity = activity
            if activity.calories is None or activity.laps is None:
                try:
                    raw_detail = self.get_workout_detail_from_api(db, user_id, str(activity.id))
                    if isinstance(raw_detail, dict):
                        detailed_activity = StravaActivityJSON(**raw_detail)
                except Exception as e:
                    log_structured(
                        self.logger,
                        "debug",
                        "Could not fetch detailed Strava activity, using summary",
                        provider="strava",
                        action="strava_fetch_detail_fallback",
                        activity_id=str(activity.id),
                        user_id=str(user_id),
                        error=str(e),
                    )

            hr_zones, power_zones = self._fetch_workout_zones(db, user_id, detailed_activity)
            record, detail = self._normalize_workout(
                detailed_activity, user_id, hr_zones=hr_zones, power_zones=power_zones
            )
            created_record = event_record_service.create(db, record)
            detail_for_record = detail.model_copy(update={"record_id": created_record.id})
            event_record_service.create_detail(db, detail_for_record)
            count += 1
            self._ingest_workout_streams(db, detailed_activity, user_id, record)

        return count

    def process_push_activity(
        self,
        db: DbSession,
        activity: StravaActivityJSON,
        user_id: UUID,
    ) -> list[UUID]:
        """Process a single activity from webhook and save to database.

        Args:
            db: Database session
            activity: Parsed Strava activity data
            user_id: Internal user ID (already mapped from Strava athlete ID)

        Returns:
            List of created event record IDs
        """
        created_ids: list[UUID] = []

        hr_zones, power_zones = self._fetch_workout_zones(db, user_id, activity)
        record, detail = self._normalize_workout(activity, user_id, hr_zones=hr_zones, power_zones=power_zones)
        created_record = event_record_service.create(db, record)
        detail_for_record = detail.model_copy(update={"record_id": created_record.id})
        event_record_service.create_detail(db, detail_for_record)
        created_ids.append(created_record.id)
        self._ingest_workout_streams(db, activity, user_id, record)

        return created_ids
