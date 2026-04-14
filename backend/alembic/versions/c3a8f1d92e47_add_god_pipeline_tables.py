"""add_god_pipeline_tables

Revision ID: c3a8f1d92e47
Revises: 55d370d2a88e
Create Date: 2026-04-11 12:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "c3a8f1d92e47"
down_revision: Union[str, None] = "55d370d2a88e"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # --- New tables ---

    op.create_table(
        "approved_countries",
        sa.Column("id", sa.dialects.postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("country_code", sa.String(3), unique=True, nullable=False),
        sa.Column("country_name", sa.String(100), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="active"),
        sa.Column("requires_edd", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_approved_countries_country_code", "approved_countries", ["country_code"], unique=True)

    op.create_table(
        "document_class_rules",
        sa.Column("id", sa.dialects.postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("country_code", sa.String(3), nullable=False),
        sa.Column("document_class", sa.String(10), nullable=False),
        sa.Column("application_type", sa.String(50), nullable=False, server_default="kyc_standard"),
        sa.Column("is_required", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("is_allowed", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_document_class_rules_country_code", "document_class_rules", ["country_code"])

    op.create_table(
        "watchlist_entries",
        sa.Column("id", sa.dialects.postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("id_number", sa.String(50), nullable=False),
        sa.Column("full_name", sa.String(255), nullable=True),
        sa.Column("reason", sa.String(500), nullable=False),
        sa.Column("source", sa.String(100), nullable=False, server_default="manual"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_watchlist_entries_id_number", "watchlist_entries", ["id_number"])

    op.create_table(
        "pipeline_results",
        sa.Column("id", sa.dialects.postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "application_id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            sa.ForeignKey("idv_applications.id", ondelete="CASCADE"),
            unique=True,
            nullable=False,
        ),
        sa.Column("pipeline_version", sa.String(20), nullable=False, server_default="1.0"),
        # Stage results
        sa.Column("stage_0_result", postgresql.JSONB(), nullable=True),
        sa.Column("stage_1_result", postgresql.JSONB(), nullable=True),
        sa.Column("stage_2_result", postgresql.JSONB(), nullable=True),
        sa.Column("stage_3_result", postgresql.JSONB(), nullable=True),
        sa.Column("stage_4_result", postgresql.JSONB(), nullable=True),
        # Channel scores
        sa.Column("channel_a_score", sa.Float(), nullable=True),
        sa.Column("channel_b_score", sa.Float(), nullable=True),
        sa.Column("channel_c_score", sa.Float(), nullable=True),
        sa.Column("channel_d_score", sa.Float(), nullable=True),
        sa.Column("channel_e_score", sa.Float(), nullable=True),
        # Scoring
        sa.Column("weighted_total", sa.Float(), nullable=True),
        sa.Column("hard_rules_result", postgresql.JSONB(), nullable=True),
        sa.Column("decision_override", sa.String(20), nullable=True),
        sa.Column("final_decision", sa.String(20), nullable=True),
        # Audit
        sa.Column("reason_codes", postgresql.JSONB(), nullable=True),
        sa.Column("flags", postgresql.JSONB(), nullable=True),
        # Timestamps
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_pipeline_results_application_id", "pipeline_results", ["application_id"], unique=True)

    # --- Add columns to existing tables ---

    # idv_applications
    op.add_column("idv_applications", sa.Column("pipeline_version", sa.String(20), nullable=True))
    op.add_column("idv_applications", sa.Column("pipeline_decision", sa.String(20), nullable=True))

    # documents
    op.add_column("documents", sa.Column("document_class", sa.String(10), nullable=True))
    op.add_column("documents", sa.Column("issuing_country", sa.String(3), nullable=True))
    op.add_column("documents", sa.Column("ocr_confidence", postgresql.JSONB(), nullable=True))
    op.add_column("documents", sa.Column("normalized_data", postgresql.JSONB(), nullable=True))
    op.add_column("documents", sa.Column("liveness_score", sa.Float(), nullable=True))
    op.add_column("documents", sa.Column("liveness_details", postgresql.JSONB(), nullable=True))

    # Seed common approved countries
    op.execute("""
        INSERT INTO approved_countries (id, country_code, country_name, status, requires_edd) VALUES
        (gen_random_uuid(), 'ARE', 'United Arab Emirates', 'active', false),
        (gen_random_uuid(), 'SAU', 'Saudi Arabia', 'active', false),
        (gen_random_uuid(), 'IND', 'India', 'active', false),
        (gen_random_uuid(), 'PAK', 'Pakistan', 'active', false),
        (gen_random_uuid(), 'EGY', 'Egypt', 'active', false),
        (gen_random_uuid(), 'JOR', 'Jordan', 'active', false),
        (gen_random_uuid(), 'GBR', 'United Kingdom', 'active', false),
        (gen_random_uuid(), 'USA', 'United States', 'active', false),
        (gen_random_uuid(), 'PHL', 'Philippines', 'active', false),
        (gen_random_uuid(), 'BGD', 'Bangladesh', 'active', false),
        (gen_random_uuid(), 'NPL', 'Nepal', 'active', false),
        (gen_random_uuid(), 'LKA', 'Sri Lanka', 'active', false),
        (gen_random_uuid(), 'CHN', 'China', 'active', false),
        (gen_random_uuid(), 'DEU', 'Germany', 'active', false),
        (gen_random_uuid(), 'FRA', 'France', 'active', false)
    """)

    # Seed document class rules (default: TD3 and TD1 allowed for kyc_standard)
    op.execute("""
        INSERT INTO document_class_rules (id, country_code, document_class, application_type, is_required, is_allowed) VALUES
        (gen_random_uuid(), 'ARE', 'TD3', 'kyc_standard', false, true),
        (gen_random_uuid(), 'ARE', 'TD1', 'kyc_standard', false, true),
        (gen_random_uuid(), 'SAU', 'TD3', 'kyc_standard', false, true),
        (gen_random_uuid(), 'SAU', 'TD1', 'kyc_standard', false, true),
        (gen_random_uuid(), 'IND', 'TD3', 'kyc_standard', false, true),
        (gen_random_uuid(), 'IND', 'TD1', 'kyc_standard', false, true),
        (gen_random_uuid(), 'PAK', 'TD3', 'kyc_standard', false, true),
        (gen_random_uuid(), 'PAK', 'TD1', 'kyc_standard', false, true)
    """)


def downgrade() -> None:
    # Drop added columns
    op.drop_column("documents", "liveness_details")
    op.drop_column("documents", "liveness_score")
    op.drop_column("documents", "normalized_data")
    op.drop_column("documents", "ocr_confidence")
    op.drop_column("documents", "issuing_country")
    op.drop_column("documents", "document_class")
    op.drop_column("idv_applications", "pipeline_decision")
    op.drop_column("idv_applications", "pipeline_version")

    # Drop new tables
    op.drop_index("ix_pipeline_results_application_id", table_name="pipeline_results")
    op.drop_table("pipeline_results")
    op.drop_index("ix_watchlist_entries_id_number", table_name="watchlist_entries")
    op.drop_table("watchlist_entries")
    op.drop_index("ix_document_class_rules_country_code", table_name="document_class_rules")
    op.drop_table("document_class_rules")
    op.drop_index("ix_approved_countries_country_code", table_name="approved_countries")
    op.drop_table("approved_countries")
