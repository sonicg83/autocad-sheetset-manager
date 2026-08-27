"""记录 CAD 工作单元的操作类型与起止时间。"""

import sqlalchemy as sa
from alembic import op

revision = "0003_dm008_job_file_cadop"
down_revision = "0002_v02_job_reliability"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("job_files") as batch:
        batch.add_column(sa.Column("cad_operation", sa.String(20), nullable=True))
        batch.add_column(sa.Column("started_at", sa.DateTime(timezone=True), nullable=True))
        batch.add_column(sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True))


def downgrade():
    with op.batch_alter_table("job_files") as batch:
        for name in ("finished_at", "started_at", "cad_operation"):
            batch.drop_column(name)
