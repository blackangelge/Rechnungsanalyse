"""Indizes für schnelle Beleg-/Artikelsuche bei vielen tausend Belegen

Revision ID: 0016_search_indexes
Revises: 0015_workflows
Create Date: 2026-10-14 00:00:00.000000

- B-Tree-Indizes auf häufig gefilterte Spalten und Fremdschlüssel (PostgreSQL legt für
  Fremdschlüssel keine Indizes an — order_positions.document_id fehlte komplett).
- pg_trgm-Indizes für die Teilstring-Suche (ILIKE '%text%'). Die Erweiterung ist "trusted"
  (ab PostgreSQL 13); schlägt das Anlegen fehl, werden nur diese Indizes übersprungen und
  die Suche funktioniert weiterhin (nur langsamer).
"""

import logging

from alembic import op
import sqlalchemy as sa

revision = "0016_search_indexes"
down_revision = "0015_workflows"
branch_labels = None
depends_on = None

logger = logging.getLogger("alembic.runtime.migration")

BTREE = {
    "documents": ["batch_id", "status", "year", "company", "document_type_id"],
    "invoice_extractions": ["supplier_id", "supplier_name", "invoice_number", "validation_status"],
    "order_positions": ["document_id"],
}

TRIGRAM = [
    ("invoice_extractions", "supplier_name"),
    ("documents", "company"),
    ("documents", "original_filename"),
    ("order_positions", "product_description"),
    ("order_positions", "article_number"),
]


def upgrade() -> None:
    for table, columns in BTREE.items():
        for col in columns:
            op.create_index(f"ix_{table}_{col}", table, [col], if_not_exists=True)

    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return
    try:
        with bind.begin_nested():      # Savepoint: ein Fehler macht die Migration nicht ungültig
            bind.execute(sa.text("CREATE EXTENSION IF NOT EXISTS pg_trgm"))
    except Exception as exc:           # noqa: BLE001
        logger.warning("pg_trgm nicht verfügbar — Teilstring-Indizes übersprungen: %s", exc)
        return
    for table, col in TRIGRAM:
        bind.execute(sa.text(
            f"CREATE INDEX IF NOT EXISTS ix_{table}_{col}_trgm ON {table} USING gin ({col} gin_trgm_ops)"
        ))


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        for table, col in TRIGRAM:
            bind.execute(sa.text(f"DROP INDEX IF EXISTS ix_{table}_{col}_trgm"))
    for table, columns in BTREE.items():
        for col in columns:
            op.drop_index(f"ix_{table}_{col}", table_name=table, if_exists=True)
