"""ai_config reasoning column

Revision ID: 0007_ai_config_reasoning
Revises: 0006_processing_settings
Create Date: 2026-04-12 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa

revision = "0007_ai_config_reasoning"
down_revision = "0006_processing_settings"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "ai_configs",
        sa.Column(
            "reasoning",
            sa.String(20),
            nullable=False,
            server_default="off",
        ),
    )


def downgrade() -> None:
    op.drop_column("ai_configs", "reasoning")
