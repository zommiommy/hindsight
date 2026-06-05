"""Merge maintenance routines repair and memory guard heads.

Revision ID: f1e2d3c4b5a6
Revises: b2d4f6a8c1e3, dd44ee55ff66
Create Date: 2026-06-08

The rebase of feat/memory-defense-extension onto main produced two parallel
Alembic heads: b2d4f6a8c1e3 (server-side maintenance routine repair, from
main) and dd44ee55ff66 (Memory Guard quarantine status column + history
split merge, from the feature branch). Structural merge revision with no
schema changes; only job is to unify the DAG so ``alembic upgrade head``
is unambiguous again.
"""

from collections.abc import Sequence

from hindsight_api.alembic._dialect import run_for_dialect

revision: str = "f1e2d3c4b5a6"
down_revision: str | Sequence[str] | None = ("b2d4f6a8c1e3", "dd44ee55ff66")
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _pg_upgrade() -> None:
    pass


def _pg_downgrade() -> None:
    pass


def _oracle_upgrade() -> None:
    pass


def _oracle_downgrade() -> None:
    pass


def upgrade() -> None:
    run_for_dialect(pg=_pg_upgrade, oracle=_oracle_upgrade)


def downgrade() -> None:
    run_for_dialect(pg=_pg_downgrade, oracle=_oracle_downgrade)
