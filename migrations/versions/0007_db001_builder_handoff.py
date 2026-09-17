"""Builder 成果包交接持久化（SPEC-DB-001 §10，PLAN-DB-001 Task 10）。

- ``handoff_sources`` 表：package_id 全局唯一的交接来源记录；
- ``document_revisions`` 增加 ``kind``（非空默认 'operation'）与可空
  ``source_json``（版本化来源摘要）。
"""

import sqlalchemy as sa
from alembic import op

revision = "0007_db001_builder_handoff"
down_revision = "0006_dm020_extension_platform"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "document_revisions",
        sa.Column("kind", sa.String(20), nullable=False, server_default="operation"),
    )
    op.add_column(
        "document_revisions",
        sa.Column("source_json", sa.Text(), nullable=True),
    )
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


def downgrade() -> None:
    op.drop_table("handoff_sources")
    op.drop_column("document_revisions", "source_json")
    op.drop_column("document_revisions", "kind")
