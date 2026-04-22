# Asynchronous Knowledge Synthesis for Self-Learning LLM Agents

**Draft — April 2026**

## Abstract

We present an architecture for self-learning LLM agents that separates knowledge capture from knowledge synthesis, addressing the fundamental unreliability of LLM agents as writers of their own persistent state. Our approach uses an external memory system (Hindsight) to deterministically capture every agent conversation, asynchronously extract structured observations, and maintain evolving knowledge pages via a novel `source_query` abstraction. The agent reads its knowledge at session start and decides what topics to track, but never writes page content directly — the system handles synthesis in the background. We demonstrate that this separation achieves 100% capture reliability (vs ~70% with agent-driven writes), eliminates synchronous write overhead from the agent's critical path, and produces higher-quality knowledge pages because synthesis operates on accumulated observations rather than single-turn context. We compare against file-based self-maintaining memory, pipeline-driven auto-creation, and the Memento-Skills reflective learning approach, identifying the failure modes of each and the design constraints that led to our architecture.

## 1. Introduction

Long-running LLM agents — those that operate across multiple sessions serving the same user or domain — face a fundamental problem: they wake up stateless. Each session begins with no memory of prior interactions unless external mechanisms provide continuity. The emerging solution is agent memory systems that persist knowledge across sessions, but the question of *who maintains that knowledge* remains open.

Three approaches exist in the literature and practice:

1. **Agent-maintained files.** The agent reads and writes its own memory files (markdown, JSON, git-tracked). Used by Claude Code's auto-memory, OpenClaw's MEMORY.md pattern, and many custom agent frameworks. Simple, zero infrastructure, but depends on the agent reliably executing post-response write operations.

2. **Pipeline-maintained knowledge.** An external system ingests conversation transcripts and uses LLM calls to extract, organize, and synthesize knowledge. The agent is read-only. Examples include RAG systems with periodic re-indexing, and Karpathy's LLM Wiki pattern [1] where an LLM maintains a structured wiki from raw document sources.

3. **Hybrid: agent-directed, system-maintained.** The agent decides *what* to track (creates knowledge pages with queries), but the system handles *capture* (deterministic hooks) and *synthesis* (asynchronous background processing). This is our approach.

We argue that approach (3) is necessary because (1) fails on write reliability and (2) fails on content curation. We present empirical evidence from building and testing all three approaches with real agents on the OpenClaw platform, backed by the Hindsight memory system.

## 2. Background and Related Work

### 2.1 The Unreliable Writer Problem

LLM agents are stateless function calls. When asked to both produce a visible response AND perform invisible bookkeeping (update memory files, append logs, commit changes), the bookkeeping competes with the primary task for the model's "attention budget." In our experiments (Section 4.1), agents dropped post-response memory writes approximately 30% of the time — they understood the rules, agreed to follow them, and then didn't execute the final steps.

This is not a prompting problem. We tested mandatory checklists (`📝 Memory: [wrote: X | logged: Y | committed: Z]`), which improved reliability but never eliminated the failure. The LLM's natural stopping point is after the visible response — everything after that is a bonus the model may or may not execute.

### 2.2 Karpathy's LLM Wiki

Andrej Karpathy proposed a pattern for LLM-maintained knowledge bases [1]: raw document sources are ingested, an LLM maintains a structured wiki, and three operations keep it current — **ingest** (add new sources), **query** (retrieve relevant sections), and **lint** (check consistency and freshness). The LLM does all the writing; the wiki evolves as sources change.

This maps cleanly to agent memory: conversation transcripts are the sources, knowledge pages are the wiki, and consolidation is the maintenance loop. However, Karpathy's model assumes curated document inputs where the LLM can identify topic boundaries. Agent conversation transcripts are 80%+ noise — tool calls, formatting, agent self-talk, delivered content — and a pipeline LLM cannot reliably distinguish signal from noise in this context (Section 4.3).

### 2.3 Memento-Skills

Memento-Skills [2] proposes "Let Agents Design Agents" — a read-write reflective learning framework where agents maintain skill files as persistent memory. The agent rewrites skill files directly after each session, with a judge LLM + unit tests + rollback mechanism to prevent regressions. Key contributions: behavior-aligned routing (matching tasks to relevant skills), convergence guarantees (skills stabilize over iterations), and the insight that skills themselves are the right unit of persistent memory.

Our approach shares the premise (skills as memory, reflective learning) but differs in a critical design choice: Memento-Skills lets the agent write content directly (with safeguards), while we separate content creation from content maintenance. Their approach requires heavier infrastructure (judge, test gate, rollback) to compensate for the unreliability we avoid by design. The trade-off: they get immediate updates within a session; we accept consolidation latency in exchange for guaranteed capture and background synthesis.

### 2.4 Other Agent Memory Systems

**MemGPT** [3] virtualizes the context window with an explicit memory management system, giving the agent control over what enters and exits working memory. Relevant but orthogonal — it addresses within-session memory management, not cross-session knowledge persistence.

**Reflexion** [4] introduces self-reflection where agents generate verbal feedback on their own outputs and use it in subsequent attempts. The reflection is immediate and task-specific, not persisted across sessions. Our observation extraction is similar in spirit but operates asynchronously and accumulates across all sessions.

**Voyager** [5] builds a skill library in Minecraft where the agent writes executable code snippets as reusable skills. The skill library persists and grows. Similar to our page creation — the agent decides what's worth persisting — but Voyager skills are executable programs, not synthesized knowledge, and there's no background refinement.

## 3. Architecture

### 3.1 Overview

Our system consists of four components:

1. **Capture layer** — A deterministic plugin hook that fires on every agent conversation end, retaining the user/assistant message history into a memory bank. The agent is not involved; capture is infrastructure.

2. **Consolidation pipeline** — An asynchronous background process that extracts structured observations from retained conversations. Runs periodically, not on the critical path of any agent response.

3. **Knowledge pages (mental models)** — Persistent, evolving documents that synthesize observations into actionable knowledge. Each page is defined by a `source_query` — a natural language question that the system re-answers after every consolidation cycle using the latest observations.

4. **Agent skill** — A read-heavy interface that the agent uses at session startup to read its knowledge pages, and occasionally to create new pages, update their scope, or query raw memories for ad-hoc research.

### 3.2 The source_query Abstraction

The key design innovation is the `source_query`. When the agent creates a knowledge page, it provides:

- A **name** (human-readable label)
- A **source_query** (a question the system will re-ask on every consolidation)

For example:
```
name: "Editorial Preferences"
source_query: "What are the user's editorial preferences for blog content,
including tone, voice, length, formatting rules, and any explicit corrections
they've stated? Include patterns from feedback."
```

The system uses this query to run a reflect operation against all accumulated observations, producing synthesized content. After each consolidation cycle — when new observations have been extracted from recent conversations — the page automatically refreshes by re-running its source_query against the updated observation set.

This abstraction has several properties:

- **Declarative, not imperative.** The agent specifies *what* it wants to know, not *how* to maintain the knowledge.
- **Idempotent.** Re-running the query produces a complete, self-contained page — not a diff or append.
- **Steerable.** The query's phrasing controls how the synthesis resolves conflicts (e.g., "when our data contradicts industry advice, prefer our data and note the deviation").
- **Evolvable.** The agent can update the source_query if the page's scope needs to change.

### 3.3 Data Flow

```
Session 1: User says "keep posts to 800 words max"
    → auto-retain captures conversation (deterministic)
    → consolidation extracts observation: "user wants 800 word max for posts"
    → "Editorial Preferences" page refreshes via source_query
    → page now includes "800 word max" alongside other preferences

Session 2: Agent reads "Editorial Preferences" page at startup
    → writes an 800-word post without being told
```

The agent never edited the page. It acknowledged the preference in conversation (so retain captures it), and the system did the rest.

### 3.4 Delta Mode

Pages can operate in **full** or **delta** mode:

- **Full mode**: On each refresh, re-synthesize the entire page from all observations. Produces the most coherent result but scales poorly with observation count.
- **Delta mode**: On each refresh, only process observations since the last refresh and merge them into the existing page content. More efficient, preserves existing structure, but requires the synthesis to handle merging.

In practice, delta mode is preferred for production use — it limits the LLM call size to new observations only, and the accumulated page content provides continuity.

### 3.5 What the Agent Controls vs. What the System Controls

| Responsibility | Agent | System |
|---|---|---|
| Capture conversations | Nothing | Deterministic plugin hook, 100% reliable |
| Create knowledge pages | Decides what topics need a page, writes the source_query | Stores the page, runs initial synthesis |
| Update page content | Nothing — just responds naturally to user feedback | Consolidation + refresh handles it |
| Update page scope | Can modify the source_query if the page needs refocusing | Re-synthesizes on next cycle |
| Delete pages | Can delete redundant pages | Removes them |
| Read knowledge | Reads pages at session startup | Returns current content |
| Ad-hoc research | Runs recall queries | Semantic search across all observations |

## 4. Experiments and Findings

### 4.1 Agent-Maintained File Memory (Approach 1)

We built an `agent-memory` skill where the agent maintains its own wiki of markdown files — one per topic, with evidence sections, git-tracked, and indexed. The agent reads before acting and writes after responding.

**Setup:** The skill defined a mandatory post-response checklist: update knowledge files, append to activity log, git commit. A completion marker (`📝 Memory: [wrote: X | logged: Y | committed: Z]`) was required at the end of every response.

**Results:**
- Read reliability: ~100%. Agents consistently read memory files when instructed.
- Write reliability: ~70%. Post-response writes were dropped in approximately 30% of sessions.
- The checklist improved reliability from ~50% to ~70% but never eliminated the problem.
- When writes succeeded, the quality was good — the agent understood what to persist and how to organize it.

**Failure analysis:** The LLM's generation terminates when it produces a natural response endpoint (answer delivered, task completed). Post-response bookkeeping requires the model to continue generating after this natural stopping point. This is architecturally similar to the "last-mile" problem in multi-step reasoning — the model handles the main task well but drops auxiliary steps.

### 4.2 Pipeline-Maintained Knowledge (Approach 2)

We built a `knowledge_base_update` pipeline that runs after consolidation: it reads the bank's mission, recent observations, and existing pages, then asks an LLM whether new pages should be created or existing ones reorganized.

**Results:**
- The pipeline reliably created pages — no write reliability issues (it's server-side code, not an agent).
- However, page quality was poor. The LLM consistently created pages for irrelevant topics:
  - "Open Source AI Models" (from news content the agent delivered)
  - "Agent Identity" (from session setup chatter)
  - "Tool Usage Patterns" (from tool call metadata)
  
**Mitigations attempted:**
1. Strict prompt rules ("NEVER create pages for delivered content") — LLM ignores them
2. Code-level observation filters (pattern matching) — fragile, wrong approach
3. Requiring 3+ observations per topic — still creates junk from clustered noise

**Failure analysis:** Observations extracted from conversation transcripts are decontextualized. A statement like "GPT-5.4 is now available" might be a news item the agent delivered or a user preference about which model to use — the pipeline LLM cannot tell the difference. The agent can, because it has the full conversation context and understands what matters to the user.

This is where Karpathy's LLM Wiki pattern breaks for agent memory: his model assumes curated document inputs, while our inputs are noisy conversation transcripts.

### 4.3 Hybrid: Agent-Directed, System-Maintained (Approach 3)

Our final architecture: the agent creates pages (it has context to judge what matters), the system refreshes them (it has reliability).

**Results:**
- Capture reliability: 100% (deterministic hook, no agent involvement)
- Page creation quality: high (agent only creates pages for topics it recognizes as recurring)
- Cross-session knowledge transfer: confirmed. Preferences stated in session N appeared in synthesized pages read by session N+1.
- Synthesis latency: 30-60 seconds (consolidation cycle). Acceptable for cross-session use; within a session, the agent applies feedback from direct conversation context.

**Key insight confirmed:** Separating the decision of *what to track* (agent) from the *mechanics of tracking* (system) produces the best outcome. Neither the agent alone (unreliable writes) nor the pipeline alone (junk pages) achieves both reliability and quality.

## 5. Discussion

### 5.1 The Async Latency Trade-off

The primary cost of our approach is latency: knowledge pages are not updated in real-time. After a user states a preference, the system requires a consolidation cycle (observation extraction) followed by a page refresh before the knowledge is available to future sessions.

Within the current session, this is not a problem — the agent has the conversation context and can apply the preference immediately. The latency only affects cross-session transfer. In practice, with consolidation running every few minutes, this delay is acceptable for the use cases we target (durable preferences, procedures, performance data).

### 5.2 The source_query as a Controllable Lens

The source_query is more than a retrieval query — it's a controllable lens that determines how raw observations are synthesized into knowledge. Different phrasings produce different pages from the same observations:

- "What are the best practices?" → produces a rule list
- "What has performed well vs poorly?" → produces a comparative analysis
- "What are the best practices, preferring our data over industry advice?" → produces personalized rules with deviation notes

This gives the agent (and by extension, the template author) fine-grained control over the knowledge representation without touching the synthesis machinery.

### 5.3 Template-Driven Agent Onboarding

Because knowledge pages are defined by source_queries, an entire agent's knowledge structure can be pre-configured via a declarative template:

```json
{
  "mental_models": [
    {"id": "best-practices", "source_query": "What are the best practices for...?"},
    {"id": "performance", "source_query": "What strategies have worked...?"},
    {"id": "preferences", "source_query": "What does the user prefer...?"}
  ]
}
```

Combined with reference document ingestion at setup time, an agent can begin its first session with pre-populated knowledge pages — synthesized from reference material, ready to evolve with user feedback. The template is the declarative specification; the system handles the imperative work.

### 5.4 Comparison with Memento-Skills

| Dimension | Memento-Skills | Our Approach |
|---|---|---|
| Who writes content | Agent (with judge + rollback) | System (consolidation + reflect) |
| Update timing | Synchronous (same turn) | Asynchronous (consolidation cycle) |
| Quality control | Judge LLM + unit tests | source_query steering + observation filtering |
| Capture reliability | Agent must write | Deterministic hook, 100% |
| Infrastructure | Judge, test gate, rollback | Memory system + worker |
| Convergence | Proven via judge feedback loop | Proven via accumulated observations |

Both approaches converge on the same insight: the agent needs persistent, evolving knowledge outside its context window. The key difference is where the write responsibility sits. Memento-Skills invests in making the agent a reliable writer (via safeguards); we avoid the problem entirely by making the agent read-only on content.

## 6. Limitations and Future Work

1. **Consolidation latency.** The async cycle means knowledge pages are always slightly stale. For time-sensitive decisions, the agent must rely on direct conversation context rather than pages.

2. **Observation quality.** The pipeline LLM that extracts observations from conversations can miss nuance or extract irrelevant facts. Improving observation extraction directly improves page quality.

3. **Scale.** With N pages, each consolidation triggers N reflect calls. Delta mode mitigates this (only processing new observations) but the cost grows linearly. Batching or selective refresh (only refresh pages whose tag scope matches new observations) would help.

4. **Provenance.** Currently, pages are synthesized text with no per-statement attribution. Adding citations to source observations would enable the agent to trace *why* a knowledge page says what it says.

5. **Cross-agent knowledge sharing.** User-level preferences (timezone, communication style) apply across all agents but currently live in per-agent banks. A shared knowledge layer would avoid duplication.

## 7. Conclusion

We demonstrate that self-learning LLM agents require a separation of concerns between knowledge capture, knowledge curation, and knowledge synthesis. The agent is an excellent reader and a capable curator (deciding what to track) but an unreliable writer (executing post-response persistence). By delegating capture to deterministic infrastructure and synthesis to asynchronous background processing, we achieve 100% capture reliability and high-quality knowledge pages without burdening the agent's critical path.

The `source_query` abstraction — a declarative question that the system re-answers on every consolidation cycle — provides a clean interface between agent intent and system execution. The agent controls *what* gets synthesized; the system handles *when*, *how*, and *from what*.

This architecture is implemented and deployed on the OpenClaw agent platform with the Hindsight memory system. It is in active use with marketing, news feed, and development agents, demonstrating practical viability across diverse agent types and use cases.

## References

[1] Karpathy, A. "How I use LLMs." Blog post, karpathy.ai, April 2025. Describes the LLM Wiki pattern: raw sources → LLM-maintained wiki with three operations (ingest, query, lint).

[2] Jiang, Y. et al. "Memento: Empowering LLM Agents to Iteratively Self-Evolve via Read-Write Reflective Learning." arXiv:2503.18743, March 2025.

[3] Packer, C., Wooders, S., Lin, K., Fang, V., Patil, S.G., Stoica, I., Gonzalez, J.E. "MemGPT: Towards LLMs as Operating Systems." arXiv:2310.08560, 2023.

[4] Shinn, N., Cassano, F., Gopinath, A., Narasimhan, K., Yao, S. "Reflexion: Language Agents with Verbal Reinforcement Learning." NeurIPS 2023. arXiv:2303.11366.

[5] Wang, G., Xie, Y., Jiang, Y., Mandlekar, A., Xiao, C., Zhu, Y., Fan, L., Anandkumar, A. "Voyager: An Open-Ended Embodied Agent with Large Language Models." arXiv:2305.16291, 2023.

[6] Sumers, T.R. et al. "Cognitive Architectures for Language Agents (CoALA)." arXiv:2309.02427, 2023. Taxonomy of agent memory modules (procedural, semantic, episodic); identifies write reliability as a core open challenge.

[7] Zhou, A. et al. "Language Agent Tree Search Unifies Reasoning Acting and Planning in Language Models." arXiv:2310.04406, 2023.
