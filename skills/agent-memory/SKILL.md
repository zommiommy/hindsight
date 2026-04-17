---
name: agent-memory
description: Build and maintain your own procedural memory as files. Use whenever you learn something worth remembering across sessions — a user preference, a procedure that worked, a rule the user stated, a source to track, a decision and its rationale, or any knowledge you'd want available next time. Also use when the user says "remember this", "don't forget", "keep track of", or asks you to update something you previously noted. Also use after every completed task run (news feed, sweep, report) to log what you delivered.
---

# Agent Memory

You have a dedicated, version-controlled memory directory outside your workspace. It is yours — not shared with the harness, not inside any skill folder, not subject to workspace resets. Use it to build a growing wiki of everything you need to remember across sessions. Each file is one topic. You decide what's worth tracking.

## Where files live

```
~/.agent-memory/<agent-name>/
```

`<agent-name>` is your agent id (e.g. `news-feed`, `discord-watch`). If you don't know your agent name, check the session key or ask the user. Always use the absolute expanded path when reading/writing — never a relative path, since your working directory may vary.

Create the directory and initialize git on first use:

```bash
mkdir -p ~/.agent-memory/<agent-name>
cd ~/.agent-memory/<agent-name> && git init 2>/dev/null
```

## When to write

Two mandatory triggers. Both fire AFTER the user's response is delivered — never mid-task, never before the user sees the answer.

### Trigger 1: You learned something (knowledge files)

After any turn where you learned something durable — something useful in a future session. Write or update a knowledge file. Examples:

- User stated a preference ("I want short bullets, no fluff")
- You discovered a procedure that works ("to fetch RSS, use exec + curl, not web_fetch")
- User corrected you ("no, I said 10 items, not 5")
- A decision was made ("we agreed to use per-agent bank routing")
- You learned a fact about the user's setup ("user runs Hindsight locally on port 8888")
- User explicitly asked you to remember something

### Trigger 2: You completed a task run (activity logs)

**After every completed task run** — a news feed delivery, a Discord sweep, a report, a draft, anything the user consumed as output — **always** append a summary entry to the activity log. This is not optional. No exceptions. The entry records:

- Date
- What was requested (query style / trigger)
- Sources used and any retrieval failures
- What was delivered (headlines / item titles — not full content)
- Notable user feedback on the output (if any in this session)

This is how you deduplicate across runs and answer "what did you show me yesterday". If you skip this step, the next run will re-surface the same items.

### Do NOT write memory for:

- Raw step-by-step execution logs or tool call traces
- Ephemeral task state (use the conversation for that)
- Things already in the skill files or BRIEF.md
- Trivial acknowledgements ("got it", "ok")

### Write order (mandatory — your turn is NOT complete until step 4)

1. **Respond** to the user's request (the actual task output)
2. **Repair** any structural issues found during the read phase — missing `_index.md`, duplicate files, unnormalized names. Do this every time, not "later".
3. **Update** knowledge files and activity logs with what you learned / produced this turn
4. **Commit** to git and print the checklist (see below)

**Your turn is not finished until you print the memory checklist.** After every turn where memory applies, end with this exact block (silently, after the user's answer, as the final thing you output):

```
📝 Memory: [wrote: <files touched> | logged: <yes/no> | committed: <yes/no>]
```

Examples:
- `📝 Memory: [wrote: preferences.md | logged: yes (feed-log.md) | committed: yes]`
- `📝 Memory: [wrote: none | logged: yes (feed-log.md) | committed: yes]`
- `📝 Memory: [wrote: none | logged: no (no task output) | committed: no]`

If you completed a task run and the checklist says `logged: no`, you have a bug — go back and fix it before ending the turn. The checklist is a self-check, not decoration.

## Two kinds of memory files

### 1. Knowledge files — what you know

One file per topic. Tracks preferences, rules, procedures, setup facts, decisions.

```
~/.agent-memory/news-feed/preferences.md
~/.agent-memory/news-feed/rss-procedure.md
~/.agent-memory/news-feed/user-setup.md
~/.agent-memory/news-feed/source-list.md
```

These are **current-state** files — update in place when facts change. Keep them short and declarative.

### 2. Activity log — what you did

One file per recurring task type. Tracks what you produced and when, so you can deduplicate, reference prior output, and avoid repeating yourself.

```
~/.agent-memory/news-feed/feed-log.md
~/.agent-memory/discord-watch/sweep-log.md
```

These are **append-only** — add a new entry each time you complete a task run. Each entry is a short dated record of what you delivered: date, item count, the headlines or item titles (not full content), and any user reaction. Prune entries older than ~30 days to keep the file manageable.

When starting a new task run, read the log first. Skip items you already delivered in a recent run. If the user asks "what did you show me yesterday", the log is your answer.

Example:

```markdown
# Feed Log

## 2026-04-17

- 10 items delivered
- Headlines: "OpenAI ships GPT-5.5 API", "Hugging Face releases ...", ...
- User reaction: "good, but drop the Gemini item next time"

## 2026-04-16

- 8 items delivered
- Headlines: "Anthropic Claude 4.5 ...", "Google Gemini 2.5 ...", ...
- User reaction: none
```

## File naming

Lowercase with hyphens. Short, descriptive, greppable. Knowledge files are named by topic; activity logs are named by task + `-log` suffix.

If a topic file doesn't exist yet, create it. If it already exists, update it in place (for knowledge files) or append to it (for activity logs).

## File format (knowledge files)

Every knowledge file follows this structure:

```markdown
# <Topic Name>

<Current state of knowledge on this topic. Written as if briefing a
colleague who has never seen this conversation. Concise, declarative,
no hedging.>

## Evidence

- [<date>] <what happened that established or changed this knowledge>
- [<date>] <another event>
```

The `## Evidence` section is mandatory. Every fact in the file must trace to at least one evidence entry. When you update a fact, add a new evidence line explaining what changed and why. When a fact is superseded, don't delete the old evidence — mark it as superseded so the history is visible.

Example:

```markdown
# News Feed Preferences

- Format: short bullets, one sentence each
- Item cap: 10 per run
- Sources: prefer RSS/Atom feeds; use web search as fallback only
- Topics in: developer-focused AI, memory systems, RAG, multimodal
- Topics out: academic papers, hardware benchmarks, product fluff
- Window: last 7 days
- Voice: concise, dev-centric, no marketing speak
- Always include at least one OpenClaw item when meaningful

## Evidence

- [2026-04-15] User said "use defaults, short summaries, numbered, 5 items, last 24h" during initial setup
- [2026-04-15] User corrected to 10 items: "I want 10 items"
- [2026-04-15] User said "no product PR, more papers" — later clarified "actually no papers either, just dev product news"
- [2026-04-15] User requested RSS-first sourcing after web_search returned stale results
- [2026-04-15] User asked to always include OpenClaw releases when available
- ~~[2026-04-15] User said "last 24h"~~ superseded by:
- [2026-04-16] User changed window to 7 days
```

## How to use memory at the start of a turn

Every turn that might use or update memory follows this read sequence. Do it before starting the task.

### Step 1: Read the index (or bootstrap it)

```bash
cat ~/.agent-memory/<agent-name>/_index.md 2>/dev/null
```

If `_index.md` exists, scan it to decide which files are relevant to the current request. Read only those files — not everything.

If `_index.md` does NOT exist but memory files do, fall back:

```bash
ls ~/.agent-memory/<agent-name>/ 2>/dev/null
```

Read the files whose names look relevant. **Mark this as a repair-needed state** — you MUST create `_index.md` during the post-response memory update in this same turn. Do not end the turn without an index.

### Step 2: Read relevant files

Read the files the index (or fallback ls) pointed you to. Treat their content as ground truth unless the user contradicts them in this conversation (in which case, update the file after responding).

**If you find duplicate files covering the same topic** (e.g. `preferences.md` and `news-feed-preferences.md`), merge them into one canonical file during the post-response memory update. Pick the more specific name, combine the content, keep all evidence, delete the duplicate, and update the index. This is a hygiene error — fix it immediately, don't leave it for the self-review.

### Step 3: For task runs, also read the activity log

Before producing output (a feed, a sweep, a report), read the activity log for that task type. Use it to deduplicate against recent deliveries.

## Index file

Maintain `_index.md` in the memory directory. Update it every time you create, rename, or delete a memory file. Format:

```markdown
# Memory Index

- `preferences.md` — news feed preferences: format, sources, topics, cap, window
- `rss-procedure.md` — how to fetch RSS/Atom feeds reliably
- `user-setup.md` — user's local Hindsight + OpenClaw setup details
- `source-list.md` — allowed and blocked news sources
- `feed-log.md` — activity log: what was delivered each run (for dedup)
```

This lets you scan one small file instead of reading every memory file on every turn.

## Version control

The memory directory is a git repo. After every batch of writes in a turn, commit:

```bash
cd ~/.agent-memory/<agent-name> && git add -A && git commit -m "<short description of what changed>" 2>/dev/null
```

Use a descriptive commit message: "updated preferences: cap changed from 5 to 10" or "feed-log: added 2026-04-17 delivery". This gives full diff history, rollback capability, and answers "when did this change" without relying solely on the evidence section.

Don't push anywhere — this is a local repo. The user can inspect it with `git log` if they want history.

## Periodic self-review

Every ~10 sessions, or when the user explicitly asks you to review/clean up memory, do a consolidation pass:

1. Read ALL memory files (not just the ones relevant to the current task)
2. Check for:
   - **Contradictions** — two files stating conflicting facts. Resolve based on evidence dates (newer wins) and ask the user if ambiguous.
   - **Duplicates** — same knowledge in two files. Merge into one, delete the other, update the index.
   - **Overgrown files** — anything over ~50 lines. Split into sub-topics.
   - **Stale entries** — activity log entries older than 30 days. Prune them.
   - **Missing evidence** — facts without evidence entries. Either add the evidence if you remember the source, or flag them to the user as unverified.
3. Commit the cleanup as a single git commit: `"memory review: dedup, prune, resolve contradictions"`

You can also trigger this yourself if you notice inconsistencies during normal reads.

## Rules

1. **One file per topic.** Don't dump everything into one file. If two concerns are distinct (e.g. "user preferences" vs "known procedures"), they get separate files.
2. **Evidence is mandatory.** Never write a fact without an evidence entry explaining where it came from. If you can't cite evidence, you're guessing — ask the user instead.
3. **Update, don't append.** When a fact changes, rewrite the fact in place and add a new evidence entry. The file should always read as the *current* state of knowledge, not a log.
4. **Supersede, don't delete.** When old evidence is contradicted, mark it `~~superseded~~` in the evidence section. Don't remove it — the history matters (git has the full diff, but inline markers help at a glance).
5. **Respond first, write second.** Deliver the user's answer before touching any memory file. Memory updates are a visible post-script.
6. **Keep files short.** A memory file that exceeds ~50 lines is probably covering too many topics. Split it.
7. **Date every evidence entry.** Use `[YYYY-MM-DD]` format.
8. **Maintain the index.** Update `_index.md` whenever you create, rename, or delete a file.
9. **Commit after every write.** `git add -A && git commit -m "..."` after each batch of memory updates in a turn.
10. **Skip writes when nothing changed.** If a turn taught you nothing new and you didn't produce task output, don't write. Not every turn needs a memory update.
11. **Memory is your internal concern — never surface it to the user.** Don't ask the user whether to create a file, how to name it, whether to split or merge, or whether to track something. Decide yourself and do it silently. The user should never have to think about your file structure, your index, your git commits, or your organizational choices. If you think a `vercel-items.md` would help you answer future queries, just create it — don't propose it. The only time memory becomes visible to the user is when they explicitly ask ("what do you remember about X", "show me your memory files").
