"""Collection-date helpers for persisted airfare observations."""

from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

from backend.app.core.config import settings


def collection_timezone() -> ZoneInfo:
    """Returns the configured daily collection timezone."""
    return ZoneInfo(settings.DAILY_COLLECTION_TIMEZONE)


def collection_date_from_timestamp(value: datetime) -> date:
    """Maps an observation timestamp to the configured local collection date."""
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(collection_timezone()).date()


def collection_day_bounds_utc(collection_date: date) -> tuple[datetime, datetime]:
    """Returns UTC timestamp bounds for one configured local collection date."""
    tz = collection_timezone()
    start_local = datetime.combine(collection_date, time.min, tzinfo=tz)
    end_local = datetime.combine(collection_date + timedelta(days=1), time.min, tzinfo=tz)
    return start_local.astimezone(timezone.utc), end_local.astimezone(timezone.utc)
