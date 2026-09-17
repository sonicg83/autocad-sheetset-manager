"""Builder 项目库 Schema 1：SPEC-DB-001 §3 八张表与约束。

从空文件创建，不承诺导入或降级任何历史项目库（§3）。
时间戳列一律 ``sa.Text`` 存 RFC3339 UTC 字符串。

Revision ID: 0001_db001_initial
Revises:
Create Date: 2026-09-17

"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0001_db001_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "projects",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("stage", sa.Text(), nullable=False),
        sa.Column("discipline", sa.Text(), nullable=False),
        sa.Column("output_path", sa.Text(), nullable=False),
        sa.Column("created_at", sa.Text(), nullable=False),
        sa.Column("updated_at", sa.Text(), nullable=False),
    )
    # §3「单库恰好一条 projects 记录」：常量表达式唯一索引在数据库层强制至多一行。
    op.execute("CREATE UNIQUE INDEX uq_projects_singleton ON projects ((1))")

    op.create_table(
        "drafts",
        sa.Column("project_id", sa.String(36), primary_key=True),
        sa.Column("payload_json", sa.Text(), nullable=False),
        sa.Column("wizard_step", sa.Integer(), nullable=False),
        sa.Column("focused_field", sa.Text(), nullable=True),
        sa.Column("updated_at", sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], name="fk_drafts_project"),
    )
    op.create_table(
        "assets",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("role", sa.String(16), nullable=False),
        sa.Column("relative_path", sa.Text(), nullable=False),
        sa.Column("sha256", sa.String(64), nullable=False),
        sa.Column("size", sa.BigInteger(), nullable=False),
        sa.Column("source_name", sa.Text(), nullable=False),
        sa.UniqueConstraint("role", "sha256", name="uq_assets_role_sha256"),
    )
    op.create_table(
        "project_revisions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("canonical_json", sa.Text(), nullable=False),
        sa.Column("sha256", sa.String(64), nullable=False),
        sa.Column("created_at", sa.Text(), nullable=False),
        sa.UniqueConstraint("sha256", name="uq_project_revisions_sha256"),
    )
    op.create_table(
        "generation_plans",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("revision_id", sa.String(36), nullable=False),
        sa.Column("canonical_json", sa.Text(), nullable=False),
        sa.Column("sha256", sa.String(64), nullable=False),
        sa.Column("confirmed_at", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(
            ["revision_id"], ["project_revisions.id"], name="fk_generation_plans_revision"
        ),
    )
    op.create_table(
        "build_runs",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("plan_id", sa.String(36), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("published_path", sa.Text(), nullable=True),
        sa.Column("created_at", sa.Text(), nullable=False),
        sa.Column("finished_at", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["plan_id"], ["generation_plans.id"], name="fk_build_runs_plan"),
    )
    op.create_table(
        "build_attempts",
        sa.Column("build_id", sa.String(36), nullable=False),
        sa.Column("attempt", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("progress", sa.Integer(), nullable=False),
        sa.Column("error_code", sa.String(80), nullable=True),
        sa.Column("error_detail", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(
            ["build_id"], ["build_runs.id"], name="fk_build_attempts_build"
        ),
        sa.PrimaryKeyConstraint("build_id", "attempt", name="pk_build_attempts_build_attempt"),
    )
    op.create_table(
        "build_events",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("build_id", sa.String(36), nullable=False),
        sa.Column("attempt", sa.Integer(), nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("event_json", sa.Text(), nullable=False),
        sa.Column("created_at", sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(["build_id"], ["build_runs.id"], name="fk_build_events_build"),
        sa.UniqueConstraint(
            "build_id", "attempt", "sequence", name="uq_build_events_sequence"
        ),
    )


def downgrade() -> None:
    op.drop_table("build_events")
    op.drop_table("build_attempts")
    op.drop_table("build_runs")
    op.drop_table("generation_plans")
    op.drop_table("project_revisions")
    op.drop_table("assets")
    op.drop_table("drafts")
    op.drop_table("projects")
