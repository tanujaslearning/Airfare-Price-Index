"""Business logic, ingestion, cleaning, normalization, and index calculation services."""

from backend.app.services.ingestion_service import (
    start_scraping_job,
    finish_scraping_job,
    ingest_raw_quotes,
    get_quote_provenance_report,
    run_mock_ingestion,
)
from backend.app.services.cleaning_service import (
    verify_and_adjust_taxes,
    deduplicate_quotes_df,
    detect_outliers_df,
    clean_and_normalize_raw_quotes,
)
from backend.app.services.pipeline_service import (
    process_raw_batch,
    run_full_mock_pipeline,
)
from backend.app.services.index_engine import (
    get_route_baseline_fare,
    calculate_route_indices,
    calculate_composite_index,
    run_pipeline_and_calculate_index,
)
from backend.app.services.live_index_service import calculate_live_only_index

__all__ = [
    "start_scraping_job",
    "finish_scraping_job",
    "ingest_raw_quotes",
    "get_quote_provenance_report",
    "run_mock_ingestion",
    "verify_and_adjust_taxes",
    "deduplicate_quotes_df",
    "detect_outliers_df",
    "clean_and_normalize_raw_quotes",
    "process_raw_batch",
    "run_full_mock_pipeline",
    "get_route_baseline_fare",
    "calculate_route_indices",
    "calculate_composite_index",
    "run_pipeline_and_calculate_index",
    "calculate_live_only_index",
]
