#!/usr/bin/env python3
"""
LLM-as-Judge Eval Script — Olyns Operational Briefing

SETUP (one time):
  1. Make sure you have your ANTHROPIC_API_KEY available.
     In your terminal, run:  export ANTHROPIC_API_KEY=your_key_here
     Or create a .env file in this folder with: ANTHROPIC_API_KEY=your_key_here

  2. Install dependencies if not already installed:
     pip install anthropic python-dotenv

HOW TO RUN:
  1. Put your downloaded briefing .txt files in:  evals/briefings/
     Name them by date, e.g.: 2026-07-01-briefing.txt
     If a briefing was run WITH a prior snapshot loaded, add "-snapshot" to the name:
     e.g.: 2026-07-08-briefing-snapshot.txt

  2. From the olyns-briefing folder, run:
     python3 evals/run_eval.py

  3. Results are saved to: evals/eval-results.csv
     Open it in Excel or Google Sheets to review.
"""

import anthropic
import os
import json
import csv
from pathlib import Path

# Try loading .env file if it exists
try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).parent / ".env")
except ImportError:
    pass

# ── Paths ─────────────────────────────────────────────────────────────
BRIEFINGS_DIR = Path(__file__).parent / "briefings"
OUTPUT_CSV    = Path(__file__).parent / "eval-results.csv"
MODEL         = "claude-sonnet-4-6"

# ── Judge Prompt ──────────────────────────────────────────────────────
JUDGE_PROMPT = """
You are evaluating an Olyns Operational Briefing. Judge its quality against a pass/fail rubric. Be strict — if a criterion is not clearly met, mark it FAIL.

CONTEXT

Olyns operates a network of AI-powered recycling kiosks called Cubes, placed inside grocery stores. Consumers deposit cans and bottles for CRV refunds. Gig workers called Sherpas are dispatched to service cubes when they fill up. The briefing goes to two audiences:

- CEO: Cares about user growth, deposit volume, and whether the numbers support expansion conversations with grocery store chains.
- Ops team: Cares about which specific cubes need maintenance, Sherpa performance and coverage gaps, CSD bag overflow, and any patterns requiring escalation.

PRIOR SNAPSHOT AVAILABLE: {prior_snapshot}

BRIEFING TO EVALUATE:

{briefing_text}

---

EVALUATION — output only valid JSON, no other text before or after:

{{
  "check_1a": {{
    "verdict": "PASS or FAIL",
    "critique": "one to two sentences quoting or referencing specific briefing text"
  }},
  "check_1b": {{
    "verdict": "PASS or FAIL",
    "critique": "one to two sentences quoting or referencing specific briefing text"
  }},
  "check_2": {{
    "verdict": "PASS or FAIL",
    "critique": "one to two sentences quoting or referencing specific briefing text"
  }},
  "check_3": {{
    "verdict": "PASS or FAIL",
    "critique": "one to two sentences quoting or referencing specific briefing text"
  }},
  "overall": {{
    "verdict": "PASS or FAIL",
    "primary_failure": "which check failed and one sentence on the core gap, or null if PASS"
  }}
}}

CHECK DEFINITIONS:

CHECK 1A — CEO Growth Narrative
If prior snapshot available: PASS requires total deposits and unique users compared to prior period with directional signal (e.g. "up 12% from last month"). FAIL if only absolute numbers given with no comparison.
If no prior snapshot: PASS requires total deposits and unique users clearly and prominently stated, with location-level context on where volume is concentrated. FAIL if these headline numbers are missing or buried.

CHECK 1B — Ops Specificity
Every ops section (Cube Performance, Maintenance Alerts, Service Response Time, Provider Performance, CSD Bag Pickups) must name specific cubes, operators, and failure types with exact numbers.
PASS: Every section names specific cube names, exact counts, operator IDs, and failure modes. Ops can act without going back to raw data.
FAIL: Any section uses vague language like "several sites," "some operators," or "certain cubes" without naming them specifically.

CHECK 2 — Cross-Signal Synthesis
PASS: At least one observation explicitly connects signals from two or more different sections. Example: noting that the highest-volume location is also the most maintenance-troubled and explaining what that tension means for the business.
FAIL: Every section is a standalone summary. No section references data or patterns from another section. The briefing reads as if each section was written in isolation.

CHECK 3 — Escalation Flag
PASS: At least one fleet-level or systemic signal is explicitly called out as requiring escalation beyond routine ops — engineering involvement, leadership attention, or a vendor or grocery chain conversation. Example: a failure type appearing across 10 or more distinct cubes suggesting a hardware defect, or Sherpa bench depth critically low across a geographic zone.
FAIL: All flagged issues are framed as per-cube fixes. Nothing is elevated to fleet-level or identified as needing a stakeholder beyond the ops team.

OVERALL: PASS only if all 4 checks pass. FAIL if any check fails.
"""

# ── Judge Runner ──────────────────────────────────────────────────────
def run_judge(client, briefing_text, prior_snapshot):
    prompt = JUDGE_PROMPT.format(
        prior_snapshot="yes" if prior_snapshot else "no",
        briefing_text=briefing_text
    )
    message = client.messages.create(
        model=MODEL,
        max_tokens=1500,
        messages=[{"role": "user", "content": prompt}]
    )
    raw = message.content[0].text.strip()

    # strip markdown code fences if the model adds them
    if raw.startswith("```"):
        parts = raw.split("```")
        raw = parts[1] if len(parts) > 1 else raw
        if raw.startswith("json"):
            raw = raw[4:].strip()

    return json.loads(raw)


# ── Main ──────────────────────────────────────────────────────────────
def main():
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        print("ERROR: ANTHROPIC_API_KEY not found.")
        print("Run: export ANTHROPIC_API_KEY=your_key_here")
        return

    client = anthropic.Anthropic(api_key=api_key)

    briefing_files = sorted(BRIEFINGS_DIR.glob("*.txt"))
    if not briefing_files:
        print(f"No .txt files found in {BRIEFINGS_DIR}")
        print("Download briefings from the tool and save them there.")
        return

    print(f"Found {len(briefing_files)} briefing(s). Running eval...\n")

    results = []
    for f in briefing_files:
        prior_snapshot = "snapshot" in f.name.lower()
        briefing_text  = f.read_text(encoding="utf-8")

        print(f"Scoring: {f.name}  (prior snapshot: {'yes' if prior_snapshot else 'no'})")

        try:
            scores = run_judge(client, briefing_text, prior_snapshot)
            row = {
                "file":            f.name,
                "prior_snapshot":  "yes" if prior_snapshot else "no",
                "check_1a":        scores["check_1a"]["verdict"],
                "check_1a_note":   scores["check_1a"]["critique"],
                "check_1b":        scores["check_1b"]["verdict"],
                "check_1b_note":   scores["check_1b"]["critique"],
                "check_2":         scores["check_2"]["verdict"],
                "check_2_note":    scores["check_2"]["critique"],
                "check_3":         scores["check_3"]["verdict"],
                "check_3_note":    scores["check_3"]["critique"],
                "overall":         scores["overall"]["verdict"],
                "primary_failure": scores["overall"]["primary_failure"] or "",
            }
            results.append(row)
            print(f"  Check 1A: {row['check_1a']}  |  Check 1B: {row['check_1b']}  |  Check 2: {row['check_2']}  |  Check 3: {row['check_3']}  |  Overall: {row['overall']}")

        except Exception as e:
            print(f"  ERROR: {e}")
            results.append({
                "file": f.name, "prior_snapshot": "yes" if prior_snapshot else "no",
                "check_1a": "ERROR", "check_1a_note": str(e),
                "check_1b": "", "check_1b_note": "",
                "check_2": "",  "check_2_note": "",
                "check_3": "",  "check_3_note": "",
                "overall": "ERROR", "primary_failure": str(e),
            })

    # write CSV
    fieldnames = [
        "file", "prior_snapshot",
        "check_1a", "check_1a_note",
        "check_1b", "check_1b_note",
        "check_2",  "check_2_note",
        "check_3",  "check_3_note",
        "overall",  "primary_failure"
    ]
    with open(OUTPUT_CSV, "w", newline="", encoding="utf-8") as csvf:
        writer = csv.DictWriter(csvf, fieldnames=fieldnames)
        writer.writeheader()
        for row in results:
            writer.writerow({k: row.get(k, "") for k in fieldnames})

    print(f"\nResults saved to: {OUTPUT_CSV}")

    valid = [r for r in results if r.get("overall") in ("PASS", "FAIL")]
    if valid:
        pass_count = sum(1 for r in valid if r["overall"] == "PASS")
        print(f"Pass rate: {pass_count}/{len(valid)} ({round(pass_count / len(valid) * 100)}%)")
        for check in ["check_1a", "check_1b", "check_2", "check_3"]:
            c_pass = sum(1 for r in valid if r.get(check) == "PASS")
            print(f"  {check}: {c_pass}/{len(valid)} passed")


if __name__ == "__main__":
    main()
