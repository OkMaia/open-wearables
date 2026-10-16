"""Tests for StravaWorkouts normalization."""

from decimal import Decimal
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest

from app.schemas.enums import EntrySource, WorkoutIntensity
from app.schemas.providers.strava import ActivityJSON as StravaActivityJSON
from app.schemas.providers.strava import StravaGearJSON
from app.services.providers.strava.oauth import StravaOAuth
from app.services.providers.strava.workouts import StravaWorkouts


class TestStravaWorkoutsNormalization:
    """Test workout normalization."""

    @pytest.fixture
    def workouts(self) -> StravaWorkouts:
        oauth = StravaOAuth(
            user_repo=MagicMock(),
            connection_repo=MagicMock(),
            provider_name="strava",
            api_base_url="https://www.strava.com/api/v3",
        )
        return StravaWorkouts(
            workout_repo=MagicMock(),
            connection_repo=MagicMock(),
            provider_name="strava",
            api_base_url="https://www.strava.com/api/v3",
            oauth=oauth,
        )

    def _activity(self, manual: bool | None = None) -> StravaActivityJSON:
        return StravaActivityJSON(
            id=12345,
            name="Evening Ride",
            type="Ride",
            sport_type="Ride",
            start_date="2024-01-15T18:00:00Z",
            elapsed_time=3600,
            manual=manual,
        )

    def test_normalize_workout_manual_entry(self, workouts: StravaWorkouts) -> None:
        record, detail = workouts._normalize_workout(self._activity(manual=True), uuid4())

        assert record.source == "strava"
        assert detail.entry_source == EntrySource.MANUAL
        assert detail.label == "Evening Ride"

    def test_normalize_workout_auto_entry(self, workouts: StravaWorkouts) -> None:
        _, detail = workouts._normalize_workout(self._activity(manual=False), uuid4())

        assert detail.entry_source == EntrySource.AUTOMATIC

    def test_normalize_workout_unknown_entry_source(self, workouts: StravaWorkouts) -> None:
        _, detail = workouts._normalize_workout(self._activity(), uuid4())

        assert detail.entry_source is None

    def test_oversized_name_does_not_abort_the_batch(self, workouts: StravaWorkouts) -> None:
        """An overlong name is truncated so the surrounding activities still import."""
        activities = [
            self._activity(manual=False),
            StravaActivityJSON(
                id=999,
                name="x" * 400,
                type="Ride",
                sport_type="Ride",
                start_date="2024-01-15T18:00:00Z",
                elapsed_time=3600,
                manual=False,
            ),
            self._activity(manual=True),
        ]

        details = [workouts._normalize_workout(a, uuid4())[1] for a in activities]

        assert len(details) == 3
        assert details[1].label == "x" * 255
        assert details[2].entry_source == EntrySource.MANUAL

    def test_normalize_workout_with_average_cadence(self, workouts: StravaWorkouts) -> None:
        activity = StravaActivityJSON(
            id=1001,
            name="Morning Run",
            type="Run",
            sport_type="Run",
            start_date="2024-01-15T08:00:00Z",
            elapsed_time=1800,
            average_cadence=172.5,
        )
        _, detail = workouts._normalize_workout(activity, uuid4())
        assert detail.average_cadence == Decimal("172.5")

    def test_normalize_workout_cadence_from_laps(self, workouts: StravaWorkouts) -> None:
        activity = StravaActivityJSON(
            id=1002,
            name="Interval Run",
            type="Run",
            sport_type="Run",
            start_date="2024-01-15T08:00:00Z",
            elapsed_time=2000,
            laps=[
                {"average_cadence": 160.0, "moving_time": 600},
                {"average_cadence": 180.0, "moving_time": 600},
            ],
        )
        _, detail = workouts._normalize_workout(activity, uuid4())
        assert detail.average_cadence == Decimal("170.0")

    def test_normalize_workout_with_segments(self, workouts: StravaWorkouts) -> None:
        activity = StravaActivityJSON(
            id=1003,
            name="Tempo Run",
            type="Run",
            sport_type="Run",
            start_date="2024-01-15T08:00:00Z",
            elapsed_time=3600,
            laps=[
                {
                    "lap_index": 1,
                    "name": "Lap 1",
                    "elapsed_time": 300,
                    "distance": 1000.0,
                    "average_speed": 3.33,
                    "average_cadence": 170.0,
                    "average_heartrate": 150.0,
                }
            ],
            splits_metric=[
                {
                    "split": 1,
                    "elapsed_time": 300,
                    "distance": 1000.0,
                    "average_speed": 3.33,
                    "elevation_difference": 5.0,
                    "pace_zone": 2,
                }
            ],
        )
        _, detail = workouts._normalize_workout(activity, uuid4())
        assert detail.segments is not None
        assert len(detail.segments) == 2
        lap_seg = detail.segments[0]
        assert lap_seg["kind"] == "lap"
        assert lap_seg["name"] == "Lap 1"
        assert lap_seg["avg_cadence"] == 170.0
        assert lap_seg["avg_heart_rate"] == 150.0

        split_seg = detail.segments[1]
        assert split_seg["kind"] == "split"
        assert split_seg["index"] == 1
        assert split_seg["elevation_difference"] == 5.0
        assert split_seg["pace_zone"] == 2

    def test_parse_activity_zones(self, workouts: StravaWorkouts) -> None:
        raw_zones = [
            {
                "type": "heartrate",
                "max": 190,
                "distribution_buckets": [
                    {"min": 0, "max": 120, "time": 100},
                    {"min": 120, "max": 150, "time": 300},
                    {"min": 150, "max": 175, "time": 600},
                    {"min": 175, "max": -1, "time": 200},
                ],
            },
            {
                "type": "power",
                "distribution_buckets": [
                    {"min": 0, "max": 150, "time": 250},
                    {"min": 150, "max": 250, "time": 500},
                ],
            },
        ]
        hr_zones, power_zones = workouts._parse_activity_zones(raw_zones)
        assert hr_zones is not None
        assert hr_zones.max_hr == 190
        assert len(hr_zones.zones) == 4
        assert hr_zones.zones[0].seconds == 100.0
        assert hr_zones.zones[0].max_bpm == 120
        assert hr_zones.zones[3].max_bpm is None

        assert power_zones is not None
        assert len(power_zones.zones) == 2
        assert power_zones.zones[1].max_watts == 250

    def test_fetch_workout_zones_skips_when_no_hr_or_power(self, workouts: StravaWorkouts) -> None:
        activity = self._activity()
        db = MagicMock()
        hr_zones, power_zones = workouts._fetch_workout_zones(db, uuid4(), activity)
        assert hr_zones is None
        assert power_zones is None

    def test_load_data_fetches_detail_when_calories_none(self, workouts: StravaWorkouts) -> None:
        db = MagicMock()
        user_id = uuid4()

        summary_activity = {
            "id": 55555,
            "name": "Summary Run",
            "type": "Run",
            "sport_type": "Run",
            "start_date": "2024-01-15T08:00:00Z",
            "elapsed_time": 1800,
            "calories": None,
            "laps": None,
        }

        detailed_activity = {
            "id": 55555,
            "name": "Summary Run",
            "type": "Run",
            "sport_type": "Run",
            "start_date": "2024-01-15T08:00:00Z",
            "elapsed_time": 1800,
            "calories": 250.0,
            "average_cadence": 165.0,
            "laps": [
                {
                    "lap_index": 1,
                    "elapsed_time": 1800,
                    "distance": 5000.0,
                }
            ],
        }

        with (
            patch.object(workouts, "get_workouts", return_value=[summary_activity]),
            patch.object(workouts, "get_workout_detail_from_api", return_value=detailed_activity) as mock_detail,
            patch.object(workouts, "_fetch_workout_zones", return_value=(None, None)),
            patch("app.services.providers.strava.workouts.event_record_service") as mock_event_service,
            patch.object(workouts, "_ingest_workout_streams"),
        ):
            mock_record = MagicMock()
            mock_record.id = uuid4()
            mock_event_service.create.return_value = mock_record

            count = workouts.load_data(db, user_id)

            assert count == 1
            mock_detail.assert_called_once_with(db, user_id, "55555")
            created_detail = mock_event_service.create_detail.call_args[0][1]
            assert created_detail.energy_burned == Decimal("250.0")
            assert created_detail.average_cadence == Decimal("165.0")
            assert created_detail.segments is not None
            assert len(created_detail.segments) == 1

    def test_normalize_workout_intensity_from_perceived_exertion(self, workouts: StravaWorkouts) -> None:
        activity_low = StravaActivityJSON(
            id=101,
            name="Easy Walk",
            type="Walk",
            sport_type="Walk",
            start_date="2024-01-15T08:00:00Z",
            elapsed_time=1200,
            perceived_exertion=2,
        )
        _, detail_low = workouts._normalize_workout(activity_low, uuid4())
        assert detail_low.intensity == WorkoutIntensity.LOW

        activity_hard = StravaActivityJSON(
            id=102,
            name="Hard Run",
            type="Run",
            sport_type="Run",
            start_date="2024-01-15T08:00:00Z",
            elapsed_time=1200,
            perceived_exertion=8,
        )
        _, detail_hard = workouts._normalize_workout(activity_hard, uuid4())
        assert detail_hard.intensity == WorkoutIntensity.HIGH

    def test_normalize_workout_overview_and_gear(self, workouts: StravaWorkouts) -> None:
        activity = StravaActivityJSON(
            id=201,
            name="Morning Run",
            type="Run",
            sport_type="Run",
            start_date="2024-01-15T08:00:00Z",
            elapsed_time=3600,
            suffer_score=85,
            average_temp=22,
            perceived_exertion=7,
            description="Good pace on trails",
            gear=StravaGearJSON(name="Nike Pegasus 40", distance=150000),
            map={"summary_polyline": "abcdef12345"},
        )
        _, detail = workouts._normalize_workout(activity, uuid4())
        assert detail.intensity == WorkoutIntensity.HIGH
        assert detail.segments is not None
        overview = next((s for s in detail.segments if s.get("kind") == "overview"), None)
        assert overview is not None
        assert overview["suffer_score"] == 85.0
        assert overview["perceived_exertion"] == 7.0
        assert overview["average_temp"] == 22.0
        assert overview["gear_name"] == "Nike Pegasus 40"
        assert overview["gear_distance_meters"] == 150000.0
        assert overview["summary_polyline"] == "abcdef12345"
        assert overview["description"] == "Good pace on trails"

    def test_normalize_workout_strength_summary(self, workouts: StravaWorkouts) -> None:
        activity = StravaActivityJSON(
            id=301,
            name="Musculação matinal",
            type="WeightTraining",
            sport_type="WeightTraining",
            start_date="2024-01-15T08:00:00Z",
            elapsed_time=2400,
            laps=[
                {"elapsed_time": 40, "moving_time": 40},
                {"elapsed_time": 60, "moving_time": 60},
                {"elapsed_time": 45, "moving_time": 45},
                {"elapsed_time": 75, "moving_time": 75},
            ],
        )
        _, detail = workouts._normalize_workout(activity, uuid4())
        assert detail.segments is not None
        strength_summary = next((s for s in detail.segments if s.get("kind") == "strength_summary"), None)
        assert strength_summary is not None
        assert strength_summary["total_sets"] == 2
        assert strength_summary["total_laps"] == 4
        assert strength_summary["work_time_seconds"] == 85.0
        assert strength_summary["rest_time_seconds"] == 135.0
        assert strength_summary["avg_rest_seconds"] == 67.5
