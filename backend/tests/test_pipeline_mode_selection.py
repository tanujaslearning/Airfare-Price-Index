"""Tests for on-demand pipeline trigger routing without external website access."""

from datetime import date, datetime, timezone

import pytest

from backend.app.api.v1.endpoints import pipeline as pipeline_endpoint
from backend.app.schemas.api_responses import PipelineTriggerRequest


@pytest.mark.asyncio
async def test_pipeline_trigger_uses_daily_live_matrix_workflow(monkeypatch):
    calls = []

    async def fake_daily_pipeline(**kwargs):
        calls.append(kwargs)
        return {
            "status": "PARTIAL",
            "job_id": 32,
            "source": "DailyLiveRouteWindowMatrix",
            "collection_date": date(2026, 9, 5),
            "ingested_count": 25,
            "processed_quotes_count": 25,
            "outliers_count": 0,
            "clean_usable_count": 25,
            "index_value": None,
            "ma_7d": None,
            "dod_change_pct": None,
            "collection_mode": "LIVE",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    monkeypatch.setattr(pipeline_endpoint, "run_daily_live_pipeline_trigger", fake_daily_pipeline)

    db = object()
    response = await pipeline_endpoint.trigger_pipeline(PipelineTriggerRequest(), db=db)

    assert response.source == "DailyLiveRouteWindowMatrix"
    assert response.collection_mode == "LIVE"
    assert response.ingested_count == 25
    assert calls == [{"db": db, "collection_date": None}]


@pytest.mark.asyncio
async def test_pipeline_trigger_ignores_obsolete_scraper_mode(monkeypatch):
    async def fake_daily_pipeline(**kwargs):
        return {
            "status": "SKIPPED",
            "job_id": 0,
            "source": "DailyLiveRouteWindowMatrix",
            "collection_date": date(2026, 9, 5),
            "ingested_count": 0,
            "processed_quotes_count": 0,
            "outliers_count": 0,
            "clean_usable_count": 0,
            "index_value": None,
            "ma_7d": None,
            "dod_change_pct": None,
            "collection_mode": "LIVE",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    monkeypatch.setattr(pipeline_endpoint, "run_daily_live_pipeline_trigger", fake_daily_pipeline)
    monkeypatch.setattr(pipeline_endpoint, "run_full_mock_pipeline", None, raising=False)
    monkeypatch.setattr(pipeline_endpoint, "run_full_live_pipeline", None, raising=False)

    response = await pipeline_endpoint.trigger_pipeline(PipelineTriggerRequest(), db=object())

    assert response.source == "DailyLiveRouteWindowMatrix"
    assert response.collection_mode == "LIVE"
