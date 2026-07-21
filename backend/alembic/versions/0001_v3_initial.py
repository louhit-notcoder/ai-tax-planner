"""Green Papaya V3 initial PostgreSQL schema.

Revision ID: 0001_v3_initial
Revises:
Create Date: 2026-07-21
"""
from __future__ import annotations

from alembic import op

from app.database import Base
from app import db_models  # noqa: F401

revision = "0001_v3_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    Base.metadata.create_all(bind=bind)
    if bind.dialect.name == "postgresql":
        op.execute("""
        CREATE OR REPLACE FUNCTION gp_prevent_mutation() RETURNS trigger AS $$
        BEGIN
          RAISE EXCEPTION 'immutable Green Papaya record cannot be updated or deleted';
        END;
        $$ LANGUAGE plpgsql;
        """)
        for table in ("audit_events", "fact_snapshots"):
            op.execute(f"DROP TRIGGER IF EXISTS {table}_immutable ON {table}")
            op.execute(f"CREATE TRIGGER {table}_immutable BEFORE UPDATE OR DELETE ON {table} FOR EACH ROW EXECUTE FUNCTION gp_prevent_mutation()")


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        for table in ("audit_events", "fact_snapshots"):
            op.execute(f"DROP TRIGGER IF EXISTS {table}_immutable ON {table}")
        op.execute("DROP FUNCTION IF EXISTS gp_prevent_mutation()")
    Base.metadata.drop_all(bind=bind)
