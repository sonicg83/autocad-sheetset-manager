"""内置扩展持久化表 for PLAN-DM-020"""

import sqlalchemy as sa
from alembic import op

revision = "0006_dm020_extension_platform"
down_revision = "0005_dm019_job_lease_seconds"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "extension_states",
        sa.Column("extension_id", sa.String(120), primary_key=True),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("last_loaded_version", sa.String(32)),
        sa.Column("last_error_code", sa.String(80)),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "extension_settings",
        sa.Column("extension_id", sa.String(120), primary_key=True),
        sa.Column("schema_version", sa.Integer(), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("value_json", sa.JSON(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "workspace_extension_preferences",
        sa.Column("workspace_id", sa.String(36), primary_key=True),
        sa.Column("extension_id", sa.String(120), primary_key=True),
        sa.Column("schema_version", sa.Integer(), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("value_json", sa.JSON(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "artifacts",
        sa.Column("artifact_id", sa.String(64), primary_key=True),
        sa.Column("extension_id", sa.String(120), nullable=False),
        sa.Column("extension_version", sa.String(32), nullable=False),
        sa.Column("workspace_id", sa.String(36), nullable=False),
        sa.Column("source_revision_id", sa.String(64), nullable=False),
        sa.Column("kind", sa.String(40), nullable=False),
        sa.Column("media_type", sa.String(120), nullable=False),
        sa.Column(
            "management_relation",
            sa.String(16),
            sa.CheckConstraint("management_relation IN ('external')"),
            nullable=False,
        ),
        sa.Column("output_path", sa.Text(), nullable=False),
        sa.Column("file_name", sa.Text(), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("sha256", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("artifacts")
    op.drop_table("workspace_extension_preferences")
    op.drop_table("extension_settings")
    op.drop_table("extension_states")
