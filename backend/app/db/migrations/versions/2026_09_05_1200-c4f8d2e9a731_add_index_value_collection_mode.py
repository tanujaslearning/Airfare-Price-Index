"""add collection mode to persisted index values

Revision ID: c4f8d2e9a731
Revises: b6f8c2d4a901
Create Date: 2026-09-05 12:00:00.000000+00:00

"""
from datetime import date
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "c4f8d2e9a731"
down_revision: Union[str, None] = "b6f8c2d4a901"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


DEFAULT_ROUTE_BASELINES = {
    "DEL-BOM": 4200.0,
    "DEL-BLR": 5400.0,
    "BOM-BLR": 3600.0,
    "DEL-CCU": 4600.0,
    "BLR-HYD": 2800.0,
    "MAA-DEL": 5500.0,
}
WINDOW_BASE_MULTIPLIERS = {
    1: 1.75,
    7: 1.35,
    15: 1.12,
    30: 1.00,
    45: 0.90,
}
ADVANCE_WINDOWS = [1, 7, 15, 30, 45]
VALID_COLLECTION_MODES = {"LIVE", "MOCK"}


def _baseline(route_key: str, advance_window: int) -> float:
    base_cost = DEFAULT_ROUTE_BASELINES.get(route_key, 4000.0)
    multiplier = WINDOW_BASE_MULTIPLIERS.get(advance_window, 1.0)
    raw_base = base_cost * multiplier
    return round(raw_base + (raw_base * 0.21) + 650.0, 2)


def _parse_date(value) -> date:
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value))


def _candidate_mode_stats(connection, target_date: date):
    rows = connection.execute(
        sa.text(
            """
            SELECT
                raw.collection_mode AS collection_mode,
                COUNT(*) AS quote_count,
                COUNT(DISTINCT processed.route_id || ':' || processed.advance_window_days) AS observed_combinations
            FROM processed_airfare_quotes AS processed
            JOIN raw_airfare_quotes AS raw
              ON processed.raw_quote_id = raw.id
            WHERE processed.is_outlier = 0
              AND date(processed.processed_at) = :target_date
              AND raw.collection_mode IN ('LIVE', 'MOCK')
            GROUP BY raw.collection_mode
            """
        ),
        {"target_date": target_date.isoformat()},
    ).mappings().all()
    if rows:
        return rows

    return connection.execute(
        sa.text(
            """
            SELECT
                raw.collection_mode AS collection_mode,
                COUNT(*) AS quote_count,
                COUNT(DISTINCT processed.route_id || ':' || processed.advance_window_days) AS observed_combinations
            FROM processed_airfare_quotes AS processed
            JOIN raw_airfare_quotes AS raw
              ON processed.raw_quote_id = raw.id
            WHERE processed.is_outlier = 0
              AND date(raw.scraped_at) = :target_date
              AND raw.collection_mode IN ('LIVE', 'MOCK')
            GROUP BY raw.collection_mode
            """
        ),
        {"target_date": target_date.isoformat()},
    ).mappings().all()


def _recompute_index_value(connection, target_date: date, collection_mode: str):
    rows = connection.execute(
        sa.text(
            """
            SELECT
                routes.id AS route_id,
                routes.origin_code || '-' || routes.destination_code AS route_key,
                routes.dgca_weight AS dgca_weight,
                processed.advance_window_days AS advance_window_days,
                AVG(processed.clean_total_fare) AS mean_fare
            FROM processed_airfare_quotes AS processed
            JOIN raw_airfare_quotes AS raw
              ON processed.raw_quote_id = raw.id
            JOIN routes
              ON processed.route_id = routes.id
            WHERE processed.is_outlier = 0
              AND date(processed.processed_at) = :target_date
              AND raw.collection_mode = :collection_mode
            GROUP BY
                routes.id,
                routes.origin_code,
                routes.destination_code,
                routes.dgca_weight,
                processed.advance_window_days
            """
        ),
        {"target_date": target_date.isoformat(), "collection_mode": collection_mode},
    ).mappings().all()
    if not rows:
        rows = connection.execute(
            sa.text(
                """
                SELECT
                    routes.id AS route_id,
                    routes.origin_code || '-' || routes.destination_code AS route_key,
                    routes.dgca_weight AS dgca_weight,
                    processed.advance_window_days AS advance_window_days,
                    AVG(processed.clean_total_fare) AS mean_fare
                FROM processed_airfare_quotes AS processed
                JOIN raw_airfare_quotes AS raw
                  ON processed.raw_quote_id = raw.id
                JOIN routes
                  ON processed.route_id = routes.id
                WHERE processed.is_outlier = 0
                  AND date(raw.scraped_at) = :target_date
                  AND raw.collection_mode = :collection_mode
                GROUP BY
                    routes.id,
                    routes.origin_code,
                    routes.destination_code,
                    routes.dgca_weight,
                    processed.advance_window_days
                """
            ),
            {"target_date": target_date.isoformat(), "collection_mode": collection_mode},
        ).mappings().all()
    if not rows:
        return None

    route_sub_indices = {}
    route_weights = {}
    for row in rows:
        key = (row["route_id"], row["route_key"])
        route_weights[key] = float(row["dgca_weight"] or 0.0)
        sub_index = (float(row["mean_fare"]) / _baseline(row["route_key"], int(row["advance_window_days"]))) * 100.0
        route_sub_indices.setdefault(key, []).append(sub_index)

    route_values = [
        (route_weights[key], sum(values) / len(values))
        for key, values in route_sub_indices.items()
    ]
    total_weight = sum(weight for weight, _ in route_values)
    if total_weight <= 0:
        return round(sum(value for _, value in route_values) / len(route_values), 2)
    return round(sum(weight * value for weight, value in route_values) / total_weight, 2)


def _infer_index_collection_mode(connection, index_row) -> str:
    target_date = _parse_date(index_row["date"])
    expected_combinations = connection.execute(
        sa.text("SELECT COUNT(*) FROM routes WHERE is_active = 1")
    ).scalar_one() * len(ADVANCE_WINDOWS)
    candidates = _candidate_mode_stats(connection, target_date)

    if not candidates:
        raise RuntimeError(
            f"Cannot infer collection_mode for airfare_index_values.id={index_row['id']}: "
            f"no raw quote provenance exists for {target_date}."
        )

    complete_modes = [
        row["collection_mode"]
        for row in candidates
        if int(row["observed_combinations"] or 0) >= expected_combinations
    ]
    if len(complete_modes) == 1:
        return complete_modes[0]

    scored_modes = []
    for row in candidates:
        mode = row["collection_mode"]
        recomputed = _recompute_index_value(connection, target_date, mode)
        if recomputed is None:
            continue
        scored_modes.append(
            (
                abs(float(index_row["index_value"]) - recomputed),
                -int(row["observed_combinations"] or 0),
                -int(row["quote_count"] or 0),
                mode,
            )
        )

    if scored_modes:
        scored_modes.sort()
        best_delta, _, _, best_mode = scored_modes[0]
        if best_delta <= 0.01 or len(scored_modes) == 1:
            return best_mode

    if len(candidates) == 1:
        return candidates[0]["collection_mode"]

    raise RuntimeError(
        f"Cannot unambiguously infer collection_mode for airfare_index_values.id={index_row['id']} "
        f"on {target_date}; candidates={[(row['collection_mode'], row['observed_combinations'], row['quote_count']) for row in candidates]}."
    )


def upgrade() -> None:
    with op.batch_alter_table("airfare_index_values", schema=None) as batch_op:
        batch_op.add_column(sa.Column("collection_mode", sa.String(length=10), nullable=True))

    connection = op.get_bind()
    index_rows = connection.execute(
        sa.text("SELECT id, date, frequency, index_value FROM airfare_index_values ORDER BY id")
    ).mappings().all()
    for index_row in index_rows:
        collection_mode = _infer_index_collection_mode(connection, index_row)
        if collection_mode not in VALID_COLLECTION_MODES:
            raise RuntimeError(f"Invalid inferred collection_mode {collection_mode!r}.")
        connection.execute(
            sa.text(
                """
                UPDATE airfare_index_values
                SET collection_mode = :collection_mode
                WHERE id = :id
                """
            ),
            {"collection_mode": collection_mode, "id": index_row["id"]},
        )

    with op.batch_alter_table("airfare_index_values", schema=None) as batch_op:
        batch_op.alter_column("collection_mode", existing_type=sa.String(length=10), nullable=False)
        batch_op.create_index(
            batch_op.f("ix_airfare_index_values_collection_mode"),
            ["collection_mode"],
            unique=False,
        )
        batch_op.create_check_constraint(
            "ck_airfare_index_values_collection_mode",
            "collection_mode IN ('LIVE', 'MOCK')",
        )


def downgrade() -> None:
    with op.batch_alter_table("airfare_index_values", schema=None) as batch_op:
        batch_op.drop_constraint("ck_airfare_index_values_collection_mode", type_="check")
        batch_op.drop_index(batch_op.f("ix_airfare_index_values_collection_mode"))
        batch_op.drop_column("collection_mode")
