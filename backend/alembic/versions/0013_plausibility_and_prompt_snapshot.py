"""Plausibilitätsprüfung + gespeicherte Systemprompts

Revision ID: 0013_plausibility
Revises: 0012_doc_ki_stats
Create Date: 2026-10-14 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa

revision = "0013_plausibility"
down_revision = "0012_doc_ki_stats"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Ergebnis der Plausibilitätsprüfung je Extraktion
    op.add_column("invoice_extractions", sa.Column("validation_status", sa.String(30), nullable=True))
    op.add_column("invoice_extractions", sa.Column("validation_details", sa.Text(), nullable=True))
    # Beim Analysieren tatsächlich verwendete Systemprompts (Wortlaut-Snapshot),
    # damit ein Beleg später nachvollzogen und erneut verarbeitet werden kann.
    op.add_column("documents", sa.Column("used_system_prompt", sa.Text(), nullable=True))
    op.add_column("documents", sa.Column("used_doc_type_prompt", sa.Text(), nullable=True))
    op.add_column("documents", sa.Column("used_recheck_prompt", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("documents", "used_recheck_prompt")
    op.drop_column("documents", "used_doc_type_prompt")
    op.drop_column("documents", "used_system_prompt")
    op.drop_column("invoice_extractions", "validation_details")
    op.drop_column("invoice_extractions", "validation_status")
