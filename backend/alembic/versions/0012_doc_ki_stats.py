"""KI-Stats direkt auf documents (Fallback für Nicht-Eingangsrechnungen)

Revision ID: 0012_doc_ki_stats
Revises: 0011_document_types
Create Date: 2026-04-21 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa

revision = "0012_doc_ki_stats"
down_revision = "0011_document_types"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # KI-Stats direkt auf dem Dokument speichern, damit Token-Verbrauch auch
    # für Nicht-Eingangsrechnungen (ohne InvoiceExtraction) sichtbar ist.
    op.add_column("documents", sa.Column("doc_ki_input_tokens",  sa.Integer(), nullable=True))
    op.add_column("documents", sa.Column("doc_ki_output_tokens", sa.Integer(), nullable=True))
    op.add_column("documents", sa.Column("doc_ki_total_duration", sa.Float(), nullable=True))


def downgrade() -> None:
    op.drop_column("documents", "doc_ki_total_duration")
    op.drop_column("documents", "doc_ki_output_tokens")
    op.drop_column("documents", "doc_ki_input_tokens")
