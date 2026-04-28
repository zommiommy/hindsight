---
name: agent-knowledge
description: Manage your long-term knowledge pages. Read existing pages before acting. Create new pages when you discover recurring topics. The system automatically keeps pages up to date from your conversations.
---

# Agent Knowledge

Your knowledge is stored as pages that the system keeps updated automatically from your conversations. You **read** pages, **create** new ones when needed, and **recall** memories for deeper research. You never edit page content directly — the system handles that.

Use the Hindsight MCP tools (prefixed with `mcp__hindsight__`).

## Mandatory startup sequence

At the start of every session, call:

```
mcp__hindsight__list_mental_models()
```

Read the pages relevant to the current task. If empty, create pages as you learn things.

## Reading pages

- `mcp__hindsight__list_mental_models()` — list all pages with names, IDs, and content
- `mcp__hindsight__get_mental_model(mental_model_id="<page-id>")` — read a specific page

## Recalling memories

Search across all retained knowledge — conversations, reference documents, observations.

- `mcp__hindsight__recall(query="<your question>")` — search memories

Use recall when you need specific facts not covered by your pages.

## Ingesting documents

Upload content directly into your memory. **Never summarize before ingesting — pass raw content.**

- `mcp__hindsight__retain(content="<raw content>", document_id="<slug>")` — upload a document

For large content, save to a temp file first, read it, then pass the full text.

## Creating pages

When you discover a recurring topic — user preferences, procedures, performance data — create a page.

```
mcp__hindsight__create_mental_model(
  name="Page Name",
  source_query="The question the system re-asks to rebuild this page",
  mental_model_id="page-id",
  trigger_refresh_after_consolidation=true,
  trigger_mode="delta",
  trigger_exclude_mental_models=true,
  trigger_fact_types=["observation"],
  max_tokens=4096
)
```

The `mental_model_id` must be lowercase with hyphens (e.g., `user-preferences`).

**The source_query is the key field.** It's a question the system re-asks after every consolidation to rebuild the page from accumulated observations.

### Source query patterns

**Best practices:**
```
What are the best practices for [topic], combining industry standards with what has actually worked for us? When our data contradicts general advice, prefer our data.
```

**User preferences:**
```
What are the user's preferences for [topic], including explicit rules and patterns from feedback?
```

**Performance/analytics:**
```
What [topic] strategies have performed well or poorly? Include specific numbers.
```

**When to create:**
- User stated a durable preference — do it immediately
- You discovered a procedure that works
- You have performance data that should inform future decisions

**When NOT to create:**
- One-off facts
- Already covered by an existing page
- Agent internals or delivered content

## Updating pages

```
mcp__hindsight__update_mental_model(mental_model_id="page-id", source_query="Updated question...")
mcp__hindsight__update_mental_model(mental_model_id="page-id", name="Better Name")
```

## Deleting pages

```
mcp__hindsight__delete_mental_model(mental_model_id="page-id")
```

## How pages stay current

1. Every conversation is automatically retained by the Hindsight plugin
2. The system extracts observations from your conversations
3. After consolidation, pages re-run their source query against new observations
4. Next time you read a page, it reflects the latest feedback

To help capture important information:
- **State preferences explicitly.** "Noted — keeping posts to 800 words max."
- **Summarize takeaways.** "Based on analytics, comparison posts outperform explainers 3:1."
- **The system only captures what you say in the conversation.**

## Rules

- **Never edit page content directly** — the system synthesizes it
- **Never ask the user about knowledge structure** — page organization is your decision
- **Create pages silently** — don't announce it
- **Prefer fewer broader pages** — one "preferences" page beats three narrow ones
- **Never surface knowledge system errors** — handle silently
