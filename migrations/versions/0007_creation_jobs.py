"""创建任务持久化：jobs 关联可空 workspace_id 与稳定 creation_draft_id（PLAN-DM-036 Task 6）

创建任务在普通工作区尚不存在时就已存在（草稿 + 权威预览 + CAD 暂存都在工作区
之外），因此 ``jobs.workspace_id`` 必须可空；创建草稿身份用独立稳定列关联，
不塞进 ``payload_json``，便于按草稿查询与后续登记工作区时定位。
"""

import sqlalchemy as sa
from alembic import op

revision = "0007_creation_jobs"
down_revision = "0006_dm020_extension_platform"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # SQLite 用 batch 重建表（env.py 已 render_as_batch）；重建期间不加外键强校验，
    # 既有 job_files/job_events/diagnostics 行原样保留。
    with op.batch_alter_table("jobs") as batch:
        batch.add_column(sa.Column("creation_draft_id", sa.String(64), nullable=True))
        batch.alter_column("workspace_id", existing_type=sa.String(36), nullable=True)


def downgrade() -> None:
    connection = op.get_bind()
    remaining = connection.execute(
        sa.text("SELECT COUNT(*) FROM jobs WHERE workspace_id IS NULL")
    ).scalar_one()
    if remaining:
        # 回退会把这些任务变成无主行（NOT NULL 无法承载），只能显式阻断而不是丢弃。
        raise RuntimeError(
            f"CREATION_JOBS_DOWNGRADE_BLOCKED: 仍有 {remaining} 个创建任务没有工作区关联，"
            "请先完成工作区登记或删除这些任务后再回退"
        )
    with op.batch_alter_table("jobs") as batch:
        batch.drop_column("creation_draft_id")
        batch.alter_column("workspace_id", existing_type=sa.String(36), nullable=False)
