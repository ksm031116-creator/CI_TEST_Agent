"""Grading records and the checks code can make on a stored analysis run.

A grading record is a person's (or a first-pass grader's) judgment of one run:
does the report name the cause written in the answer label? The rules are in
docs/grading_spec.md. Code decides only what needs no judgment: whether the
conclusion type is allowed, whether the top candidate points at the labelled
file and line, and whether a record is consistent with the report it grades.

This package reads answer labels. Nothing under ci_failure_analyzer.analysis
may import it.
"""

from __future__ import annotations

from dataclasses import dataclass

SPEC_VERSION = "1"
MATCH, PARTIAL, MISMATCH = "match", "partial", "mismatch"
VERDICTS = (MATCH, PARTIAL, MISMATCH)
NOT_TOP, UNSPECIFIED, WRONG_SIDE, WITHHELD = "not_top", "unspecified", "wrong_side", "withheld"
PARTIAL_REASONS = (NOT_TOP, UNSPECIFIED, WRONG_SIDE, WITHHELD)
OUT_OF_SCOPE = "out_of_scope"
LINE_TOLERANCE = 2
_CONFIDENCE_RANK = {"high": 0, "medium": 1, "low": 2}


def top_candidate_index(report: dict | None) -> int | None:
    """1-based index of the most confident candidate; the earlier one wins a tie."""
    candidates = (report or {}).get("cause_candidates") or []
    if not candidates:
        return None
    return 1 + min(range(len(candidates)), key=lambda i: (_CONFIDENCE_RANK[candidates[i]["confidence"]], i))


def conclusion_allowed(report: dict | None, label: dict) -> bool:
    if report is None or report["conclusion"] not in label["acceptable_conclusions"]:
        return False
    if report["conclusion"] == OUT_OF_SCOPE:
        return report.get("reason_code") == label.get("expected_reason_code")
    return True


def automatic_verdict(report: dict | None, label: dict) -> str | None:
    """Verdict for runs that need no judgment, else None.

    No report, an out_of_scope report, or an out_of_scope label: the run is right
    exactly when the conclusion and reason code are the labelled ones.
    """
    if report is None:
        return MISMATCH
    if report["conclusion"] == OUT_OF_SCOPE or label["acceptable_conclusions"] == [OUT_OF_SCOPE]:
        return MATCH if conclusion_allowed(report, label) else MISMATCH
    return None


def location_match(report: dict | None, label: dict) -> str:
    """How the top candidate's location compares with the labelled cause.

    "n/a": the label has no code location or expects no analysis. "none": no top candidate or it gives
    no location. "line": same file, within LINE_TOLERANCE lines. "file": same
    file only. "other": a different file.
    """
    cause = label["root_cause"]
    if not cause.get("file") or label["acceptable_conclusions"] == [OUT_OF_SCOPE]:
        return "n/a"
    index = top_candidate_index(report)
    location = report["cause_candidates"][index - 1].get("location") if index else None
    if not location:
        return "none"
    if location["path"].replace("\\", "/").removeprefix("./") != cause["file"]:
        return "other"
    return "line" if abs(location["line"] - cause["line"]) <= LINE_TOLERANCE else "file"


def wrong_high_candidates(report: dict, matched_candidate: int | None) -> list[int]:
    """1-based indexes of high-confidence candidates that are not the labelled cause."""
    return [
        number
        for number, candidate in enumerate(report.get("cause_candidates") or [], 1)
        if candidate["confidence"] == "high" and number != matched_candidate
    ]


def grading_problems(grading: dict, report: dict, label: dict, report_sha256: str) -> list[str]:
    """Why a grading record cannot be used as it stands. Empty when it is consistent."""
    problems: list[str] = []
    if grading.get("spec_version") != SPEC_VERSION:
        problems.append(f"spec_version is {grading.get('spec_version')!r}, expected {SPEC_VERSION!r}")
    if grading.get("report_sha256") != report_sha256:
        problems.append("report_sha256 does not match the stored report")
    verdict = grading.get("verdict")
    if verdict is None:
        return [*problems, "not graded yet"]
    if verdict not in VERDICTS:
        return [*problems, f"unknown verdict {verdict!r}"]
    matched = grading.get("matched_candidate")
    reasons = list(grading.get("partial_reasons") or [])
    count = len(report.get("cause_candidates") or [])
    top = top_candidate_index(report)
    allowed = conclusion_allowed(report, label)
    if matched is not None and not 1 <= matched <= count:
        problems.append(f"matched_candidate {matched} is not one of the report's {count} candidates")
    unknown = sorted(set(reasons) - set(PARTIAL_REASONS))
    if unknown:
        problems.append(f"unknown partial_reasons: {', '.join(unknown)}")
    if not (grading.get("rationale") or "").strip():
        problems.append("rationale is empty")
    if verdict == MATCH:
        if matched is None or matched != top:
            problems.append("match needs matched_candidate to be the top candidate")
        if not allowed:
            problems.append("match needs an allowed conclusion")
        if reasons:
            problems.append("match cannot have partial_reasons")
    elif verdict == PARTIAL:
        if matched is None:
            problems.append("partial needs matched_candidate")
        if not reasons:
            problems.append("partial needs partial_reasons")
        if matched is not None and (NOT_TOP in reasons) != (matched != top):
            problems.append("not_top must be listed exactly when matched_candidate is not the top candidate")
        if (WITHHELD in reasons) != (not allowed):
            problems.append("withheld must be listed exactly when the conclusion is not allowed")
    else:
        if matched is not None:
            problems.append("mismatch cannot have matched_candidate")
        if reasons:
            problems.append("mismatch cannot have partial_reasons")
    review = grading.get("review")
    if review is not None and review.get("verdict") not in VERDICTS:
        problems.append(f"unknown review verdict {review.get('verdict')!r}")
    return problems


def effective_verdict(grading: dict) -> str:
    """The reviewer's verdict when a person has reviewed the record, else the grader's."""
    review = grading.get("review")
    return review["verdict"] if review else grading["verdict"]


def is_correct_but_withheld(grading: dict) -> bool:
    """The top candidate is the labelled cause and the only shortfall is the conclusion type."""
    return effective_verdict(grading) == PARTIAL and list(grading.get("partial_reasons") or []) == [WITHHELD]


@dataclass(frozen=True)
class RunScore:
    """One run's results: code-decided checks plus the verdict, if any."""

    run_id: str
    case_id: str
    method: str
    has_report: bool
    first_reply_passed: bool | None
    conclusion: str | None
    conclusion_allowed: bool
    location: str
    verdict: str | None
    verdict_source: str
    reviewed: bool
    withheld: bool
    wrong_high: bool | None
    top_candidate_key: str | None
    problems: tuple[str, ...] = ()


def score_run(manifest: dict, report: dict | None, label: dict, grading: dict | None, report_sha256: str | None) -> RunScore:
    """Combine a stored run, its label and its grading record (None when absent)."""
    attempts = manifest.get("attempts") or []
    first_passed = None
    if attempts:
        # Method C records every model call; the first reply that is not a tool
        # request is its first report. A run that never got that far did not pass.
        reports = [a for a in attempts if a.get("kind", "report") == "report"]
        first = reports[0] if reports else None
        first_passed = (
            first is not None
            and first["stop_reason"] == "end_turn"
            and not first["format_problems"]
            and not first["citation_problems"]
        )
    verdict = automatic_verdict(report, label)
    source = "code" if verdict else "ungraded"
    problems: tuple[str, ...] = ()
    reviewed = withheld = False
    wrong_high: bool | None = None
    key = None
    if verdict is None and grading is not None:
        problems = tuple(grading_problems(grading, report, label, report_sha256 or ""))
        if not problems:
            verdict = effective_verdict(grading)
            reviewed = grading.get("review") is not None
            source = "reviewed" if reviewed else "grader"
            withheld = is_correct_but_withheld(grading)
            wrong_high = bool(wrong_high_candidates(report, grading.get("matched_candidate")))
            key = grading.get("top_candidate_key")
    return RunScore(
        run_id=manifest["run_id"],
        case_id=label["case_id"],
        method=manifest["method"],
        has_report=report is not None,
        first_reply_passed=first_passed,
        conclusion=report["conclusion"] if report else None,
        conclusion_allowed=conclusion_allowed(report, label),
        location=location_match(report, label),
        verdict=verdict,
        verdict_source=source,
        reviewed=reviewed,
        withheld=withheld,
        wrong_high=wrong_high,
        top_candidate_key=key,
        problems=problems,
    )
