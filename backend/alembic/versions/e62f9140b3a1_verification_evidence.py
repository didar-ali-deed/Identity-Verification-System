"""Persist multi-frame selfies and the complete pipeline evidence.

Revision ID: e62f9140b3a1
Revises: d21ab84f970c
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "e62f9140b3a1"
down_revision = "d21ab84f970c"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column("audit_logs", "performed_by", nullable=True)
    op.execute("UPDATE document_class_rules SET application_type = 'idv_standard' WHERE application_type = 'kyc_standard'")
    op.alter_column("document_class_rules", "application_type", server_default="idv_standard")
    op.create_table(
        "task_outbox",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("task_name", sa.String(120), nullable=False),
        sa.Column("args", postgresql.JSONB(), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("dispatched_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_task_outbox_dispatched_at", "task_outbox", ["dispatched_at"])
    op.add_column("face_verifications", sa.Column("frame_paths", postgresql.JSONB(), nullable=True))
    op.add_column("pipeline_results", sa.Column("stage_results", postgresql.JSONB(), nullable=True))
    # One editable application per user, including concurrent submissions.
    op.create_index(
        "uq_idv_active_user", "idv_applications", ["user_id"], unique=True,
        postgresql_where=sa.text("status IN ('PENDING', 'PROCESSING', 'READY_FOR_REVIEW', 'ERROR')"),
    )


def downgrade() -> None:
    # Automated audit entries cannot be represented in the old non-null schema.
    # Downgrade intentionally leaves this column nullable to preserve audit history.
    op.drop_table("task_outbox")
    op.drop_index("uq_idv_active_user", table_name="idv_applications")
    op.drop_column("pipeline_results", "stage_results")
    op.drop_column("face_verifications", "frame_paths")
