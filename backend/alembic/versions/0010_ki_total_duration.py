"""Add ki_total_duration to invoice_extractions

Revision ID: 0010
Revises: 0009
Create Date: 2026-04-20
"""
from alembic import op
import sqlalchemy as sa

revision = "0010"
down_revision = "0009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "invoice_extractions",
        sa.Column("ki_total_duration", sa.Float(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("invoice_extractions", "ki_total_duration")
