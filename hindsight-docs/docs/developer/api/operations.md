---
sidebar_position: 9
---

# Operations

Hindsight runs several maintenance and ingestion tasks asynchronously instead of blocking the API call that triggers them. These tasks share a single queue (`async_operations`) and a single worker pool, and the same REST endpoints — list, status, cancel, retry — work across every type.

This page explains each operation type, when it fires, and how to inspect or manage it.

:::tip Prerequisites
Make sure you've completed the [Quick Start](./quickstart) and understand [how retain works](./retain).
:::

## How operations work

When an API call needs background work, the request handler writes a row to the `async_operations` table with `status=pending` and returns immediately. A worker (running either in-process inside the API by default, or as a dedicated service — see [Services - Worker Service](../services#worker-service)) polls the table, claims pending rows, executes the corresponding handler, and marks the row `completed` or `failed`.

By default, every operation runs in-process: no external queue, no extra process to deploy. The same code paths support scaling out to dedicated worker processes when throughput demands it.

:::note Kafka Integration
Support for external streaming platforms like Kafka for scale-out processing is planned but **not available out of the box** in the current release.
:::

### Lifecycle

| Status | Meaning |
|--------|---------|
| `pending` | The row is queued. Either no worker has picked it up yet, or an extension has parked it via `next_retry_at` in the future (e.g., for backpressure). |
| `processing` | A worker has claimed the row and is actively running the handler. |
| `completed` | The handler returned successfully. |
| `failed` | The handler raised. `error_message` carries the reason; you can re-queue with `POST /…/retry`. |
| `cancelled` | The operation was cancelled via `DELETE /…/operations/{id}` before a worker picked it up. Cancelling a `processing` operation is not supported. |

The worker retries failed operations up to `HINDSIGHT_API_WORKER_MAX_RETRIES` times before settling on `failed`. Deterministic failures (e.g., invalid embedding dimensions, integrity violations) skip retries — they won't succeed by re-running.

## Operation types

Every operation has an `operation_type` in the database and a `task_type` in the payload. They're usually the same; the table below uses one column to keep things readable.

| Type | Trigger | Bank-deduped | What it does |
|------|---------|--------------|--------------|
| [`retain`](#retain) | `POST /memories` with `async=true`, or a `retain_batch` call | No | Runs the full retain pipeline (fact extraction, embedding, entity resolution, link creation) for the submitted content. |
| [`file_convert_retain`](#file_convert_retain) | `POST /documents/upload` for binary file uploads | No | Converts a binary file (PDF, DOCX, etc.) to text, then runs `retain` on the output. |
| [`consolidation`](#consolidation) | After every retain that produced new memories (when enabled); after deletes that invalidated observations | Yes | Synthesizes new world/experience memories into observations and mental models. |
| [`refresh_mental_model`](#refresh_mental_model) | Manual via `POST /mental-models/{id}/refresh` | No | Re-runs the source query for a single mental model and updates its content. |
| [`graph_maintenance`](#graph_maintenance) | After any mutation that leaves the graph with stale derived state — today, deletes that remove memory_units | Yes | Generic post-mutation cleanup queue. Currently runs one kind of work — `relink_unit`, topping up outgoing temporal/semantic links for units that lost neighbours to a delete. |
| [`webhook_delivery`](#webhook_delivery) | Configured webhooks fire after qualifying operations complete | No | Delivers the webhook payload, retrying on transient HTTP failures. |

### `retain`

Submitted by `POST /v1/default/banks/{bank_id}/memories` with `async=true`, or by the multi-item `retain_batch` call. The handler runs the same pipeline as a synchronous retain: fact extraction (LLM), embedding generation, entity resolution, and link creation (entity, temporal, semantic). For large batches Hindsight automatically splits the input into sub-batches and creates a parent operation that tracks the children — listing operations with `exclude_parents=true` filters them out.

Use async retain when you're ingesting thousands of items and don't want the HTTP call to hold for minutes. The `operation_id` in the response lets you poll for completion.

### `file_convert_retain`

Submitted by file upload endpoints. The handler runs MIME-specific conversion (PDF → text, DOCX → text, etc.) and then passes the extracted text into the retain pipeline. Failures here are **non-retryable** by default — a corrupted PDF or missing OCR won't improve on rerun, so the operation goes straight to `failed`.

### `consolidation`

Hindsight's higher-order memory layer. After retain commits new world/experience memories, consolidation reads them, groups by tag scope, and emits **observations** — short synthesized statements about patterns in those memories. Observations then feed mental model updates.

Triggered automatically:

- After every retain that added world/experience facts (gated by per-bank `enable_auto_consolidation` and `enable_observations`).
- After deletes that invalidated existing observations (the source memory disappeared → derived observations are stale → re-run with the surviving co-source memories).
- Manually via `POST /v1/default/banks/{bank_id}/consolidate`. Pass `observation_scopes` to consolidate only memories matching specific tag combinations.

**Bank-deduped**: while one `consolidation` job is pending for a bank, repeat submits return the existing `operation_id` instead of stacking. Once the job starts processing, the next submit becomes the next pending slot.

### `refresh_mental_model`

A mental model has a `source_query` that defines which memories it summarizes. Calling `POST /v1/default/banks/{bank_id}/mental-models/{id}/refresh` re-runs that query, re-summarizes the result, and updates the model's content in place. The operation is fire-and-forget — there's no synchronous refresh endpoint.

Requires an LLM provider; blocked at submit time when `HINDSIGHT_API_LLM_PROVIDER=none`.

### `graph_maintenance`

Generic worker for post-mutation graph cleanup. The queue table (`graph_maintenance_queue`) is keyed by `(bank_id, kind, target_id)` so future cleanup work can ride on the same surface without a new task type.

**Why it exists.** Some mutations leave behind derived state that's still readable but no longer accurate. Today the only example is link counts after a delete (see the `relink_unit` kind below). The framework is here so we don't grow a forest of near-identical task types as we add more reconciliation jobs (orphan entity pruning, stale cooccurrence cleanup, etc.).

**Bank-deduped.** While one `graph_maintenance` job is pending for a bank, repeat submits return the existing `operation_id` instead of stacking. Once the job starts processing, the next submit becomes the next pending slot — so work enqueued during processing gets picked up by the follow-up run.

**Worker loop.** Drains the queue in batches of 50 rows, groups each batch by `kind`, and dispatches each group to the matching handler. Batch + queue delete commit together, so a crash mid-job loses at most one batch (already-committed work persists). Rows of unknown `kind` (e.g. forward-compat — a future migration enqueues something the current build doesn't recognize) are dequeued and logged without crashing.

#### Kind: `relink_unit`

Reactively maintains a unit's outgoing temporal/semantic link counts after one of its neighbours is deleted.

**Why it's needed.** When a memory_unit is deleted, the foreign-key cascade removes any `memory_links` row referencing it — including entries that pointed *at* it from surviving units. Those surviving units now have fewer outgoing temporal/semantic links than the cap (20 temporal, 50 semantic), and the original retain pipeline only generates links for *newly inserted* units. Without a back-fill, surviving units stay permanently under-capped, which degrades graph-expansion recall over time.

**Trigger sites:**

- `DELETE /documents/{id}` (`delete_document`)
- `DELETE /memories/{id}` (`delete_memory_unit`)
- `POST /memories` with an existing `document_id` (the upsert path inside `handle_document_tracking`)

A full bank wipe (`delete_bank`) does *not* enqueue — there are no surviving units to top up.

**How it runs:**

1. Inside the existing delete transaction, before the cascade fires, Hindsight runs one indexed query to find the surviving units that had an outgoing temporal/semantic link to a doomed unit. Those IDs are written into the queue with `kind='relink_unit'` (`ON CONFLICT DO NOTHING`, so repeat deletes coalesce per target).
2. After the delete commits, `submit_async_graph_maintenance(bank_id)` schedules the worker.
3. For each claimed `relink_unit` target, the worker counts current outgoing links per type. If below the cap, it calls the same probes used at retain time (`fetch_temporal_neighbours`, the HNSW ANN scan in `compute_semantic_links_ann`) to find replacement neighbours. `bulk_insert_links` has `ON CONFLICT DO NOTHING` on the uniqueness key, so already-linked neighbours are skipped at insert time.

**Caveat (Oracle).** The semantic top-up uses the PG-specific HNSW probe; on Oracle it's caught and logged, and only the temporal top-up runs. Same asymmetry as the retain-time semantic link creation today.

### `webhook_delivery`

After certain operations complete (e.g., consolidation finishing on a bank with a registered webhook), Hindsight enqueues a `webhook_delivery` task. The handler POSTs the payload to the configured URL and retries on transient failures.

## Endpoints

All paths below are scoped by `bank_id`.

### List operations

```bash
GET /v1/default/banks/{bank_id}/operations
```

Query parameters:

| Param | Description |
|-------|-------------|
| `status` | Filter by `pending`, `processing`, `completed`, `failed`, `cancelled`. |
| `type` | Filter by `retain`, `file_convert_retain`, `consolidation`, `refresh_mental_model`, `graph_maintenance`, `webhook_delivery`. |
| `limit` | 1–100, default 20. |
| `offset` | Pagination offset. |
| `exclude_parents` | Exclude parent batch operations from results (large `retain_batch` calls create one parent + N children). |

```bash
curl "http://localhost:8000/v1/default/banks/my-bank/operations?type=graph_maintenance&status=pending"
```

Response:

```json
{
  "bank_id": "my-bank",
  "total": 1,
  "limit": 20,
  "offset": 0,
  "operations": [
    {
      "id": "550e8400-e29b-41d4-a716-446655440000",
      "task_type": "graph_maintenance",
      "items_count": 0,
      "document_id": null,
      "created_at": "2026-05-27T10:30:00Z",
      "status": "pending",
      "error_message": null,
      "retry_count": 0,
      "next_retry_at": null
    }
  ]
}
```

`items_count` is operation-specific — non-zero only for retain-shaped operations (it counts content items in the submission).

### Get operation status

```bash
GET /v1/default/banks/{bank_id}/operations/{operation_id}
```

Include the submission payload with `?include_payload=true`.

### Cancel a pending operation

```bash
curl -X DELETE \
  "http://localhost:8000/v1/default/banks/my-bank/operations/550e8400-e29b-41d4-a716-446655440000"
```

Returns `409` if the operation is already in `processing`, `completed`, or `failed` state.

### Retry a failed operation

```bash
curl -X POST \
  "http://localhost:8000/v1/default/banks/my-bank/operations/550e8400-e29b-41d4-a716-446655440000/retry"
```

The row's status resets to `pending` and the worker picks it up again. Returns `409` if the operation isn't in `failed` or `cancelled` state.

```json
{
  "success": true,
  "message": "Operation 550e8400-e29b-41d4-a716-446655440000 queued for retry",
  "operation_id": "550e8400-e29b-41d4-a716-446655440000"
}
```

## Async retain example

```bash
curl -X POST "http://localhost:8000/v1/default/banks/my-bank/memories" \
  -H "Content-Type: application/json" \
  -d '{
    "items": [
      {"content": "Alice joined Google in 2023"},
      {"content": "Bob prefers Python over JavaScript"}
    ],
    "async": true
  }'
```

```json
{
  "success": true,
  "bank_id": "my-bank",
  "items_count": 2,
  "async": true,
  "operation_id": "550e8400-e29b-41d4-a716-446655440000"
}
```

Poll until the matching operation flips to `completed`:

```bash
curl "http://localhost:8000/v1/default/banks/my-bank/operations/550e8400-e29b-41d4-a716-446655440000"
```

## Worker tuning

Each worker has a single concurrency budget (`HINDSIGHT_API_WORKER_MAX_SLOTS`, default 10) shared across all operation types. Per-type slot reservations (`HINDSIGHT_API_WORKER_<TYPE>_MAX_SLOTS`) carve out guaranteed capacity within that budget; remaining slots form a shared pool any type can use. See [Configuration → Worker Configuration](../configuration#worker-configuration) for the full table.

For most deployments the defaults are fine. Reserve slots for an operation type if you've seen it starved by a flood of another type (e.g., a long file_convert_retain blocking graph_maintenance on a deletion-heavy workload).

## Next Steps

- [**Documents**](./documents) — Track document sources
- [**Memory Banks**](./memory-banks) — Configure bank settings
