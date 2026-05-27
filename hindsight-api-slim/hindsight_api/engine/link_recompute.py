"""Async link top-up after document/unit deletes.

When a memory_unit is deleted, the FK cascade removes its outgoing/incoming
``memory_links`` rows. Other units that had this unit in their top-K
``temporal``/``semantic`` neighbours therefore lose links and stay
permanently under-capped — the original retain path only generates links
for newly-inserted units, never re-evaluates surviving ones.

This module fixes that staleness reactively:

* :func:`enqueue_link_recompute_victims` is called inside the delete
  transaction by every code path that removes memory_units. It captures the
  ``from_unit_id`` of every outgoing temporal/semantic link that targeted a
  deleted unit and writes those IDs into ``link_recompute_queue``. The
  capture happens *before* the cascade fires so the rows still exist.
* :func:`run_link_recompute_job` is the worker handler. It drains the
  queue in batches, runs the same probes used at retain time
  (:func:`fetch_temporal_neighbors`, :func:`compute_semantic_links_ann`) to
  find replacement neighbours, and inserts top-up links. ``bulk_insert_links``
  has ``ON CONFLICT DO NOTHING`` on the uniqueness key, so we can re-probe
  freely and the DB de-dupes.

The worker dedupes on bank: a second job for the same bank is dropped while
one is pending. Once processing starts, a new job becomes the *next* pending
slot — which is what we want, so victims enqueued during processing get
picked up by the follow-up run.
"""

from __future__ import annotations

import logging
import time
import uuid as uuid_module
from typing import TYPE_CHECKING, Any

from ..models import RequestContext
from .db.base import DatabaseConnection
from .retain.link_utils import (
    MAX_TEMPORAL_LINKS_PER_UNIT,
    _bulk_insert_links,
    _normalize_datetime,
    compute_semantic_links_ann,
)
from .schema import fq_table

if TYPE_CHECKING:
    from .memory_engine import MemoryEngine

logger = logging.getLogger(__name__)

# Mirrors the ``top_k`` default in ``compute_semantic_links_ann`` at retain
# time. If you change one, change the other — otherwise victims would either
# never reach the cap (probe returns less than the cap) or stay perpetually
# under it (cap is higher than retain creates).
MAX_SEMANTIC_LINKS_PER_UNIT = 50

# Worker fetches this many victims per loop iteration. Bounds per-iteration
# probe/insert latency so a 10k-victim job doesn't hold a worker slot for
# minutes. Chosen so the typical iteration runs in well under 1s.
_DRAIN_BATCH_SIZE = 50


async def enqueue_link_recompute_victims(
    conn: DatabaseConnection,
    bank_id: str,
    deleted_unit_ids: list[str],
    ops: Any,
) -> int:
    """Enqueue surviving units whose outgoing temporal/semantic links pointed at
    ``deleted_unit_ids`` for later link top-up.

    Must run inside the same transaction that deletes the units, *before* the
    cascade fires — once the rows are gone, the join that finds the victims
    returns nothing.

    Args:
        conn: Database connection inside the active delete transaction.
        bank_id: Bank owning the deleted units.
        deleted_unit_ids: Memory_unit IDs about to be (or being) deleted.
        ops: ``DataAccessOps`` instance, supplies the dialect-specific
            bulk-insert path.

    Returns:
        Number of distinct victim units enqueued (after dedup against units
        already in the queue).
    """
    if not deleted_unit_ids:
        return 0

    deleted_uuids = [uuid_module.UUID(uid) if isinstance(uid, str) else uid for uid in deleted_unit_ids]
    deleted_str_set = {str(uid) for uid in deleted_uuids}

    # Find units (other than the ones being deleted) that have an outgoing
    # temporal/semantic link pointing at a doomed unit. Entity links are
    # intentionally excluded — they're scheduled for removal and would only
    # add noise to the recompute job.
    victim_rows = await conn.fetch(
        f"""
        SELECT DISTINCT from_unit_id
        FROM {fq_table("memory_links")}
        WHERE to_unit_id = ANY($1::uuid[])
          AND bank_id = $2
          AND link_type IN ('temporal', 'semantic')
        """,
        deleted_uuids,
        bank_id,
    )

    victim_ids = [row["from_unit_id"] for row in victim_rows if str(row["from_unit_id"]) not in deleted_str_set]

    if not victim_ids:
        return 0

    await ops.enqueue_link_recompute_victims(
        conn,
        fq_table("link_recompute_queue"),
        bank_id,
        victim_ids,
    )

    logger.debug(
        f"[LINK_RECOMPUTE] Enqueued {len(victim_ids)} victims in bank={bank_id} (deleted {len(deleted_unit_ids)} units)"
    )
    return len(victim_ids)


async def run_link_recompute_job(
    memory_engine: "MemoryEngine",
    bank_id: str,
    request_context: RequestContext,
    operation_id: str | None = None,
) -> dict[str, int]:
    """Drain ``link_recompute_queue`` for ``bank_id`` until empty.

    Each iteration claims up to ``_DRAIN_BATCH_SIZE`` victims, computes
    replacement temporal/semantic links for the ones below cap, inserts the
    new links, and commits. A worker crash mid-job loses at most the current
    batch (already-committed top-ups persist).

    Returns:
        Dict with ``victims_processed`` (claimed from queue) and ``links_added``
        (rows inserted; may be lower than victims if everyone was already at
        cap).
    """
    del request_context  # accepted for symmetry with other run_*_job helpers
    backend = await memory_engine._get_backend()
    ops = backend.ops

    total_victims = 0
    total_links = 0
    iterations = 0
    job_start = time.time()

    # Per-iteration loop: claim → top up → commit. Continues until the queue
    # for this bank is drained. We rely on submit-time dedup to keep at most
    # one job per bank running, so no need for SKIP LOCKED.
    while True:
        from .memory_engine import acquire_with_retry

        async with acquire_with_retry(backend) as conn:
            async with conn.transaction():
                victim_ids = await ops.claim_link_recompute_batch(
                    conn,
                    fq_table("link_recompute_queue"),
                    bank_id,
                    _DRAIN_BATCH_SIZE,
                )
                if not victim_ids:
                    break

                links_added = await _topup_batch(conn, bank_id, victim_ids, ops, backend)

        total_victims += len(victim_ids)
        total_links += links_added
        iterations += 1

        if iterations > 10000:
            # Defensive guard against runaway loops — at 50 victims/iter that's
            # 500k victims, far beyond any realistic single-bank backlog.
            logger.error(
                f"[LINK_RECOMPUTE] bank={bank_id} hit iteration cap ({iterations}); "
                f"aborting drain (processed={total_victims}, links_added={total_links})"
            )
            break

    elapsed = time.time() - job_start
    logger.info(
        f"[LINK_RECOMPUTE] bank={bank_id} done: victims_processed={total_victims}, "
        f"links_added={total_links}, iterations={iterations}, elapsed={elapsed:.2f}s, "
        f"operation_id={operation_id}"
    )
    return {"victims_processed": total_victims, "links_added": total_links}


async def _topup_batch(
    conn: DatabaseConnection,
    bank_id: str,
    victim_ids: list[str],
    ops: Any,
    backend: Any,
) -> int:
    """Top up links for a single batch of victims. Returns rows inserted."""
    # Load each victim's metadata. Victims whose units were deleted between
    # enqueue and now silently drop out — exactly the no-op behaviour we want
    # for stale queue rows.
    victim_uuids = [uuid_module.UUID(vid) for vid in victim_ids]
    victim_rows = await conn.fetch(
        f"""
        SELECT id::text AS id, event_date, fact_type, embedding::text AS embedding
        FROM {fq_table("memory_units")}
        WHERE id = ANY($1::uuid[])
          AND bank_id = $2
          AND fact_type IN ('experience', 'world')
        """,
        victim_uuids,
        bank_id,
    )

    if not victim_rows:
        return 0

    alive_uuids = [uuid_module.UUID(row["id"]) for row in victim_rows]

    # Count current outgoing temporal/semantic links per victim so we only
    # probe for the ones genuinely below cap. Saves the bulk of the work when
    # most victims still have plenty of links.
    count_rows = await conn.fetch(
        f"""
        SELECT from_unit_id, link_type, COUNT(*) AS cnt
        FROM {fq_table("memory_links")}
        WHERE from_unit_id = ANY($1::uuid[])
          AND bank_id = $2
          AND link_type IN ('temporal', 'semantic')
        GROUP BY from_unit_id, link_type
        """,
        alive_uuids,
        bank_id,
    )
    counts: dict[tuple[str, str], int] = {}
    for row in count_rows:
        counts[(str(row["from_unit_id"]), row["link_type"])] = int(row["cnt"])

    # --- Temporal top-up ---
    temporal_needs = [r for r in victim_rows if counts.get((r["id"], "temporal"), 0) < MAX_TEMPORAL_LINKS_PER_UNIT]
    new_links: list[tuple] = []

    if temporal_needs:
        lateral_unit_ids = [uuid_module.UUID(r["id"]) for r in temporal_needs if r["event_date"] is not None]
        lateral_event_dates = [
            _normalize_datetime(r["event_date"]) for r in temporal_needs if r["event_date"] is not None
        ]
        lateral_fact_types = [r["fact_type"] for r in temporal_needs if r["event_date"] is not None]

        if lateral_unit_ids:
            rows = await ops.fetch_temporal_neighbors(
                conn,
                fq_table("memory_units"),
                bank_id,
                lateral_unit_ids,
                lateral_event_dates,
                lateral_fact_types,
                MAX_TEMPORAL_LINKS_PER_UNIT,
            )
            for row in rows:
                time_diff_h = float(row["time_diff_hours"])
                # Mirror the 24h window enforced at retain time. The bidirectional
                # index scan returns the K closest neighbours regardless of
                # window, so we filter here.
                if time_diff_h > 24:
                    continue
                weight = max(0.3, 1.0 - (time_diff_h / 24))
                new_links.append((row["from_id"], str(row["id"]), "temporal", weight, None))

    # --- Semantic top-up ---
    # ANN must run on its own connection: it opens a nested transaction with
    # SET LOCAL hnsw.ef_search + CREATE TEMP TABLE ON COMMIT DROP, and nesting
    # that inside our current write transaction would commit our writes early.
    semantic_needs = [
        r
        for r in victim_rows
        if counts.get((r["id"], "semantic"), 0) < MAX_SEMANTIC_LINKS_PER_UNIT and r["embedding"] is not None
    ]
    if semantic_needs:
        from .memory_engine import acquire_with_retry

        seed_ids = [r["id"] for r in semantic_needs]
        seed_embs = [r["embedding"] for r in semantic_needs]
        seed_ftypes = [r["fact_type"] for r in semantic_needs]
        async with acquire_with_retry(backend) as ann_conn:
            try:
                ann_links = await compute_semantic_links_ann(
                    ann_conn,
                    bank_id,
                    seed_ids,
                    seed_embs,
                    fact_types=seed_ftypes,
                )
                # Strip self-links (rare but possible because the ANN probe
                # has no exclude list — see the comment in compute_semantic_links_ann).
                ann_links = [lnk for lnk in ann_links if lnk[0] != lnk[1]]
                new_links.extend(ann_links)
            except Exception as e:
                # ANN uses PG-specific HNSW syntax; on dialects/configs where
                # it isn't available we still want the temporal top-up to land.
                logger.warning(f"[LINK_RECOMPUTE] Semantic top-up failed for bank={bank_id}: {type(e).__name__}: {e}")

    if not new_links:
        return 0

    await _bulk_insert_links(
        conn,
        new_links,
        bank_id=bank_id,
        skip_exists_check=False,
        ops=ops,
    )
    return len(new_links)
