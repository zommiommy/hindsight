import pytest


@pytest.mark.asyncio
async def test_memory_units_has_status_column(memory) -> None:
    async with memory._pool.acquire() as conn:
        row = await conn.fetchrow("""
            SELECT column_default, is_nullable
              FROM information_schema.columns
             WHERE table_name = 'memory_units' AND column_name = 'status'
        """)
    assert row is not None
    assert "active" in (row["column_default"] or "")
    assert row["is_nullable"] == "NO"


@pytest.mark.asyncio
async def test_memory_units_status_check_constraint(memory) -> None:
    async with memory._pool.acquire() as conn:
        defn = await conn.fetchval("""
            SELECT pg_get_constraintdef(c.oid)
              FROM pg_constraint c
              JOIN pg_class t ON t.oid = c.conrelid
             WHERE t.relname = 'memory_units'
               AND c.conname = 'memory_units_status_check'
        """)
    assert defn is not None
    assert "active" in defn and "quarantined" in defn
