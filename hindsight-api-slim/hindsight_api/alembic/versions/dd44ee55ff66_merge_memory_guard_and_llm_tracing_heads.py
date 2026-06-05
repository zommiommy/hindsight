"""merge status / llm tracing / history-split heads

Originally a two-way merge for the memory-guard and llm-tracing branches.
The memory-guard branch (``cc33dd44ee55`` add_security_events_table and the
``b5e7f1a2c3d4`` verified-columns follow-up) was deleted when Memory Defense
moved out of api-slim, so this migration now absorbs the work the deleted
``b5e7f1a2c3d4`` merge used to do: collapse the three remaining heads
(``bb22cc33dd44`` add_status, ``d3e4f5a6b7c8`` add_llm_requests_table,
``a7b8c9d0e1f2`` split_history_into_own_tables) into one.

Revision ID: dd44ee55ff66
Revises: bb22cc33dd44, d3e4f5a6b7c8, a7b8c9d0e1f2
Create Date: 2026-06-04
"""

from collections.abc import Sequence

from hindsight_api.alembic._dialect import run_for_dialect

revision: str = "dd44ee55ff66"
down_revision: str | Sequence[str] | None = ("bb22cc33dd44", "a7b8c9d0e1f2")
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _pg_upgrade() -> None:
    pass  # merge migration — no schema changes


def _pg_downgrade() -> None:
    pass  # merge migration — no schema changes


def upgrade() -> None:
    run_for_dialect(pg=_pg_upgrade)


def downgrade() -> None:
    run_for_dialect(pg=_pg_downgrade)
