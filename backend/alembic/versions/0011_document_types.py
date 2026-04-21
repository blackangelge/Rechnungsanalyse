"""document_types table, document_type_id on documents, is_document_type_prompt on system_prompts

Revision ID: 0011_document_types
Revises: 0010_ki_total_duration
Create Date: 2026-04-21 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy import text

revision = "0011_document_types"
down_revision = "0010"
branch_labels = None
depends_on = None

DOCUMENT_TYPES = [
    (1,  "Eingangsrechnung"),
    (2,  "Ausgangsrechnung"),
    (3,  "Gutschrift / Kreditnote"),
    (4,  "Lieferschein"),
    (5,  "Auftragsbestätigung"),
    (6,  "Angebot"),
    (7,  "Mahnung"),
    (8,  "Kontoauszug"),
    (9,  "Kassenbon / Quittung"),
    (10, "Vertrag"),
    (11, "Lohnabrechnung"),
    (12, "Reisekostenabrechnung"),
    (13, "Zollpapier"),
    (14, "Versicherungspolice"),
    (15, "Sonstiges"),
]


def upgrade() -> None:
    # 1. document_types Tabelle erstellen
    op.create_table(
        "document_types",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_document_types_id", "document_types", ["id"], unique=False)

    # 2. Standarddaten einfügen
    conn = op.get_bind()
    conn.execute(
        text("INSERT INTO document_types (id, name) VALUES (:id, :name)"),
        [{"id": id_, "name": name} for id_, name in DOCUMENT_TYPES],
    )

    # 3. document_type_id zu documents hinzufügen
    op.add_column(
        "documents",
        sa.Column(
            "document_type_id",
            sa.Integer(),
            sa.ForeignKey("document_types.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )

    # 4. is_document_type_prompt zu system_prompts hinzufügen
    op.add_column(
        "system_prompts",
        sa.Column(
            "is_document_type_prompt",
            sa.Boolean(),
            server_default="false",
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_column("system_prompts", "is_document_type_prompt")
    op.drop_column("documents", "document_type_id")
    op.drop_index("ix_document_types_id", table_name="document_types")
    op.drop_table("document_types")
