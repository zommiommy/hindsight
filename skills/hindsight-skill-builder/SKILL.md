---
name: hindsight-skill-builder
description: Create a new self-improving skill for this agent whenever the user asks for a capability the agent doesn't yet have. Use when the user says "can you also do X", "I want a weekly brief", "remember how I like X", "start tracking Y for me", "build me a Z", or otherwise implies a recurring task the agent should formalize. Produces a thin loader SKILL.md plus a Hindsight mental model that will capture and evolve the user's taste for that task over time.
---

# Hindsight Skill Builder

You are the agent's tool for **growing its own capabilities**. Every time the user asks for a recurring task you don't already have a skill for, use this meta-skill to build one. Once built, the harness reloads it and the agent can handle that class of request going forward — and it gets sharper over time as the user gives feedback.

## ⚠️ The one rule you cannot break

**Once a skill is created, you must never edit its SKILL.md in response to user feedback about what the task should do.** Not for "prefer RSS", not for "include X", not for "drop Y source", not for "use bullet format". All of that is playbook content — it belongs in the mental model, not in the SKILL.md file.

When the user gives you feedback after a skill has been built:
1. Acknowledge it in one declarative sentence so the retain pipeline captures it cleanly.
2. Do NOT open the SKILL.md. Do NOT use Edit / Write / apply_patch on it.
3. The next consolidation + MM refresh will fold that feedback into the playbook automatically.

The SKILL.md changes exactly twice in its life: when you create it, and if a tool allowlist or hard invariant actually needs to change. Everything else is MM territory. If you find yourself reaching for Edit on an existing SKILL.md, stop and retain the feedback as a user statement instead.

## The discipline: thin SKILL.md + rich mental model

Every skill you build has exactly two artifacts:

1. **SKILL.md** (static, tiny — 20–40 lines) — the harness trigger binding. Only three things belong here: *when* the skill activates (trigger phrasings in the description), *which tools* it may use (allowlist + hard guardrails), and the single procedural instruction: "read the mental model; follow it literally; do not contradict it".
2. **Mental model** (dynamic, in Hindsight — can be long) — the **entire playbook** for this task. Everything the agent needs to remember about doing this task well for this user: what the task is, sensible defaults, structure, format, voice, specific rules, exclusions, anything. Evolves as the user gives feedback. Refreshes after each consolidation via `refresh_after_consolidation`.

**Everything the agent has to remember for the task lives in the MM, not the SKILL.md.** The SKILL.md is the tiniest possible shell that says "there's a playbook in Hindsight — go read it". If you catch yourself writing task-specific content into the SKILL.md — defaults, format notes, example output, anything that might plausibly evolve — stop and move it to the MM.

**What belongs where:**

| SKILL.md (tiny, stable) | MM (the whole playbook) |
|---|---|
| Trigger phrasings in the `description` frontmatter | What the task is (definition, purpose) |
| Tool allowlist ("may use web_search, web_fetch, …") | Structure + sections + format |
| Hard invariants ("never post without approval") | Sensible defaults when the user hasn't specified |
| The 4-step loader procedure | Specific rules from user feedback |
| Out-of-scope list (what to defer to other skills) | Voice, tone, stylistic quirks |
|  | Sources / channels / people to focus on or avoid |
|  | Concrete examples if they sharpen the output |

Why the MM holds it all: because *anything* in the playbook could evolve from user feedback, and the MM is the only artifact that updates without a harness reload. Stuff you put in SKILL.md is locked in until the agent edits and reloads it — that's the right place for triggers and guardrails, the wrong place for anything the user might tune.

## Human-in-the-loop protocol (MANDATORY)

Every decision point below requires explicit user approval before you execute. You propose → user approves or edits → only then you run. Never chain decisions.

Approval gates:
1. **Skill spec**: name, trigger phrasing, one-line description, procedure sketch
2. **MM spec**: id, name, source_query (the *most important* field — it's the question the MM answers every consolidation cycle)
3. **Final SKILL.md content** (before writing)
4. **Reload plan** (session restart is often required — the agent tells the user how, doesn't do it silently)

---

## Step 1 — Resolve the bank

Every agent already has a bank provisioned by the installer (retain / observations / reflect missions are already tuned for this agent). You don't create a bank; you bind the new MM to the existing one.

The openclaw-hindsight plugin writes its effective config into openclaw's config file. Read it:

```bash
python3 -c "import json, pathlib; c = json.loads(pathlib.Path('~/.openclaw/openclaw.json').expanduser().read_text()); cfg = c['plugins']['entries']['hindsight-openclaw']['config']; print(cfg.get('hindsightApiUrl'), '|', cfg.get('bankIdPrefix',''), '|', cfg.get('dynamicBankGranularity') or cfg.get('bankId'))"
```

The agent's bank id follows the plugin routing. For `dynamicBankGranularity=['agent']` (the installer default), it's `<bankIdPrefix>-<thisAgentName>`. Confirm the resolved bank id with a health check:

```bash
hindsight bank stats <bank_id> --output json | head
```

Make sure the CLI points at the same `hindsightApiUrl` the plugin uses — `hindsight configure --api-url <url>` if it doesn't. If `hindsightApiToken` is set on the plugin as a plain value, pass `--api-key` too.

> Tell the user: "This skill will bind to bank `<bank_id>` on `<hindsightApiUrl>`." Wait for approval.

---

## Step 2 — Propose the skill spec

Pick a name (lowercase-with-hyphens, specific to the task). Write a one-line description that names the trigger phrasings. Sketch the procedure in 3–6 lines. Propose the MM id + source_query separately.

Example proposal template:

> **Skill: `<name>`**
> **Description:** *"<description incl. trigger phrasings>"*
> **Procedure:**
>   1. `hindsight mental-model get <bank> <mm_id> --output json` → read `content` as rubric
>   2. If content is empty, stop and ask the user for initial direction
>   3. Fetch / produce / filter per rubric using <tools>
>   4. Render per rubric format; never cache state locally
>
> **Mental model**
>   - id: `<mm_id>`
>   - name: `<MM display name>`
>   - source_query: *"<question that will synthesize the user's accumulated advice about this task into an actionable rubric for the skill to follow>"*

Wait for approval. Iterate on the source_query especially — that's what determines whether the MM content is useful.

### Good source_query shape

The source_query must produce **the complete playbook** the skill follows — not "user preferences", not a bullet dump. The MM's output IS the skill's entire behavioral instruction set for this task.

**Use the universal playbook template below for every skill you build**, customized only in the leading paragraph that names the task and the user. The section headers stay identical across skills so the loader skill can rely on the shape.

Universal template (copy + fill the `<angle-bracket>` parts for the specific task):

```
You are the complete playbook a <ROLE> follows to do <TASK> for the user.

Read everything retained in this bank about how the user wants <TASK>
done, extract durable rules from their advice / corrections / reactions,
and produce a self-sufficient playbook organized into the sections
below. Where the user has given explicit guidance, follow it exactly.
Where advice is partial, extrapolate intent to adjacent cases. Where
a section has no durable user input yet, provide a sensible generic
default and mark it as "(default — no user guidance yet)". Omit a
section entirely only when it genuinely doesn't apply to this task.

When two pieces of advice conflict, the newer wins; mark the older as
stale.

Output sections, in this exact order:

## Purpose
One sentence: what this skill does, for whom, under what trigger.

## Scope
- In scope: what this skill handles
- Out of scope: what belongs to sibling skills or to the user directly

## Rules
- Always: hard constraints the user has stated (must-haves, must-nots)
- Prefer: softer defaults (style, ordering, priorities)

## Procedure
Numbered steps at the level of guidance, not code. Reference the
Inputs and Output sections by name rather than restating their
content.

## Inputs and context
Where material comes from: sources, channels, time windows, people,
external context this skill depends on.

## Output shape
- Structure
- Format
- Length / cap
- Voice / tone

## Stop conditions
When to refuse or ask a clarifying question instead of guessing.

## Open questions
Things the user hasn't told me yet that would sharpen the playbook
next time they interact.
```

Why a universal template:
- Loader skills can rely on a stable structure (Rules before Procedure before Output, always).
- Cross-skill transfer — a user's "always cite sources" rule looks the same in a research skill and a blog skill.
- Less cognitive load for the user — they learn one playbook shape, not one per task.
- Empty-task bootstrap works: the template's defaults kick in on day one; user advice enriches them over time.

Only tweak the leading paragraph (role / task / user) per skill. Do NOT invent skill-specific section names (like "TAKE", "DROP", "CAP" — those are news-feed jargon leaking into the MM). Keep the headers.

---

## Step 3 — Create the mental model

After approval:

```bash
hindsight mental-model create <bank_id> "<name>" "<source_query>" \
  --id <mm_id> \
  --trigger-refresh-after-consolidation
```

If the MM already exists, use `update` instead:

```bash
hindsight mental-model update <bank_id> <mm_id> \
  --name "<name>" \
  --source-query "<source_query>" \
  --trigger-refresh-after-consolidation true
```

Verify:

```bash
hindsight mental-model get <bank_id> <mm_id> --output json | head -20
```

Don't refresh it yet — it'll auto-refresh on the next consolidation after the user starts giving this skill feedback.

---

## Step 4 — Write the SKILL.md

Propose the final file content first. Use this template — keep it short. Extra prose belongs in the MM, not here.

```markdown
---
name: <skill-name>
description: <one-line what this does + the trigger phrasings that should fire this skill>
---

# <Skill Name>

This skill's entire playbook lives in the `<mm_id>` mental model in bank `<bank_id>`. Read it, follow it literally.

## Mental model spec (source of truth for this skill's MM)

- **Bank:** `<bank_id>`
- **MM id:** `<mm_id>`
- **MM name:** `<mm_display_name>`
- **Trigger:** `refresh_after_consolidation`

The full `source_query` that defines what this MM synthesizes lives in
step 0 below, as a heredoc. If you ever need to regenerate or inspect
it, that's the canonical copy.

## Procedure

0. **Ensure the MM exists** (idempotent — safe to run every turn; NO-OP when the MM is already there):

   ```bash
   SRC_QUERY=$(cat <<'EOF'
   <paste the exact source_query the meta-skill approved, verbatim, here>
   EOF
   )
   hindsight mental-model get <bank_id> <mm_id> --output json >/dev/null 2>&1 || \
     hindsight mental-model create <bank_id> "<mm_display_name>" "$SRC_QUERY" \
       --id <mm_id> \
       --trigger-refresh-after-consolidation
   ```

   If the MM was missing, this creates it with empty `content`. A subsequent consolidation cycle populates it from retained facts. On the very next turn the fetch in step 1 will still return empty `content` → follow step 2.

1. **Fetch the playbook:**
   ```bash
   hindsight mental-model get <bank_id> <mm_id> --output json
   ```
   The `content` field is the complete set of instructions for this task. Follow it as-is.

2. **If the MM returns empty / "no information" content**, surface that to the user and ask what to do — do not fall back to improvising. On a brand-new MM (just created in step 0) this is expected for the first turn; explain that and ask the user to seed with their initial preferences so retain + consolidation can populate the playbook.

3. **Do the task** using only these tools: <tool allowlist>. Respect all invariants the playbook states.

4. **Re-fetch on follow-up** — if the user asks for a refresh or correction, re-read the MM before responding; the playbook may have been updated by consolidation since the last turn.

## Hard invariants (never delegated to the MM)

<list any "never" rules that must hold regardless of what the MM says — e.g. "never post without user approval", "never call tool X". Keep this list small. Most rules belong in the MM.>

## Out of scope

<list other skills that handle adjacent requests so this one stays focused.>

## Learning loop

The plugin retains every turn. The bank's retain + observations missions extract guidance from the user's feedback. Consolidation merges it. `refresh_after_consolidation` rebuilds `<mm_id>`. Next run reads the updated playbook automatically — no local state.
```

### Why step 0 (idempotent MM create) matters

The MM lives server-side, the SKILL.md lives in the workspace. Those can drift:
- Someone resets the bank or deletes the MM by hand
- Workspace gets copied to a fresh machine with an empty Hindsight instance
- Consolidation never ran so the MM was created lazily but then purged

With step 0, the skill **self-heals** on its next invocation. The SKILL.md is the source of truth for the `source_query`; if the server lost the MM, the skill recreates it. The `get || create` pattern makes this a no-op when the MM is already present.

Important: step 0 does NOT update an existing MM's `source_query`. If the meta-skill needs to change the source_query (rare — it's the *spec* of the MM), that's an explicit operation via `hindsight mental-model update …`, not a silent side-effect of every turn.

Wait for approval, then write the file to:

```
~/.hindsight-agents/openclaw/<this-agent>/skills/<skill-name>/SKILL.md
```

(The workspace path the harness loads skills from. Confirm by reading `agents.list` via the openclaw RPC if unsure.)

---

## Step 5 — Reload the harness

OpenClaw loads skills at session start. A new skill won't take effect for the current session. Tell the user explicitly:

> I've installed `<skill-name>`. To pick it up, end this session and start a fresh one (close + reopen the chat tab, or `openclaw agent --agent <this> --session-id new-<timestamp>`). You don't need to restart the gateway unless you've changed plugin config.

Do NOT call `openclaw gateway restart` yourself — that's disruptive (kills all sessions) and not your decision. If the user wants a full restart, they'll ask.

---

## Counter-examples — things to refuse

- **Any task-specific content in SKILL.md** beyond triggers, tool allowlist, and hard invariants. Defaults, format notes, examples, voice guidance, source lists, step-by-step procedure — all of that goes in the MM. If a human looks at the SKILL.md and learns *how to do the task*, it's too fat.
- **SKILL.md longer than ~50 lines**. You've bled playbook content into the skill. Move it to the MM.
- **Procedures without an MM**. If nothing about the task would ever change from user feedback, this isn't a Hindsight skill; skip this meta-skill and write a plain skill directly.
- **Multiple MMs per skill**. One skill = one MM holding the whole playbook. If you're tempted to split, it's actually two skills.
- **Empty source_query / "summarize preferences"**. The source_query produces the full playbook the skill will follow; it must stand up on day one with no user facts. A vague query produces an empty MM and a skill that can't act.
- **Skipping the approval gates**. The user needs to see + shape each piece — skill name, trigger, source_query, final SKILL.md, reload plan.
