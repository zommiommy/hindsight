"""
Regression tests for the consolidation retry-storm guard.

When a consolidation task hits a transient error, the worker's generic retry
path raises ``RetryTaskAt`` to re-queue the operation (memory_engine.py, see
``execute_task``'s exception branch). During a long upstream outage, every
retain on the same bank also enqueues a fresh consolidation op via
``submit_async_consolidation``. Without dedup, each op then independently
consumes its own retry budget, multiplying load on the broken dependency.

The guard: if another consolidation op is already ``pending`` for the same
bank when the retry decision is made, skip the retry and let the other op
cover the work when it runs.
"""

import json
import uuid
from unittest.mock import patch

import pytest

from hindsight_api.worker.exceptions import RetryTaskAt


async def _ensure_bank(pool, bank_id: str) -> None:
    await pool.execute(
        "INSERT INTO banks (bank_id, name) VALUES ($1, $2) ON CONFLICT DO NOTHING",
        bank_id,
        bank_id,
    )


async def _insert_consolidation_op(pool, bank_id: str, operation_id: uuid.UUID, status: str) -> None:
    """Insert a consolidation row with the given ``status``."""
    payload = json.dumps(
        {
            "type": "consolidation",
            "operation_id": str(operation_id),
            "bank_id": bank_id,
        }
    )
    await pool.execute(
        """
        INSERT INTO async_operations (operation_id, bank_id, operation_type, status, task_payload)
        VALUES ($1, $2, 'consolidation', $3, $4::jsonb)
        """,
        operation_id,
        bank_id,
        status,
        payload,
    )


async def _cleanup(pool, bank_id: str, *operation_ids: uuid.UUID) -> None:
    if operation_ids:
        await pool.execute(
            "DELETE FROM async_operations WHERE operation_id = ANY($1::uuid[])",
            list(operation_ids),
        )
    await pool.execute("DELETE FROM banks WHERE bank_id = $1", bank_id)


@pytest.mark.asyncio
async def test_retry_skipped_when_other_pending_consolidation_exists(memory):
    """
    With another pending consolidation op already covering the same bank, a
    transient failure on the currently-executing op must NOT raise
    ``RetryTaskAt`` — the pending op will process the same unconsolidated
    rows when the worker picks it up. Without this guard, a long outage
    causes a retry storm: every retain enqueues a new op, and each op burns
    three retry slots against the same broken dependency.
    """
    bank_id = f"test-dedup-{uuid.uuid4().hex[:8]}"
    running_op_id = uuid.uuid4()
    peer_pending_op_id = uuid.uuid4()

    pool = await memory._get_pool()
    await _ensure_bank(pool, bank_id)
    # The op currently executing (drives execute_task below).
    await _insert_consolidation_op(pool, bank_id, running_op_id, status="processing")
    # A peer consolidation already pending for the same bank — the dedup guard
    # should fire because of this row.
    await _insert_consolidation_op(pool, bank_id, peer_pending_op_id, status="pending")

    task_dict = {
        "type": "consolidation",
        "operation_id": str(running_op_id),
        "bank_id": bank_id,
    }

    transient = RuntimeError("upstream LLM 503")
    with patch.object(memory, "_handle_consolidation", side_effect=transient):
        # The original exception must propagate as-is (the poller catches it
        # and calls _mark_failed). The point of the test is that it is NOT
        # converted to RetryTaskAt — pytest.raises(RuntimeError) asserts that
        # implicitly, since RetryTaskAt is not a RuntimeError subclass.
        with pytest.raises(RuntimeError, match="upstream LLM 503"):
            await memory.execute_task(task_dict)

    # Peer pending op must be untouched by the dedup guard.
    peer_row = await pool.fetchrow(
        "SELECT status FROM async_operations WHERE operation_id = $1",
        peer_pending_op_id,
    )
    assert peer_row["status"] == "pending"

    await _cleanup(pool, bank_id, running_op_id, peer_pending_op_id)


@pytest.mark.asyncio
async def test_retry_happens_when_no_other_pending_consolidation(memory):
    """
    Sanity check: with no peer pending op, the normal retry path still fires
    and ``RetryTaskAt`` is raised — the dedup guard must not regress the
    common-case behaviour.
    """
    bank_id = f"test-dedup-{uuid.uuid4().hex[:8]}"
    running_op_id = uuid.uuid4()

    pool = await memory._get_pool()
    await _ensure_bank(pool, bank_id)
    await _insert_consolidation_op(pool, bank_id, running_op_id, status="processing")

    task_dict = {
        "type": "consolidation",
        "operation_id": str(running_op_id),
        "bank_id": bank_id,
    }

    transient = RuntimeError("transient blip")
    with patch.object(memory, "_handle_consolidation", side_effect=transient):
        with pytest.raises(RetryTaskAt):
            await memory.execute_task(task_dict)

    await _cleanup(pool, bank_id, running_op_id)


@pytest.mark.asyncio
async def test_peer_only_dedups_when_same_bank(memory):
    """
    A pending consolidation for a DIFFERENT bank must not suppress the retry
    — the dedup guard is per-bank, not global.
    """
    bank_id_a = f"test-dedup-a-{uuid.uuid4().hex[:8]}"
    bank_id_b = f"test-dedup-b-{uuid.uuid4().hex[:8]}"
    running_op_id = uuid.uuid4()
    unrelated_pending_op_id = uuid.uuid4()

    pool = await memory._get_pool()
    await _ensure_bank(pool, bank_id_a)
    await _ensure_bank(pool, bank_id_b)
    await _insert_consolidation_op(pool, bank_id_a, running_op_id, status="processing")
    await _insert_consolidation_op(pool, bank_id_b, unrelated_pending_op_id, status="pending")

    task_dict = {
        "type": "consolidation",
        "operation_id": str(running_op_id),
        "bank_id": bank_id_a,
    }

    with patch.object(memory, "_handle_consolidation", side_effect=RuntimeError("blip")):
        with pytest.raises(RetryTaskAt):
            await memory.execute_task(task_dict)

    await _cleanup(pool, bank_id_a, running_op_id)
    await _cleanup(pool, bank_id_b, unrelated_pending_op_id)
