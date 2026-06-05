"""Add status column to memory_units (Memory Guard quarantine).

Revision ID: bb22cc33dd44
Revises: z1u2v3w4x5y6
Create Date: 2026-06-04
"""

from collections.abc import Sequence

from alembic import context, op

from hindsight_api.alembic._dialect import run_for_dialect

revision: str = "bb22cc33dd44"
down_revision: str | Sequence[str] | None = "z1u2v3w4x5y6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_VALID = "('active','quarantined','released')"


def _pg_schema_prefix() -> str:
    schema = context.config.get_main_option("target_schema")
    return f'"{schema}".' if schema else ""


def _pg_upgrade() -> None:
    s = _pg_schema_prefix()
    op.execute(f"ALTER TABLE {s}memory_units ADD COLUMN IF NOT EXISTS status TEXT NOT NULL DEFAULT 'active'")
    op.execute(f"ALTER TABLE {s}memory_units ADD CONSTRAINT memory_units_status_check CHECK (status IN {_VALID})")
    op.execute(
        f"CREATE INDEX IF NOT EXISTS idx_memory_units_status "
        f"ON {s}memory_units (bank_id, status) WHERE status <> 'active'"
    )


def _pg_downgrade() -> None:
    s = _pg_schema_prefix()
    op.execute(f"DROP INDEX IF EXISTS {s}idx_memory_units_status")
    op.execute(f"ALTER TABLE {s}memory_units DROP CONSTRAINT IF EXISTS memory_units_status_check")
    op.execute(f"ALTER TABLE {s}memory_units DROP COLUMN IF EXISTS status")


def _oracle_upgrade() -> None:
    op.execute("ALTER TABLE memory_units ADD status VARCHAR2(32) DEFAULT 'active' NOT NULL")
    op.execute(f"ALTER TABLE memory_units ADD CONSTRAINT memory_units_status_check CHECK (status IN {_VALID})")
    op.execute("CREATE INDEX idx_memory_units_status ON memory_units (bank_id, status)")


def _oracle_downgrade() -> None:
    op.execute("DROP INDEX idx_memory_units_status")
    op.execute("ALTER TABLE memory_units DROP CONSTRAINT memory_units_status_check")
    op.execute("ALTER TABLE memory_units DROP COLUMN status")


def upgrade() -> None:
    run_for_dialect(pg=_pg_upgrade, oracle=_oracle_upgrade)


def downgrade() -> None:
    run_for_dialect(pg=_pg_downgrade, oracle=_oracle_downgrade)
