"""Add an index on memory_links.bank_id for bank-scoped queries (PostgreSQL).

``bank_id`` was added to ``memory_links`` in ``c5d6e7f8a9b0`` precisely so that
bank-scoped reads (e.g. the stats endpoint) could filter on the link table
directly instead of joining ``memory_units`` — that JOIN took 18+ seconds on
banks with millions of links. The column landed without an index, so every
``bank_id = $1`` predicate still falls back to a sequential scan over the whole
table.

This adds the missing btree. The Oracle baseline (``o1a2b3c4d5e6``) already
creates ``idx_ml_bank_id`` on ``memory_links(bank_id)``, so the asymmetry is
deliberate: only the PostgreSQL dialect was missing the index. The Oracle slot
is intentionally absent.

``memory_links`` can hold tens of millions of rows, so the index is built
CONCURRENTLY to avoid taking a write lock on the table. CONCURRENTLY cannot run
inside a transaction block, so the statement runs in an ``autocommit_block()``;
``IF NOT EXISTS`` keeps it idempotent across retries and re-migrated tenant
schemas.

Revision ID: 2071c7518f88
Revises: a1d3f5b7c9e2
Create Date: 2026-06-16
"""

from collections.abc import Sequence

from alembic import context, op

from hindsight_api.alembic._dialect import run_for_dialect

revision: str = "2071c7518f88"
down_revision: str | Sequence[str] | None = "a1d3f5b7c9e2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _get_schema_prefix() -> str:
    """Schema-qualifier for raw SQL on PG (multi-tenant search_path)."""
    schema = context.config.get_main_option("target_schema")
    return f'"{schema}".' if schema else ""


def _pg_upgrade() -> None:
    schema = _get_schema_prefix()

    # CREATE INDEX CONCURRENTLY cannot run inside a transaction block; the
    # autocommit_block runs the statement outside Alembic's migration
    # transaction. IF NOT EXISTS makes it idempotent on retry.
    with op.get_context().autocommit_block():
        op.execute(f"CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_memory_links_bank_id ON {schema}memory_links(bank_id)")


def _pg_downgrade() -> None:
    schema = _get_schema_prefix()
    with op.get_context().autocommit_block():
        op.execute(f"DROP INDEX CONCURRENTLY IF EXISTS {schema}idx_memory_links_bank_id")


def upgrade() -> None:
    run_for_dialect(pg=_pg_upgrade)


def downgrade() -> None:
    run_for_dialect(pg=_pg_downgrade)
