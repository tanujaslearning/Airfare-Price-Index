"""APScheduler wiring for daily controlled LIVE airfare collection."""

import logging
from datetime import date, datetime
from typing import Optional, Sequence
from zoneinfo import ZoneInfo

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from backend.app.core.config import settings
from backend.app.db.session import SessionLocal
from backend.app.services.daily_collection_service import DailyCollectionResult, run_daily_collection

logger = logging.getLogger("apix.scheduler.daily")


def parse_daily_collection_time(value: str) -> tuple[int, int]:
    """Parses HH:MM daily collection time."""
    parts = value.strip().split(":")
    if len(parts) != 2:
        raise ValueError("DAILY_COLLECTION_TIME must use HH:MM format.")
    hour = int(parts[0])
    minute = int(parts[1])
    if hour < 0 or hour > 23 or minute < 0 or minute > 59:
        raise ValueError("DAILY_COLLECTION_TIME must be a valid 24-hour HH:MM time.")
    return hour, minute


def create_daily_collection_scheduler(
    *,
    collection_time: Optional[str] = None,
    timezone_name: Optional[str] = None,
    source_keys: Optional[Sequence[str]] = None,
) -> AsyncIOScheduler:
    """Creates a stopped scheduler with one daily collection job."""
    time_value = collection_time or settings.DAILY_COLLECTION_TIME
    tz_value = timezone_name or settings.DAILY_COLLECTION_TIMEZONE
    hour, minute = parse_daily_collection_time(time_value)
    timezone = ZoneInfo(tz_value)

    scheduler = AsyncIOScheduler(timezone=timezone)
    scheduler.add_job(
        scheduled_daily_collection_job,
        trigger=CronTrigger(hour=hour, minute=minute, timezone=timezone),
        id="daily_live_airfare_collection",
        name="Daily LIVE airfare collection",
        replace_existing=True,
        kwargs={"source_keys": list(source_keys) if source_keys is not None else None},
    )
    return scheduler


def start_daily_collection_scheduler(
    *,
    collection_time: Optional[str] = None,
    timezone_name: Optional[str] = None,
    source_keys: Optional[Sequence[str]] = None,
) -> AsyncIOScheduler:
    """Creates and starts the daily collection scheduler."""
    scheduler = create_daily_collection_scheduler(
        collection_time=collection_time,
        timezone_name=timezone_name,
        source_keys=source_keys,
    )
    scheduler.start()
    logger.info("Started daily LIVE airfare collection scheduler")
    return scheduler


def shutdown_daily_collection_scheduler(scheduler: AsyncIOScheduler) -> None:
    """Stops a running scheduler gracefully."""
    if scheduler.running:
        scheduler.shutdown(wait=False)
        logger.info("Stopped daily LIVE airfare collection scheduler")


async def scheduled_daily_collection_job(source_keys: Optional[Sequence[str]] = None) -> DailyCollectionResult:
    """Runs one scheduled daily collection using the application database session."""
    db = SessionLocal()
    try:
        timezone = ZoneInfo(settings.DAILY_COLLECTION_TIMEZONE)
        result = await run_daily_collection(db, collection_date=datetime.now(timezone).date(), source_keys=source_keys)
        logger.info("Scheduled daily collection completed: %s", result.message)
        return result
    finally:
        db.close()


async def trigger_daily_collection_now(
    collection_date: Optional[date] = None,
    *,
    source_keys: Optional[Sequence[str]] = None,
    route_codes: Optional[Sequence[str]] = None,
    advance_windows: Optional[Sequence[int]] = None,
) -> DailyCollectionResult:
    """Manual one-shot trigger for tests or supervised operations."""
    db = SessionLocal()
    try:
        return await run_daily_collection(
            db,
            collection_date=collection_date,
            source_keys=source_keys,
            route_codes=route_codes,
            advance_windows=advance_windows,
        )
    finally:
        db.close()
