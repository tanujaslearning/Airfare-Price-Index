"""Controlled SpiceJet live ingestion diagnostic.

This script runs exactly one SpiceJet live collection for DEL-BOM and writes
the required report.json. It intentionally uses the existing scraper,
orchestrator, ingestion, cleaning, and live-index services.
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
from collections import Counter
from dataclasses import asdict
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

from sqlalchemy import func

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

if os.environ.get("DEBUG", "").strip().lower() not in {"", "0", "1", "true", "false", "yes", "no", "on", "off"}:
    os.environ["DEBUG"] = "false"

from backend.app.db.session import SessionLocal
from backend.app.models.airline import Airline
from backend.app.models.quote import ProcessedAirfareQuote, RawAirfareQuote
from backend.app.models.route import Route
from backend.app.models.scraping_job import ScrapingJobLog
from backend.app.services.ingestion_service import (
    COLLECTION_MODE_LIVE,
    filter_duplicate_raw_quotes,
    finish_scraping_job,
    ingest_raw_quotes,
    start_scraping_job,
)
from backend.app.services.live_index_service import calculate_live_only_index
from backend.app.services.pipeline_service import process_raw_batch
from scraper.airlines.spicejet_scraper import SpiceJetWebsiteScraper
from scraper.base.source_orchestrator import (
    ACCESS_DENIED,
    CAPTCHA,
    RATE_LIMITED,
    SUCCESS,
    TEMPORARILY_BLOCKED,
    SourceOrchestrator,
)


DIAG_DIR = Path(__file__).resolve().parent
REPORT_PATH = DIAG_DIR / "report.json"
VISIBLE_TEXT_PATH = DIAG_DIR / "visible_text.txt"
RENDERED_HTML_PATH = DIAG_DIR / "rendered.html"

SOURCE_NAME = "SpiceJet"
SOURCE_CODE = "SG"
ROUTE_ORIGIN = "DEL"
ROUTE_DESTINATION = "BOM"
ROUTE_LABEL = "DEL-BOM"
DEPARTURE_DATE = date(2026, 9, 5)
ADVANCE_WINDOW = 1
COLLECTION_MODE = COLLECTION_MODE_LIVE
CABIN_CLASS = "ECONOMY"
CURRENCY = "INR"


class RecordingSpiceJetScraper(SpiceJetWebsiteScraper):
    """SpiceJet scraper with diagnostic capture of the rendered result page."""

    def __init__(self) -> None:
        super().__init__()
        self.results_url: str | None = None
        self.page_title: str | None = None
        self.rendered_text: str | None = None
        self.rendered_html: str | None = None

    async def _result_page_text(self, page) -> str:
        self.results_url = getattr(page, "url", None)
        self.page_title = await page.title()
        self.rendered_html = await page.content()
        text = await super()._result_page_text(page)
        self.rendered_text = text
        RENDERED_HTML_PATH.write_text(self.rendered_html or "", encoding="utf-8")
        VISIBLE_TEXT_PATH.write_text(text, encoding="utf-8")
        return text


def jsonable(value: Any) -> Any:
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if hasattr(value, "model_dump"):
        return value.model_dump()
    if hasattr(value, "__dataclass_fields__"):
        return asdict(value)
    return str(value)


def count_query(db, *criteria) -> int:
    query = (
        db.query(func.count(RawAirfareQuote.id))
        .outerjoin(Airline, RawAirfareQuote.source_id == Airline.id)
        .outerjoin(Route, RawAirfareQuote.route_id == Route.id)
    )
    if criteria:
        query = query.filter(*criteria)
    return int(query.scalar() or 0)


def processed_count_query(db, *criteria) -> int:
    query = (
        db.query(func.count(ProcessedAirfareQuote.id))
        .outerjoin(RawAirfareQuote, ProcessedAirfareQuote.raw_quote_id == RawAirfareQuote.id)
        .outerjoin(Airline, RawAirfareQuote.source_id == Airline.id)
        .outerjoin(Route, ProcessedAirfareQuote.route_id == Route.id)
    )
    if criteria:
        query = query.filter(*criteria)
    return int(query.scalar() or 0)


def raw_group_counts(db) -> dict[str, int]:
    rows = (
        db.query(
            func.coalesce(Airline.code, "NULL"),
            func.coalesce(Airline.name, "NULL"),
            RawAirfareQuote.collection_mode,
            Route.origin_code,
            Route.destination_code,
            RawAirfareQuote.advance_window_days,
            func.count(RawAirfareQuote.id),
        )
        .outerjoin(Airline, RawAirfareQuote.source_id == Airline.id)
        .join(Route, RawAirfareQuote.route_id == Route.id)
        .group_by(
            Airline.code,
            Airline.name,
            RawAirfareQuote.collection_mode,
            Route.origin_code,
            Route.destination_code,
            RawAirfareQuote.advance_window_days,
        )
        .all()
    )
    return {
        "|".join([code, name, mode or "NULL", f"{origin}-{destination}", str(window)]): int(count)
        for code, name, mode, origin, destination, window, count in rows
    }


def processed_group_counts(db) -> dict[str, int]:
    rows = (
        db.query(
            func.coalesce(Airline.code, "NULL"),
            func.coalesce(Airline.name, "NULL"),
            RawAirfareQuote.collection_mode,
            Route.origin_code,
            Route.destination_code,
            ProcessedAirfareQuote.advance_window_days,
            func.count(ProcessedAirfareQuote.id),
        )
        .outerjoin(RawAirfareQuote, ProcessedAirfareQuote.raw_quote_id == RawAirfareQuote.id)
        .outerjoin(Airline, RawAirfareQuote.source_id == Airline.id)
        .join(Route, ProcessedAirfareQuote.route_id == Route.id)
        .group_by(
            Airline.code,
            Airline.name,
            RawAirfareQuote.collection_mode,
            Route.origin_code,
            Route.destination_code,
            ProcessedAirfareQuote.advance_window_days,
        )
        .all()
    )
    return {
        "|".join([code, name, mode or "NULL", f"{origin}-{destination}", str(window)]): int(count)
        for code, name, mode, origin, destination, window, count in rows
    }


def db_fingerprint(db) -> dict[str, Any]:
    db_path = ROOT / "apix.db"
    latest_job = db.query(ScrapingJobLog).order_by(ScrapingJobLog.id.desc()).first()
    return {
        "db_path": str(db_path),
        "db_size": db_path.stat().st_size if db_path.exists() else None,
        "db_modification_time": (
            datetime.fromtimestamp(db_path.stat().st_mtime, tz=timezone.utc).isoformat()
            if db_path.exists()
            else None
        ),
        "latest_scraping_job_id": latest_job.id if latest_job else None,
        "latest_scraping_job": (
            {
                "id": latest_job.id,
                "source_name": latest_job.source_name,
                "status": latest_job.status,
                "total_scraped": latest_job.total_scraped,
                "start_time": latest_job.start_time,
                "end_time": latest_job.end_time,
                "error_log": latest_job.error_log,
            }
            if latest_job
            else None
        ),
        "scraping_job_count": int(db.query(func.count(ScrapingJobLog.id)).scalar() or 0),
        "raw_quote_count": count_query(db),
        "processed_quote_count": int(db.query(func.count(ProcessedAirfareQuote.id)).scalar() or 0),
        "live_quote_count": count_query(db, RawAirfareQuote.collection_mode == COLLECTION_MODE_LIVE),
        "live_processed_quote_count": processed_count_query(
            db,
            RawAirfareQuote.collection_mode == COLLECTION_MODE_LIVE,
        ),
        "mock_quote_count": count_query(db, RawAirfareQuote.collection_mode == "MOCK"),
        "akasa_raw_quote_count": count_query(db, Airline.code == "QP"),
        "akasa_processed_quote_count": processed_count_query(db, Airline.code == "QP"),
        "raw_group_counts": raw_group_counts(db),
        "processed_group_counts": processed_group_counts(db),
    }


def resolve_reference_data(db) -> tuple[Route, Airline]:
    route = (
        db.query(Route)
        .filter(
            Route.origin_code == ROUTE_ORIGIN,
            Route.destination_code == ROUTE_DESTINATION,
            Route.is_active == True,
        )
        .first()
    )
    if route is None:
        raise RuntimeError("Controlled route DEL-BOM is not configured or active.")

    source = db.query(Airline).filter(Airline.code == SOURCE_CODE).first()
    if source is None:
        raise RuntimeError("SpiceJet source SG is not configured.")
    return route, source


def quote_to_report(raw_quote) -> dict[str, Any]:
    fare_family = raw_quote.cabin_class
    if "-" in fare_family:
        fare_family = fare_family.split("-", 1)[1]
    return {
        "quote_id": getattr(raw_quote, "id", None),
        "source": SOURCE_NAME,
        "collection_mode": getattr(raw_quote, "collection_mode", COLLECTION_MODE),
        "scraping_job_id": getattr(raw_quote, "scraping_job_id", None),
        "route": ROUTE_LABEL,
        "flight_number": raw_quote.flight_number,
        "departure_datetime": raw_quote.departure_datetime,
        "arrival_datetime": raw_quote.arrival_datetime,
        "advance_window_days": raw_quote.advance_window_days,
        "base_fare": raw_quote.base_fare,
        "taxes_fees": raw_quote.taxes_fees,
        "base_fare_semantics": "unavailable_from_visible_dom",
        "taxes_fees_semantics": "unavailable_from_visible_dom",
        "total_fare": raw_quote.total_fare,
        "fare_family": fare_family,
        "currency": CURRENCY,
        "cabin_class": raw_quote.cabin_class,
        "scraped_at": raw_quote.scraped_at,
    }


def validate_quotes(quotes, route: Route, source: Airline) -> tuple[list[Any], list[dict[str, Any]]]:
    valid = []
    rejected = []
    for quote in quotes:
        reasons = []
        if quote.source_id != source.id:
            reasons.append(f"source_id {quote.source_id} != {source.id}")
        if quote.route_id != route.id:
            reasons.append(f"route_id {quote.route_id} != {route.id}")
        if quote.departure_datetime.date() != DEPARTURE_DATE:
            reasons.append(f"departure_date {quote.departure_datetime.date()} != {DEPARTURE_DATE}")
        if quote.advance_window_days != ADVANCE_WINDOW:
            reasons.append(f"advance_window_days {quote.advance_window_days} != {ADVANCE_WINDOW}")
        if quote.total_fare <= 0:
            reasons.append(f"total_fare {quote.total_fare} <= 0")
        if reasons:
            rejected.append({"quote": quote.model_dump(), "reasons": reasons})
        else:
            valid.append(quote)
    return valid, rejected


def group_deltas(before: dict[str, int], after: dict[str, int]) -> dict[str, int]:
    keys = set(before) | set(after)
    return {key: after.get(key, 0) - before.get(key, 0) for key in sorted(keys) if after.get(key, 0) != before.get(key, 0)}


def verify_unrelated_data(before: dict[str, Any], after: dict[str, Any], inserted_raw: int, inserted_processed: int) -> dict[str, Any]:
    raw_deltas = group_deltas(before["raw_group_counts"], after["raw_group_counts"])
    processed_deltas = group_deltas(before["processed_group_counts"], after["processed_group_counts"])
    expected_key = f"{SOURCE_CODE}|{SOURCE_NAME}|{COLLECTION_MODE}|{ROUTE_LABEL}|{ADVANCE_WINDOW}"
    unexpected_raw = {
        key: delta
        for key, delta in raw_deltas.items()
        if not (key == expected_key and delta == inserted_raw)
    }
    unexpected_processed = {
        key: delta
        for key, delta in processed_deltas.items()
        if not (key == expected_key and delta == inserted_processed)
    }
    return {
        "exactly_one_scraping_job_created": after["scraping_job_count"] - before["scraping_job_count"] == 1,
        "akasa_raw_records_changed": after["akasa_raw_quote_count"] - before["akasa_raw_quote_count"],
        "akasa_processed_records_changed": after["akasa_processed_quote_count"] - before["akasa_processed_quote_count"],
        "mock_records_inserted": after["mock_quote_count"] - before["mock_quote_count"],
        "raw_group_deltas": raw_deltas,
        "processed_group_deltas": processed_deltas,
        "unexpected_raw_group_deltas": unexpected_raw,
        "unexpected_processed_group_deltas": unexpected_processed,
        "only_expected_spicejet_records_inserted": not unexpected_raw and not unexpected_processed,
    }


def verify_new_quotes(db, job_id: int, route: Route, source: Airline) -> dict[str, Any]:
    rows = (
        db.query(RawAirfareQuote)
        .filter(RawAirfareQuote.scraping_job_id == job_id)
        .order_by(RawAirfareQuote.id.asc())
        .all()
    )
    failures = []
    for quote in rows:
        reasons = []
        if quote.source_id != source.id:
            reasons.append("source_id")
        if quote.collection_mode != COLLECTION_MODE:
            reasons.append("collection_mode")
        if quote.scraping_job_id != job_id:
            reasons.append("scraping_job_id")
        if quote.route_id != route.id:
            reasons.append("route")
        if quote.departure_datetime.date() != DEPARTURE_DATE:
            reasons.append("departure_date")
        if quote.advance_window_days != ADVANCE_WINDOW:
            reasons.append("advance_window_days")
        if quote.total_fare <= 0:
            reasons.append("total_fare")
        if reasons:
            failures.append({"quote_id": quote.id, "failed_fields": reasons})
    return {
        "checked_quote_count": len(rows),
        "all_new_quotes_valid": not failures,
        "failures": failures,
    }


def rejection_reason_counts(rejections: list[dict[str, Any]]) -> dict[str, int]:
    counts = Counter()
    for rejected in rejections:
        for reason in rejected["reasons"]:
            counts[reason] += 1
    return dict(counts)


def repair_existing_report() -> dict[str, Any]:
    report = json.loads(REPORT_PATH.read_text(encoding="utf-8"))
    for section_name in ("DATABASE_BEFORE", "DATABASE_AFTER"):
        section = report.get(section_name, {})
        raw_groups = section.get("raw_group_counts", {})
        processed_groups = section.get("processed_group_counts", {})
        section["akasa_raw_quote_count"] = sum(
            count for key, count in raw_groups.items() if key.startswith("QP|Akasa Air|")
        )
        section["akasa_processed_quote_count"] = sum(
            count for key, count in processed_groups.items() if key.startswith("QP|Akasa Air|")
        )

    before = report.get("DATABASE_BEFORE", {})
    after = report.get("DATABASE_AFTER", {})
    check = report.setdefault("UNRELATED_DATA_CHECK", {})
    check["akasa_raw_records_changed"] = after.get("akasa_raw_quote_count", 0) - before.get("akasa_raw_quote_count", 0)
    check["akasa_processed_records_changed"] = (
        after.get("akasa_processed_quote_count", 0) - before.get("akasa_processed_quote_count", 0)
    )
    REPORT_PATH.write_text(json.dumps(report, default=jsonable, indent=2), encoding="utf-8")
    return report


async def main() -> dict[str, Any]:
    DIAG_DIR.mkdir(parents=True, exist_ok=True)
    db = SessionLocal()
    job = None
    scraper = RecordingSpiceJetScraper()
    parsed_quotes = []
    saved_raw = []
    processed_summary: dict[str, Any] = {
        "status": "not_run",
        "processed_quotes_count": 0,
        "outliers_count": 0,
        "clean_usable_count": 0,
    }
    errors: list[str] = []
    rejection_details: list[dict[str, Any]] = []
    result = "LIVE_INGESTION_FAILED"

    try:
        before = db_fingerprint(db)
        route, source = resolve_reference_data(db)
        job = start_scraping_job(db, source_name="LiveWebsiteOrchestrator")

        orchestrator = SourceOrchestrator(
            sources=[scraper],
            source_id_by_name={SOURCE_NAME: source.id},
        )
        collection_result = await orchestrator.collect_quotes(
            origin=ROUTE_ORIGIN,
            destination=ROUTE_DESTINATION,
            departure_date=DEPARTURE_DATE,
            cabin_class=CABIN_CLASS,
            route_id=route.id,
            source_id=source.id,
        )
        attempts = [asdict(attempt) for attempt in collection_result.attempts]
        parsed_quotes = collection_result.quotes

        blocked_states = {CAPTCHA, RATE_LIMITED, ACCESS_DENIED, TEMPORARILY_BLOCKED}
        if any(attempt["state"] in blocked_states for attempt in attempts):
            result = "CAPTCHA_OR_BLOCK"
            errors.extend(f"{a['source_name']}: {a['state']}: {a['message']}" for a in attempts)
            finish_scraping_job(db, job, total_scraped=0, status="FAILED", error_log="; ".join(errors))
        elif not parsed_quotes:
            result = "LIVE_INGESTION_FAILED"
            errors.extend(f"{a['source_name']}: {a['state']}: {a['message']}" for a in attempts)
            finish_scraping_job(db, job, total_scraped=0, status="FAILED", error_log="; ".join(errors))
        else:
            valid_quotes, rejection_details = validate_quotes(parsed_quotes, route, source)
            if rejection_details:
                result = "DATA_VALIDATION_FAILED"
                errors.append("One or more parsed quotes failed pre-ingestion validation.")
                finish_scraping_job(db, job, total_scraped=0, status="FAILED", error_log="; ".join(errors))
            else:
                filtered_quotes, duplicate_count = filter_duplicate_raw_quotes(
                    db,
                    valid_quotes,
                    collection_mode=COLLECTION_MODE,
                )
                if duplicate_count:
                    rejection_details.extend(
                        {"quote": {}, "reasons": ["duplicate same-day live raw quote"]}
                        for _ in range(duplicate_count)
                    )
                saved_raw = ingest_raw_quotes(
                    db,
                    filtered_quotes,
                    job=job,
                    collection_mode=COLLECTION_MODE,
                )
                if saved_raw:
                    processed_summary = process_raw_batch(db, raw_quotes=saved_raw, job_id=job.id)
                    finish_scraping_job(db, job, total_scraped=len(saved_raw), status="COMPLETED")
                    result = "LIVE_INGESTION_SUCCESS"
                else:
                    result = "LIVE_INGESTION_PARTIAL"
                    errors.append("Parsed quotes were valid but no new raw quotes were inserted.")
                    finish_scraping_job(db, job, total_scraped=0, status="FAILED", error_log="; ".join(errors))

        after = db_fingerprint(db)
        db.refresh(job)
        processed_rows = (
            db.query(ProcessedAirfareQuote)
            .join(RawAirfareQuote, ProcessedAirfareQuote.raw_quote_id == RawAirfareQuote.id)
            .filter(RawAirfareQuote.scraping_job_id == job.id)
            .order_by(ProcessedAirfareQuote.id.asc())
            .all()
            if job
            else []
        )
        provenance_verification = verify_new_quotes(db, job.id, route, source) if job else {}
        unrelated_check = verify_unrelated_data(
            before,
            after,
            inserted_raw=len(saved_raw),
            inserted_processed=len(processed_rows),
        )

        index_visibility: dict[str, Any]
        if saved_raw:
            index_response = calculate_live_only_index(
                db,
                collection_date=saved_raw[0].scraped_at.date(),
                route=route,
                advance_window_days=ADVANCE_WINDOW,
                source=source,
            )
            index_visibility = index_response.model_dump()
        else:
            index_visibility = {
                "status": "not_checked_no_new_live_quotes",
                "live_quote_count": 0,
            }

        report = {
            "RESULT": result,
            "JOB_ID": job.id if job else None,
            "JOB_STATUS": job.status if job else None,
            "COLLECTION_MODE": COLLECTION_MODE,
            "SOURCE_ID": source.id,
            "ROUTE_ID": route.id,
            "ROUTE": ROUTE_LABEL,
            "DEPARTURE_DATE": DEPARTURE_DATE,
            "ADVANCE_WINDOW": ADVANCE_WINDOW,
            "REQUESTED_DEPARTURE_AND_WINDOW_NOTE": (
                "Environment date is 2026-09-05. The existing SpiceJet parser derives "
                "advance_window_days from visible departure date minus scraped_at.date()."
            ),
            "RESULTS_URL": scraper.results_url,
            "PAGE_TITLE": scraper.page_title,
            "PARSED_FLIGHT_COUNT": len({q.flight_number for q in parsed_quotes}),
            "PARSED_QUOTE_COUNT": len(parsed_quotes),
            "INSERTED_RAW_QUOTE_COUNT": len(saved_raw),
            "INSERTED_PROCESSED_QUOTE_COUNT": len(processed_rows),
            "REJECTED_COUNT": len(rejection_details),
            "REJECTION_REASONS": rejection_reason_counts(rejection_details),
            "SCRAPER_ATTEMPTS": attempts if "attempts" in locals() else [],
            "RAW_QUOTES_BEFORE": before["raw_quote_count"],
            "RAW_QUOTES_AFTER": after["raw_quote_count"],
            "PROCESSED_QUOTES_BEFORE": before["processed_quote_count"],
            "PROCESSED_QUOTES_AFTER": after["processed_quote_count"],
            "LIVE_QUOTES_BEFORE": before["live_quote_count"],
            "LIVE_QUOTES_AFTER": after["live_quote_count"],
            "QUOTES": [quote_to_report(q) for q in saved_raw],
            "PARSED_QUOTES_NOT_INSERTED": [
                {
                    "flight_number": item["quote"].get("flight_number"),
                    "departure_datetime": item["quote"].get("departure_datetime"),
                    "arrival_datetime": item["quote"].get("arrival_datetime"),
                    "advance_window_days": item["quote"].get("advance_window_days"),
                    "total_fare": item["quote"].get("total_fare"),
                    "fare_family": str(item["quote"].get("cabin_class", "")).split("-", 1)[-1],
                    "currency": CURRENCY,
                    "reasons": item["reasons"],
                }
                for item in rejection_details
                if item.get("quote")
            ],
            "PROVENANCE_VERIFICATION": provenance_verification,
            "DATABASE_BEFORE": before,
            "DATABASE_AFTER": after,
            "UNRELATED_DATA_CHECK": unrelated_check,
            "INDEX_VISIBILITY_CHECK": index_visibility,
            "ERRORS": errors,
            "FINAL_CLASSIFICATION": result,
        }
        REPORT_PATH.write_text(json.dumps(report, default=jsonable, indent=2), encoding="utf-8")
        return report
    except Exception as exc:
        db.rollback()
        errors.append(f"{type(exc).__name__}: {exc}")
        if job is not None:
            finish_scraping_job(db, job, total_scraped=0, status="FAILED", error_log="; ".join(errors))
        after = db_fingerprint(db)
        report = {
            "RESULT": "LIVE_INGESTION_FAILED",
            "JOB_ID": job.id if job else None,
            "JOB_STATUS": job.status if job else None,
            "COLLECTION_MODE": COLLECTION_MODE,
            "ROUTE": ROUTE_LABEL,
            "ADVANCE_WINDOW": ADVANCE_WINDOW,
            "RESULTS_URL": scraper.results_url,
            "PARSED_FLIGHT_COUNT": len({q.flight_number for q in parsed_quotes}),
            "PARSED_QUOTE_COUNT": len(parsed_quotes),
            "INSERTED_RAW_QUOTE_COUNT": len(saved_raw),
            "INSERTED_PROCESSED_QUOTE_COUNT": processed_summary.get("processed_quotes_count", 0),
            "REJECTED_COUNT": len(rejection_details),
            "QUOTES": [quote_to_report(q) for q in saved_raw],
            "PROVENANCE_VERIFICATION": {},
            "DATABASE_BEFORE": before if "before" in locals() else {},
            "DATABASE_AFTER": after,
            "UNRELATED_DATA_CHECK": {},
            "INDEX_VISIBILITY_CHECK": {},
            "ERRORS": errors,
            "FINAL_CLASSIFICATION": "LIVE_INGESTION_FAILED",
        }
        REPORT_PATH.write_text(json.dumps(report, default=jsonable, indent=2), encoding="utf-8")
        return report
    finally:
        db.close()


if __name__ == "__main__":
    if "--repair-report-only" in sys.argv:
        final_report = repair_existing_report()
    else:
        final_report = asyncio.run(main())
    print(json.dumps({
        "report_path": str(REPORT_PATH),
        "result": final_report.get("RESULT"),
        "job_id": final_report.get("JOB_ID"),
        "inserted_raw": final_report.get("INSERTED_RAW_QUOTE_COUNT"),
        "inserted_processed": final_report.get("INSERTED_PROCESSED_QUOTE_COUNT"),
    }, indent=2))
