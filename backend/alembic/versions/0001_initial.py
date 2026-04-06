"""initial

Revision ID: 0001_initial
Revises:
Create Date: 2026-04-06 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa

revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "ai_configs",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("api_url", sa.String(500), nullable=False),
        sa.Column("api_key", sa.String(200), nullable=True),
        sa.Column("model_name", sa.String(200), nullable=False),
        sa.Column("is_default", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("max_tokens", sa.Integer(), nullable=False, server_default="2048"),
        sa.Column("temperature", sa.Float(), nullable=False, server_default="0.1"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_ai_configs_id"), "ai_configs", ["id"], unique=False)

    op.create_table(
        "image_settings",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("dpi", sa.Integer(), nullable=False, server_default="150"),
        sa.Column("image_format", sa.String(10), nullable=False, server_default="PNG"),
        sa.Column("jpeg_quality", sa.Integer(), nullable=False, server_default="85"),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "import_batches",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("folder_path", sa.String(1000), nullable=False),
        sa.Column("company_name", sa.String(255), nullable=False),
        sa.Column("year", sa.Integer(), nullable=False),
        sa.Column("comment", sa.Text(), nullable=True),
        sa.Column("status", sa.String(50), nullable=False, server_default="pending"),
        sa.Column("total_docs", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("processed_docs", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("ai_config_id", sa.Integer(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["ai_config_id"], ["ai_configs.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_import_batches_id"), "import_batches", ["id"], unique=False)

    op.create_table(
        "documents",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("batch_id", sa.Integer(), nullable=False),
        sa.Column("original_filename", sa.String(500), nullable=False),
        sa.Column("stored_filename", sa.String(500), nullable=True),
        sa.Column("file_size_bytes", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("page_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("company", sa.String(255), nullable=False),
        sa.Column("year", sa.Integer(), nullable=False),
        sa.Column("comment", sa.Text(), nullable=True),
        sa.Column("status", sa.String(50), nullable=False, server_default="pending"),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["batch_id"], ["import_batches.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_documents_id"), "documents", ["id"], unique=False)

    op.create_table(
        "invoice_extractions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("document_id", sa.Integer(), nullable=False),
        sa.Column("supplier_name", sa.String(255), nullable=True),
        sa.Column("supplier_address", sa.Text(), nullable=True),
        sa.Column("hrb_number", sa.String(100), nullable=True),
        sa.Column("tax_number", sa.String(100), nullable=True),
        sa.Column("vat_id", sa.String(100), nullable=True),
        sa.Column("bank_name", sa.String(255), nullable=True),
        sa.Column("iban", sa.String(50), nullable=True),
        sa.Column("bic", sa.String(20), nullable=True),
        sa.Column("customer_number", sa.String(100), nullable=True),
        sa.Column("invoice_number", sa.String(100), nullable=True),
        sa.Column("invoice_date", sa.Date(), nullable=True),
        sa.Column("due_date", sa.Date(), nullable=True),
        sa.Column("total_amount", sa.Numeric(12, 2), nullable=True),
        sa.Column("discount_amount", sa.Numeric(12, 2), nullable=True),
        sa.Column("cash_discount_amount", sa.Numeric(12, 2), nullable=True),
        sa.Column("payment_terms", sa.Text(), nullable=True),
        sa.Column("raw_response", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["document_id"], ["documents.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("document_id"),
    )
    op.create_index(op.f("ix_invoice_extractions_id"), "invoice_extractions", ["id"], unique=False)

    op.create_table(
        "order_positions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("document_id", sa.Integer(), nullable=False),
        sa.Column("position_index", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("product_description", sa.Text(), nullable=True),
        sa.Column("article_number", sa.String(100), nullable=True),
        sa.Column("unit_price", sa.Numeric(12, 4), nullable=True),
        sa.Column("total_price", sa.Numeric(12, 2), nullable=True),
        sa.Column("quantity", sa.Numeric(12, 4), nullable=True),
        sa.Column("unit", sa.String(50), nullable=True),
        sa.Column("discount", sa.String(100), nullable=True),
        sa.ForeignKeyConstraint(["document_id"], ["documents.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_order_positions_id"), "order_positions", ["id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_order_positions_id"), table_name="order_positions")
    op.drop_table("order_positions")
    op.drop_index(op.f("ix_invoice_extractions_id"), table_name="invoice_extractions")
    op.drop_table("invoice_extractions")
    op.drop_index(op.f("ix_documents_id"), table_name="documents")
    op.drop_table("documents")
    op.drop_index(op.f("ix_import_batches_id"), table_name="import_batches")
    op.drop_table("import_batches")
    op.drop_table("image_settings")
    op.drop_index(op.f("ix_ai_configs_id"), table_name="ai_configs")
    op.drop_table("ai_configs")
