"""add raw quote provenance

Revision ID: b6f8c2d4a901
Revises: aca32761bee4
Create Date: 2026-09-04 17:00:00.000000+00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "b6f8c2d4a901"
down_revision: Union[str, None] = "aca32761bee4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("raw_airfare_quotes", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column(
                "collection_mode",
                sa.String(length=10),
                server_default="MOCK",
                nullable=False,
            )
        )
        batch_op.add_column(sa.Column("scraping_job_id", sa.Integer(), nullable=True))
        batch_op.create_index(batch_op.f("ix_raw_airfare_quotes_collection_mode"), ["collection_mode"], unique=False)
        batch_op.create_index(batch_op.f("ix_raw_airfare_quotes_scraping_job_id"), ["scraping_job_id"], unique=False)
        batch_op.create_foreign_key(
            "fk_raw_airfare_quotes_scraping_job_id_scraping_job_logs",
            "scraping_job_logs",
            ["scraping_job_id"],
            ["id"],
            ondelete="SET NULL",
        )

    op.execute(
        """
        UPDATE raw_airfare_quotes
        SET collection_mode = 'MOCK'
        WHERE collection_mode IS NULL OR collection_mode = ''
        """
    )
    op.execute(
        """
        UPDATE raw_airfare_quotes
        SET collection_mode = 'LIVE',
            scraping_job_id = 11
        WHERE id BETWEEN 1891 AND 1897
          AND EXISTS (
              SELECT 1
              FROM scraping_job_logs
              WHERE id = 11
                AND source_name = 'LiveWebsiteOrchestrator'
          )
          AND source_id IN (
              SELECT id
              FROM airlines
              WHERE code = 'QP'
          )
          AND route_id IN (
              SELECT id
              FROM routes
              WHERE origin_code = 'DEL'
                AND destination_code = 'BOM'
          )
        """
    )


def downgrade() -> None:
    with op.batch_alter_table("raw_airfare_quotes", schema=None) as batch_op:
        batch_op.drop_constraint("fk_raw_airfare_quotes_scraping_job_id_scraping_job_logs", type_="foreignkey")
        batch_op.drop_index(batch_op.f("ix_raw_airfare_quotes_scraping_job_id"))
        batch_op.drop_index(batch_op.f("ix_raw_airfare_quotes_collection_mode"))
        batch_op.drop_column("scraping_job_id")
        batch_op.drop_column("collection_mode")
