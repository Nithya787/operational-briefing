# LLM-as-Judge Prompt: Olyns Operational Briefing Eval

**Project:** Workstream 1 — LLM Evals on the Briefing Tool
**Created:** 2026-08-18
**Status:** Active

---

## How to Use This

1. Replace `{PRIOR_SNAPSHOT_AVAILABLE}` with `yes` or `no` depending on whether the briefing was run with a prior snapshot loaded for comparison.
2. Replace `{BRIEFING_TEXT}` with the full text output of the briefing (copy from the downloaded .txt file or from the tool output).
3. Send the full prompt to Claude (claude-sonnet-4-6 or better).
4. Parse the output into your scoring table.

---

## The Judge Prompt

```
You are evaluating an Olyns Operational Briefing. Your job is to judge the quality of the briefing against a pass/fail rubric. You must be strict and specific. Do not give benefit of the doubt — if the criterion is not clearly met, mark it FAIL.

---

CONTEXT

Olyns operates a network of AI-powered recycling kiosks (called "Cubes") placed inside grocery stores. Consumers bring cans and bottles to deposit and receive CRV refunds. Gig workers called "Sherpas" are dispatched to service cubes when they fill up with crushed containers. The briefing is sent to two audiences:

- CEO: Cares about user growth, deposit volume trends, and whether the numbers support conversations with grocery store chains about expansion or contract renewal. He wants to see deposits and users going up, cubes staying available, and servicing getting faster over time.
- Ops team: Cares about which specific cubes need maintenance, Sherpa performance and coverage gaps, CSD (container sorting/deposit) bag overflow, and any patterns that need escalation to engineering.

---

PRIOR SNAPSHOT AVAILABLE: {PRIOR_SNAPSHOT_AVAILABLE}

---

BRIEFING TO EVALUATE:

{BRIEFING_TEXT}

---

EVALUATION RUBRIC

Evaluate the briefing on 4 checks. For each check, output exactly:
  Verdict: PASS or FAIL
  Critique: One to two sentences. Be specific — quote or reference the actual briefing text. Do not be vague.

---

CHECK 1A: CEO Growth Narrative

The CEO needs to see the headline business metrics and whether the business is growing.

If prior snapshot is available:
  PASS requires: Total deposits and unique users are stated AND compared to the prior period with a directional signal (e.g., "up 12% from last month" or "down from 340K last period"). At least one location-level growth insight should be present (e.g., which sites are driving volume growth).
  FAIL if: Only absolute numbers are given with no comparison to prior period, even though a snapshot exists to compare against.

If no prior snapshot is available:
  PASS requires: Total deposits and unique users are clearly and prominently stated, along with enough location-level context that the CEO understands where volume is concentrated.
  FAIL if: These headline numbers are missing, buried in a table, or not synthesized into a narrative.

Verdict:
Critique:

---

CHECK 1B: Ops Specificity

Every ops-relevant section (Cube Performance, Maintenance Alerts, Service Response Time, Provider Performance, CSD Bag Pickups) must name specific cubes, operators, and failure types with exact numbers. No section should summarize in general terms when specific data is available.

PASS: Every section names specific cube names (e.g., "Safeway 1196"), specific counts (e.g., "122 maintenance transitions"), and specific operators or failure modes (e.g., "CRUSHER_HAS_FAULTED"). The ops team can act on this briefing without going back to the raw data.

FAIL: Any section uses vague language like "several sites," "some operators," "certain cubes," or "high maintenance activity" without naming the specific locations and numbers.

Verdict:
Critique:

---

CHECK 2: Cross-Signal Synthesis

The briefing must make at least one connection that spans two or more different sections — an insight that only emerges from reading the full picture, not from any single data table.

PASS: At least one observation explicitly connects signals from two sections. Examples: noting that the highest-volume location is also the most maintenance-troubled and explaining what that tension means for the business; linking CSD bag overflow to high maintenance transitions at the same sites; connecting Sherpa acceptance lag to cube dwell time as cause and effect.

FAIL: Every section reads as a standalone summary. No section references data or patterns from another section. The briefing could have been written section by section in isolation.

Verdict:
Critique:

---

CHECK 3: Escalation Flag

The briefing must surface at least one signal that a single ops person cannot fix on their own — something requiring engineering involvement, leadership attention, or a vendor/grocery chain conversation. This distinguishes a fleet-level insight from a per-cube fix.

PASS: At least one fleet-level or systemic signal is explicitly called out. Examples: a failure type (e.g., DOOR_IS_OPEN, CRUSHER_HAS_FAULTED) appearing across 10 or more distinct cubes suggesting a hardware defect or firmware issue; Sherpa bench depth critically low across a geographic zone; a pattern at high-volume sites suggesting the service model needs renegotiation with the grocery chain.

FAIL: All flagged issues are framed as per-cube fixes ("dispatch a Sherpa to Safeway 1196"). No signal is elevated to fleet-level or identified as requiring a stakeholder beyond the ops team.

Verdict:
Critique:

---

OVERALL VERDICT

A briefing PASSES only if all 4 checks pass. If any check fails, the overall verdict is FAIL.

Overall verdict: PASS or FAIL
Primary failure reason (if FAIL): State which check failed and one sentence on the core gap.
```

---

## Output Format for Scoring Table

When running this across multiple briefings, record results in this format:

| Briefing Date | Prior Snapshot | Check 1A | Check 1B | Check 2 | Check 3 | Overall | Primary Failure |
|---------------|----------------|----------|----------|---------|---------|---------|-----------------|
| 2026-07-01    | no             | PASS     | PASS     | PASS    | FAIL    | FAIL    | Check 3: no escalation flag |
| 2026-07-08    | yes            | FAIL     | PASS     | PASS    | PASS    | FAIL    | Check 1A: no trend comparison |

---

## Design Notes (for portfolio write-up)

**Why binary pass/fail instead of 1-5 scoring?**
Multi-criteria scoring creates false precision. A briefing that scores 3/5 on four dimensions gives you no actionable signal — you don't know what to fix or whether it's usable. Binary forces the question: would you actually send this to the CEO and ops team today? If any answer is no, the briefing fails and you fix the prompt or the code.

**Why 4 checks instead of 1?**
One overall pass/fail hides where the failure is. Four targeted checks tell you exactly what went wrong — and whether it's a prompt issue (e.g., the prompt doesn't instruct the model to compare to prior period) or a code issue (e.g., the prior snapshot data isn't being passed correctly).

**Why are 1A and 1B separate?**
They serve different audiences reading the same document. A briefing can be excellent for ops (every cube named, every failure counted) but useless for the CEO if it doesn't frame growth. They can fail independently.

**What a failing briefing looks like for each check:**
- Check 1A fail: "July generated strong deposit volumes across the fleet." No numbers, no comparison.
- Check 1B fail: "Several high-maintenance cubes were flagged for attention." No names, no counts.
- Check 2 fail: Each section is a clean standalone summary. No line anywhere connects two sections.
- Check 3 fail: Actions are all "dispatch Sherpa to X" or "schedule maintenance at Y." Nothing escalated to engineering or leadership.
