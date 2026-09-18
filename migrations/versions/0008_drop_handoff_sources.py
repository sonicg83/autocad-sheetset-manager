"""移除 Builder 成果包交接持久化（RFC-INT-002）。

删除 ``handoff_sources`` 表。``document_revisions.kind`` 与 ``source_json``
保留：它们是通用修订元数据，已由修订读取接口暴露给 API 消费方。
"""

import sqlalchemy as sa
from alembic import op

revision = "0008_drop_handoff_sources"
down_revision = "0007_db001_builder_handoff"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_table("handoff_sources")


def downgrade() -> None:
    op.create_table(
        "handoff_sources",
        sa.Column("package_id", sa.String(36), primary_key=True),
        sa.Column(
            "workspace_id",
            sa.String(36),
            sa.ForeignKey("workspaces.id"),
            nullable=False,
        ),
        sa.Column("revision_id", sa.String(64), nullable=False),
        sa.Column("build_id", sa.String(36), nullable=False),
        sa.Column("plan_id", sa.String(36), nullable=False),
        sa.Column("manifest_sha256", sa.String(64), nullable=False),
        sa.Column("handoff_path", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
