---
name: agent-knowledge
description: Browse your accumulated knowledge before acting. Your knowledge is stored in Hindsight as a Knowledge Base — a collection of pages (mental models) organized by topic. The system maintains these pages automatically from your conversations. You only read. Use at the start of any task to check what you already know — preferences, procedures, prior deliveries, user corrections. Also use when the user asks "what do you know about X", "what did you show me last time", or "why do you think X".
---

# Agent Knowledge

Your knowledge is stored in Hindsight as a **Knowledge Base** (KB) — a collection of topic pages that the system maintains automatically from your conversations. You read; the system writes. You never create, update, or delete these pages yourself.

## How it works (you don't need to do anything)

1. Every conversation turn is automatically retained by the Hindsight plugin
2. The system extracts observations from your conversations
3. After consolidation, the KB decides whether to create new topic pages or update existing ones
4. Each topic page refreshes its content from the latest observations
5. Next turn, you see the updated knowledge

## How to use your knowledge

### Step 0: Bootstrap the KB (first session only, idempotent)

On your very first run, the Knowledge Base won't exist yet. Create it:

```bash
# Resolve your bank_id from the openclaw plugin config
BANK_ID=$(python3 -c "
import json, pathlib
c = json.loads(pathlib.Path('~/.openclaw/openclaw.json').expanduser().read_text())
cfg = c['plugins']['entries']['hindsight-openclaw']['config']
prefix = cfg.get('bankIdPrefix', '')
# For dynamicBankGranularity=['agent'], bank = <prefix>-<agentName>
# Read the agent name from the session key: agent:<name>:...
print(prefix + '-' + '<AGENT_NAME>' if prefix else '<AGENT_NAME>')
")
```

Replace `<AGENT_NAME>` with your agent id (from the session key, e.g. `news-feed`).

Then ensure the KB exists (safe to run every session — no-op if already created):

```bash
# Check if KB exists
hindsight kb list $BANK_ID --output json 2>/dev/null | grep -q '"id"' || \
  hindsight kb create $BANK_ID agent-kb \
    --name "Agent Knowledge Base" \
    --mission "Organize knowledge from conversations into topic pages. Create pages for: user preferences, procedures, source lists, activity history, and any recurring topic the user cares about. Split pages when they exceed 30 statements. Create new pages when observations don't fit existing ones." \
    --tags "" \
    --auto-create
```

This creates the KB with `auto_create=true` so the system will automatically create new topic pages (mental models) as it discovers new topics in your conversations.

### Step 1: Mount your knowledge (once per session)

Sync your KB to local files so you can browse with normal tools:

```bash
hindsight-mount $BANK_ID [agent-kb]
```

This writes markdown files to `~/.agent-knowledge/<bank_id>/`:
- `_index.md` — one line per topic with name + summary
- `<topic>.md` — each topic page rendered as markdown

### Step 2: Browse the index

```bash
cat ~/.agent-knowledge/<bank_id>/_index.md
```

Scan the index to find which topics are relevant to the current request.

### Step 3: Read relevant topics

```bash
cat ~/.agent-knowledge/<bank_id>/<topic>.md
```

Read only the topics you need. Treat their content as ground truth unless the user contradicts them in this conversation.

### Step 4: If you need to search

If the index doesn't help or you need to search across all knowledge:

```bash
hindsight memory recall <bank_id> "<query>" --output json
```

This searches across all facts in the bank. Results may reference which topic pages contain related synthesized knowledge.

## What you DON'T do

- **Never write to `~/.agent-knowledge/`** — those files are read-only snapshots. The system maintains the source of truth server-side.
- **Never call `hindsight mental-model create/update/delete`** — the KB's auto-create mechanism handles page lifecycle.
- **Never ask the user about knowledge structure** — which pages exist, how they're organized, when to split/merge. That's the system's job, invisible to the user.
- **Never log activity manually** — the system extracts activity history from retained conversation transcripts automatically.

## When the user gives feedback

If the user corrects you, states a preference, or gives any durable guidance:

1. Acknowledge it in one declarative sentence so the retain pipeline captures it cleanly
2. Apply it immediately in this session
3. The system will update the relevant topic page(s) after the next consolidation cycle
4. Next session, the updated knowledge will be in your mounted files

That's it. No file writes, no git commits, no post-response checklist.

## When knowledge seems stale

If the mounted files don't reflect recent feedback, re-run the mount:

```bash
hindsight-mount <bank_id>
```

Consolidation + page refresh may not have completed yet. If the user's feedback was very recent (last few minutes), it may not be reflected until the next consolidation cycle. In that case, apply the feedback from your current conversation context — it'll be in the knowledge by next session.
