---
sidebar_position: 31
title: "Hindsight Tracing in Pydantic Logfire | Observability Guide"
description: "Send Hindsight's OpenTelemetry traces — retain, recall, reflect, and the LLM calls inside them — to Pydantic Logfire with three environment variables. Zero code changes."
---

# Hindsight in Pydantic Logfire

[Pydantic Logfire](https://logfire.pydantic.dev) is an OpenTelemetry-native observability platform from the Pydantic team. Hindsight already emits OpenTelemetry spans for every memory operation, so wiring it up to Logfire is a configuration change — no code changes, no new dependency.

When you do, every `retain`, `recall`, and `reflect` shows up in Logfire as a structured span with sub-spans for the LLM calls Hindsight makes internally (fact extraction, query analysis, reranking, reflection synthesis).

## Prerequisites

- A running Hindsight instance (Cloud or self-hosted) — version 0.5+
- A [Pydantic Logfire](https://logfire.pydantic.dev) account
- A Logfire **write token** for the project you want to send traces to

## Configuration

Set three environment variables on the Hindsight server:

```bash
export HINDSIGHT_API_OTEL_TRACES_ENABLED=true
export HINDSIGHT_API_OTEL_EXPORTER_OTLP_ENDPOINT=https://logfire-api.pydantic.dev/v1/traces
export HINDSIGHT_API_OTEL_EXPORTER_OTLP_HEADERS="Authorization=Bearer ${LOGFIRE_TOKEN}"
```

Optional but useful — name your service so traces are easy to group:

```bash
export HINDSIGHT_API_OTEL_SERVICE_NAME=hindsight
export HINDSIGHT_API_OTEL_DEPLOYMENT_ENVIRONMENT=production   # or "staging" / "dev"
```

Restart the Hindsight API. Generate some traffic (run an agent, call retain/recall/reflect from a client) and traces appear in Logfire within seconds.

## What you see in Logfire

Hindsight emits the span hierarchy already documented in the [Distributed Tracing reference](./monitoring#distributed-tracing) — Logfire renders it as a tree:

```
hindsight.recall                                (220 ms)
├─ hindsight.recall_embedding                   ( 38 ms)
├─ hindsight.recall_retrieval                   (110 ms)
│   ├─ semantic search
│   ├─ BM25
│   ├─ graph expansion
│   └─ temporal filter
├─ hindsight.recall_fusion                      (  9 ms)
└─ hindsight.recall_rerank                      ( 60 ms)
```

Reflect calls show their internal LLM tool-loop:

```
hindsight.reflect                               (1.4 s)
├─ hindsight.reflect_tool_call (recall)
├─ chat openai:gpt-4o-mini
├─ hindsight.reflect_tool_call (lookup)
└─ chat openai:gpt-4o-mini
```

LLM child spans follow the [GenAI semantic conventions](https://opentelemetry.io/docs/specs/semconv/gen-ai/) — Logfire automatically picks up prompts, completions, token counts, and finish reasons.

## Pairing with Pydantic AI traces

If your application uses [Pydantic AI](https://ai.pydantic.dev), add Logfire's Pydantic-AI auto-instrumentation in your client process so the agent run becomes the parent of each Hindsight span:

```python
import logfire

logfire.configure()
logfire.instrument_pydantic_ai()
```

You'll see `agent.run` at the top of each trace, with `hindsight.recall` / `hindsight.retain` / `hindsight.reflect` nested underneath as the agent calls them.

For the broader Pydantic-AI + Hindsight integration, see the [Pydantic AI guide](/sdks/integrations/pydantic-ai).

## Filtering and dashboards

A few queries that are useful out of the box in Logfire:

| What you want to see | Logfire query |
|---|---|
| All retain failures last 24h | `name = "hindsight.retain" and level = "error"` |
| p95 recall latency by deployment | `name = "hindsight.recall"`, group by `deployment.environment`, aggregate p95 of `duration` |
| Empty recalls (zero results) | `name = "hindsight.recall" and attributes.result_count = 0` |
| Reflect tool-call depth | `name = "hindsight.reflect"`, count `hindsight.reflect_tool_call` children |

## Self-hosted Hindsight

The exact same env vars apply if you run Hindsight via Docker or Kubernetes — set them on the API container and Logfire receives traces. Hindsight Cloud users can request these be enabled per-org by [contacting support](mailto:support@vectorize.io).

## Troubleshooting

**No traces appearing in Logfire**

Check the API logs for `OTLP exporter` warnings. Common causes:

- `HINDSIGHT_API_OTEL_EXPORTER_OTLP_HEADERS` missing the `Authorization=Bearer` prefix
- Wrong endpoint — should be `/v1/traces`, not the project URL from your dashboard
- Token permissions — Logfire write tokens are per-project; the token must match the project you expect traces in

**Traces appear but lack LLM details**

Confirm `HINDSIGHT_API_OTEL_TRACES_ENABLED=true`. Without it, no spans are emitted. Hindsight's tracing is opt-in and disabled by default.

**Logfire dashboard sluggish on large bank/replay**

Hindsight uses the OTLP **HTTP** exporter and batches with `BatchSpanProcessor`. For very high traffic, lower the recall trace volume by setting your environment to `dev`/`staging` and only enabling production tracing for the org's primary banks.
