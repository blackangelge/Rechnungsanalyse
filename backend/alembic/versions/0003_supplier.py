"""suppliers table and supplier_id FK on invoice_extractions

Revision ID: 0003_supplier
Revises: 0002_system_prompts
Create Date: 2026-04-06 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy import text

revision = "0003_supplier"
down_revision = "0002_system_prompts"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. suppliers Tabelle erstellen
    op.create_table(
        "suppliers",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("address", sa.Text(), nullable=True),
        sa.Column("hrb_number", sa.String(100), nullable=True),
        sa.Column("tax_number", sa.String(100), nullable=True),
        sa.Column("vat_id", sa.String(100), nullable=True),
        sa.Column("bank_name", sa.String(255), nullable=True),
        sa.Column("iban", sa.String(50), nullable=True),
        sa.Column("bic", sa.String(20), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_suppliers_id", "suppliers", ["id"], unique=False)

    # 2. supplier_id zu invoice_extractions hinzufügen
    op.add_column(
        "invoice_extractions",
        sa.Column(
            "supplier_id",
            sa.Integer(),
            sa.ForeignKey("suppliers.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )


def downgrade() -> None:
    op.drop_column("invoice_extractions", "supplier_id")
    op.drop_index("ix_suppliers_id", table_name="suppliers")
    op.drop_table("suppliers")
