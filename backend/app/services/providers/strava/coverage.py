from app.schemas.enums import SeriesType
from app.schemas.enums.health_score_category import HealthScoreCategory

# (/api/v3/activities/{id}/streams)
# time not included since it only defines offset
STREAM_KEY_SERIES_TYPE: dict[str, SeriesType] = {
    "heartrate": SeriesType.heart_rate,
    "velocity_smooth": SeriesType.speed,
    "cadence": SeriesType.cadence,
    "watts": SeriesType.power,
    "altitude": SeriesType.elevation,
    "temp": SeriesType.air_temperature,
}

# Value for the Strava streams `keys` query param: time axis first, then every metric.
STREAM_KEYS_PARAM: str = ",".join(["time", *STREAM_KEY_SERIES_TYPE])

# Workout-context only, gated by settings.ingest_workout_samples.
TIMESERIES: frozenset[SeriesType] = frozenset(
    STREAM_KEY_SERIES_TYPE.values(),  # /api/v3/activities/{id}/streams
)

# EventRecordDetail fields populated by workouts.py from workout records
# (/api/v3/athlete/activities + /api/v3/activities/{id}).
WORKOUT_FIELDS: frozenset[str] = frozenset(
    {
        "average_cadence",
        "average_speed",
        "average_watts",
        "distance",
        "elev_high",
        "elev_low",
        "energy_burned",
        "entry_source",
        "heart_rate_avg",
        "heart_rate_max",
        "hr_zones",
        "intensity",
        "label",
        "max_speed",
        "max_watts",
        "moving_time_seconds",
        "power_zones",
        "segments",
        "total_elevation_gain",
    }
)

SLEEP_FIELDS: frozenset[str] = frozenset()

HEALTH_SCORES: frozenset[HealthScoreCategory] = frozenset()
