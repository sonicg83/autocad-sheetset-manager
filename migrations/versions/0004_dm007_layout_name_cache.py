"""layout name cache for SPEC-DM-007"""

import sqlalchemy as sa
from alembic import op

revision = "0004_dm007_layout_name_cache"
down_revision = "0003_dm008_job_file_cadop"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "layout_name_cache",
        sa.Column("file_hash", sa.String(64), primary_key=True),
        sa.Column("source_path", sa.Text(), nullable=False),
        sa.Column("layouts", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("layout_name_cache")
