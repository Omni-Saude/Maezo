"""001 – Create contract_rules and contract_rule_changes tables.

Revision ID: 001_initial
Create Date: 2026-02-17
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID as PGUUID

revision = "001_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "contract_rules",
        sa.Column("id", PGUUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", sa.String(), nullable=False),
        sa.Column("payer_id", sa.String(), nullable=False),
        sa.Column(
            "category",
            sa.Enum("PRICING", "BUNDLE", "OPME", "AUTHORIZATION", "DISCOUNT", name="rulecategory"),
            nullable=False,
        ),
        sa.Column(
            "archetype",
            sa.Enum(
                "LOOKUP", "ROUTING", "PRICING", "AUTHORIZATION",
                "BUNDLING", "WHITELIST", "OPME", "DISCOUNT",
                name="rulearchetype",
            ),
            nullable=False,
        ),
        sa.Column("rule_definition", sa.JSON(), nullable=False),
        sa.Column("version", sa.String(), nullable=False, server_default="1.0.0"),
        sa.Column("effective_date", sa.Date(), nullable=False),
        sa.Column("expiry_date", sa.Date(), nullable=True),
        sa.Column(
            "status",
            sa.Enum("DRAFT", "ACTIVE", "INACTIVE", "ARCHIVED", name="rulestatus"),
            nullable=False,
            server_default="DRAFT",
        ),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
    )
    op.create_index("ix_contract_rules_tenant_id", "contract_rules", ["tenant_id"])

    op.create_table(
        "contract_rule_changes",
        sa.Column("id", PGUUID(as_uuid=True), primary_key=True),
        sa.Column("rule_id", PGUUID(as_uuid=True), sa.ForeignKey("contract_rules.id"), nullable=False),
        sa.Column("changed_by", sa.String(), nullable=False),
        sa.Column("changed_at", sa.DateTime(), nullable=True),
        sa.Column("change_type", sa.String(), nullable=False),
        sa.Column("old_value", sa.JSON(), nullable=True),
        sa.Column("new_value", sa.JSON(), nullable=True),
    )
    op.create_index("ix_contract_rule_changes_rule_id", "contract_rule_changes", ["rule_id"])


def downgrade() -> None:
    op.drop_index("ix_contract_rule_changes_rule_id", table_name="contract_rule_changes")
    op.drop_table("contract_rule_changes")
    op.drop_index("ix_contract_rules_tenant_id", table_name="contract_rules")
    op.drop_table("contract_rules")
    op.execute("DROP TYPE IF EXISTS rulecategory")
    op.execute("DROP TYPE IF EXISTS rulearchetype")
    op.execute("DROP TYPE IF EXISTS rulestatus")
