"""Add KI stats fields to invoice_extractions

Revision ID: 0009
Revises: 0008
Create Date: 2026-04-12
"""
from alembic import op
import sqlalchemy as sa

revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("invoice_extractions", sa.Column("ki_input_tokens", sa.Integer(), nullable=True))
    op.add_column("invoice_extractions", sa.Column("ki_output_tokens", sa.Integer(), nullable=True))
    op.add_column("invoice_extractions", sa.Column("ki_reasoning_tokens", sa.Integer(), nullable=True))
    op.add_column("invoice_extractions", sa.Column("ki_tokens_per_second", sa.Float(), nullable=True))
    op.add_column("invoice_extractions", sa.Column("ki_time_to_first_token", sa.Float(), nullable=True))


def downgrade() -> None:
    op.drop_column("invoice_extractions", "ki_time_to_first_token")
    op.drop_column("invoice_extractions", "ki_tokens_per_second")
    op.drop_column("invoice_extractions", "ki_reasoning_tokens")
    op.drop_column("invoice_extractions", "ki_output_tokens")
    op.drop_column("invoice_extractions", "ki_input_tokens")
