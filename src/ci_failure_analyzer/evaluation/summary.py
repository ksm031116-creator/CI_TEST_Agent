"""Aggregate scored runs into the numbers the evaluation tables show.

Everything here is counting. Verdicts come from `grading.score_run`; cost,
tokens and duration come from the run manifests. The functions return plain
dicts so the same numbers can be printed as Markdown or written as JSON.
"""

from __future__ import annotations

from collections import Counter
from decimal import Decimal
from statistics import median

from ci_failure_analyzer.evaluation.grading import MATCH, MISMATCH, PARTIAL, RunScore

UNGRADED = "ungraded"
LOCATIONS = ("line", "file", "other", "none")


def method_summary(rows: list[RunScore]) -> dict:
    """Run-level counts for one method."""
    verdicts = Counter(s.verdict for s in rows)
    located = [s for s in rows if s.location != "n/a"]
    location = Counter(s.location for s in located)
    called = [s for s in rows if s.first_reply_passed is not None]
    judged = [s for s in rows if s.verdict_source in ("grader", "reviewed")]
    return {
        "runs": len(rows),
        "verdicts": {MATCH: verdicts[MATCH], PARTIAL: verdicts[PARTIAL], MISMATCH: verdicts[MISMATCH], UNGRADED: verdicts[None]},
        "correct_but_withheld": sum(s.withheld for s in rows),
        "wrong_high_confidence": sum(bool(s.wrong_high) for s in rows),
        "conclusion_allowed": sum(s.conclusion_allowed for s in rows),
        "location": {name: location[name] for name in LOCATIONS} | {"applicable": len(located)},
        "first_reply_passed": {"passed": sum(bool(s.first_reply_passed) for s in called), "called": len(called)},
        "reviewed": {"reviewed": sum(s.reviewed for s in judged), "judged": len(judged)},
    }


def case_summary(groups: list[list[RunScore]]) -> dict:
    """Case-level counts for one method. Each group is one case's runs, oldest first."""
    groups = [g for g in groups if g]
    keyed = [g for g in groups if any(s.top_candidate_key for s in g)]
    return {
        "cases": len(groups),
        "all_runs_match": sum(all(s.verdict == MATCH for s in g) for g in groups),
        "majority_match": sum(2 * sum(s.verdict == MATCH for s in g) > len(g) for g in groups),
        "same_verdict": sum(len({s.verdict for s in g}) == 1 for g in groups),
        "same_conclusion": sum(len({s.conclusion for s in g}) == 1 for g in groups),
        "same_top_candidate": sum(len({s.top_candidate_key for s in g}) == 1 for g in keyed),
        "cases_with_top_candidate": len(keyed),
    }


def cost_summary(manifests: list[dict]) -> dict:
    """Calls, tokens, cost and duration of one method's runs.

    Averages and the median are over runs that called the model; a run decided
    without a call (out of scope) costs nothing and would only pull them down.
    Cost stays a decimal string, as in the manifests and the usage ledger.
    """
    called = [m for m in manifests if m.get("model_calls")]
    cost = sum((Decimal(m.get("cost_usd") or "0") for m in manifests), Decimal(0))
    durations = [m["duration_seconds"] for m in called if m.get("duration_seconds") is not None]
    count = len(called)
    return {
        "runs": len(manifests),
        "runs_with_calls": count,
        "model_calls": sum(m.get("model_calls") or 0 for m in manifests),
        "tool_calls": sum(m.get("tool_call_count") or 0 for m in manifests),
        "input_tokens": sum(m.get("input_tokens") or 0 for m in manifests),
        "output_tokens": sum(m.get("output_tokens") or 0 for m in manifests),
        "cost_usd": f"{cost:.6f}",
        "cost_usd_per_run": f"{cost / count:.6f}" if count else None,
        "max_cost_usd": f"{max(Decimal(m.get('cost_usd') or '0') for m in called):.6f}" if count else None,
        "median_duration_seconds": round(median(durations), 1) if durations else None,
        "max_duration_seconds": max(durations) if durations else None,
    }


def match_counts(scores: list[RunScore], case_ids: list[str], methods: list[str]) -> dict[str, dict[str, dict | None]]:
    """Per case and method: how many runs matched, out of how many. None when the method has no run."""
    table: dict[str, dict[str, dict | None]] = {}
    for case_id in case_ids:
        table[case_id] = {}
        for method in methods:
            rows = [s for s in scores if s.case_id == case_id and s.method == method]
            table[case_id][method] = {"match": sum(s.verdict == MATCH for s in rows), "runs": len(rows)} if rows else None
    return table
