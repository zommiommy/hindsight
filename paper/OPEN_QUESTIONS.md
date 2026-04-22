# Open Questions — Unresolved (Need Your Input)

These are the questions I couldn't address from our existing work. Each requires either running experiments, collecting data, or making a decision that only you can make.

---

## Empirical Claims Needing Data

### Q1: Formalized write-reliability measurement
The paper claims ~30% drop rate from ~40 manual observations. For a conference submission, we need a proper experiment: N=100+ sessions with controlled inputs ("remember that I prefer X"), automated check for whether the preference appears in memory files. Report with confidence intervals.

**What's needed:** Design the experiment, run it, report numbers.

### Q2: Write reliability by mechanism (tool calls vs file writes)
The paper acknowledges tool-based writes are likely more reliable, but argues the file-write pattern is the realistic baseline. A reviewer may push back: "if tool calls fix it, your motivation collapses." A controlled comparison (same agent, same sessions, three conditions) would settle this.

**What's needed:** Decide if we run this experiment or argue it's out of scope.

### Q3: Consolidation latency P50/P95/P99
The paper says "consolidation cycle dependent" but doesn't give numbers. We need instrumented measurements under various loads.

**What's needed:** Instrument the pipeline, run 100+ cycles, report distribution.

### Q4: "Page quality was poor" — formalized measurement
Currently based on manual inspection (70% junk rate). Need a rubric, 2+ raters, inter-rater agreement.

**What's needed:** Design rubric, rate pages, report.

---

## Missing Experiments

### Q5: End-to-end task quality comparison (HARD BLOCKER)
The most important missing evidence. A benchmark where an agent serves a user across N sessions, user states preferences, and we measure adherence in later sessions. Compare: no memory, file-based (Approach 1), pipeline (Approach 2), our approach (Approach 3).

**Proposal:** 10 user preferences stated across sessions 1-3, measure adherence score in sessions 4-10. Could use AMB or build a simpler preference-adherence benchmark.

**What's needed:** Design and run the benchmark. This is the #1 priority.

### Q6: Cross-session transfer experiment with numbers
User states preference in session 1, measure whether agent honors it in session N. Compare to no-memory baseline and Approach 1.

**What's needed:** This may overlap with Q5. Decide if it's part of the same experiment or separate.

### Q7: source_query phrasing stability ablation
Pick 3-5 queries, write 5 paraphrases each, run all, measure content overlap (ROUGE/BERTScore). Validates the "steerable" claim.

**What's needed:** Design and run. Medium priority — can be acknowledged as future work if we're short on time.

### Q8: Delta vs full mode empirical comparison
Quality degradation over long horizons, cost savings, drift measurement. Currently asserted.

**What's needed:** Run a page through 20+ consolidation cycles with incremental observations. Compare delta vs full on quality + cost.

### Q9: Observation extraction faithfulness
On a labeled set of conversations, measure precision/recall/fabrication of observation extraction.

**What's needed:** Label 20 conversations with ground-truth, run extraction, measure.

### Q10: Scaling behavior
As observations grow (100 → 10k → 100k), what happens to synthesis cost, quality, latency?

**What's needed:** Synthetic scaling test. Lower priority — can acknowledge as future work.

---

## Deployment Data

### Q11: End-to-end template example with real data
The paper's Section 5.3 has a sketch. For the submission, include actual page content before/after user feedback, with screenshots from the control plane.

**What's needed:** Run the marketing-seo demo end-to-end, capture actual page content at each stage.

### Q12: Deployment numbers
How many agents, sessions, pages, typical page size, observation counts. Grounds the work.

**What's needed:** Systematic logging. Or just report what we have (~5 agents, ~100 sessions, 3-5 pages/agent, 50-500 observations/bank).

---

## Priority for Conference Submission

**Hard blockers (must do):**
1. Q5 — end-to-end quality benchmark
2. Q6 — cross-session transfer with numbers

**Should do:**
3. Q1 — formalized write-reliability
4. Q9 — observation extraction faithfulness
5. Q11 — real template example with data

**Can acknowledge as future work:**
6. Q7 — phrasing stability
7. Q8 — delta vs full comparison
8. Q10 — scaling
9. Q2 — tool call vs file write comparison
10. Q3 — latency distribution
11. Q4 — formalized quality measurement
12. Q12 — deployment numbers
