"""jobs.lease_seconds 行快照 for PLAN-DM-019"""

import sqlalchemy as sa
from alembic import op

revision = "0005_dm019_job_lease_seconds"
down_revision = "0004_dm007_layout_name_cache"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("jobs", sa.Column("lease_seconds", sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column("jobs", "lease_seconds")
