"""Add street/zip_code/city to suppliers and endpoint_type to ai_configs

Revision ID: 0008
Revises: 0007_ai_config_reasoning
Create Date: 2026-04-12
"""
from alembic import op
import sqlalchemy as sa

revision = "0008"
down_revision = "0007_ai_config_reasoning"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("suppliers", sa.Column("street", sa.String(255), nullable=True))
    op.add_column("suppliers", sa.Column("zip_code", sa.String(20), nullable=True))
    op.add_column("suppliers", sa.Column("city", sa.String(255), nullable=True))
    op.add_column("ai_configs", sa.Column("endpoint_type", sa.String(20), nullable=False, server_default="openai"))


def downgrade() -> None:
    op.drop_column("suppliers", "street")
    op.drop_column("suppliers", "zip_code")
    op.drop_column("suppliers", "city")
    op.drop_column("ai_configs", "endpoint_type")
