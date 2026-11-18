from pathlib import Path

import pytest

from ci_failure_analyzer.evaluation.grading import (
    MATCH,
    MISMATCH,
    PARTIAL,
    SPEC_VERSION,
    automatic_verdict,
    conclusion_allowed,
    grading_problems,
    location_match,
    score_run,
    top_candidate_index,
    wrong_high_candidates,
)

SHA = "a" * 64
LABEL = {
    "case_id": "case-900",
    "root_cause": {"file": "src/shop/pricing.py", "line": 18, "summary": "boundary"},
    "acceptable_conclusions": ["cause_candidate"],
}
NO_FILE_LABEL = {
    "case_id": "case-901",
    "root_cause": {"file": None, "line": None, "summary": "external data"},
    "acceptable_conclusions": ["insufficient_evidence", "cause_candidate"],
}
OUT_OF_SCOPE_LABEL = {
    "case_id": "case-902",
    "root_cause": {"file": "pyproject.toml", "line": 9, "summary": "install"},
    "acceptable_conclusions": ["out_of_scope"],
    "expected_reason_code": "no_junit",
}


def candidate(confidence="medium", path=None, line=None):
    location = {"path": path, "line": line} if path else None
    return {"summary": "s", "reasoning": "r", "confidence": confidence, "location": location, "evidence_ids": ["E1"]}


def report(conclusion="cause_candidate", candidates=None, reason_code=None):
    return {"conclusion": conclusion, "reason_code": reason_code, "cause_candidates": candidates or []}


def grading(verdict, matched=None, reasons=(), **extra):
    record = {
        "spec_version": SPEC_VERSION,
        "report_sha256": SHA,
        "verdict": verdict,
        "matched_candidate": matched,
        "partial_reasons": list(reasons),
        "rationale": "because",
        "top_candidate_key": "boundary",
        "review": None,
    }
    return record | extra


def manifest(method="B", attempts=None):
    first = {"stop_reason": "end_turn", "format_problems": [], "citation_problems": []}
    return {"run_id": "run-1", "method": method, "attempts": [first] if attempts is None else attempts}


def test_top_candidate_is_most_confident_and_first_on_ties():
    assert top_candidate_index(report(candidates=[candidate("low"), candidate("medium"), candidate("medium")])) == 2
    assert top_candidate_index(report()) is None
    assert top_candidate_index(None) is None


def test_conclusion_allowed_checks_reason_code_for_out_of_scope():
    assert conclusion_allowed(report("out_of_scope", reason_code="no_junit"), OUT_OF_SCOPE_LABEL)
    assert not conclusion_allowed(report("out_of_scope", reason_code="other"), OUT_OF_SCOPE_LABEL)
    assert not conclusion_allowed(report("insufficient_evidence"), LABEL)
    assert not conclusion_allowed(None, LABEL)


def test_automatic_verdict_only_where_no_judgment_is_needed():
    assert automatic_verdict(None, LABEL) == MISMATCH
    assert automatic_verdict(report("out_of_scope", reason_code="no_junit"), OUT_OF_SCOPE_LABEL) == MATCH
    assert automatic_verdict(report("cause_candidate", [candidate()]), OUT_OF_SCOPE_LABEL) == MISMATCH
    assert automatic_verdict(report("out_of_scope", reason_code="no_junit"), LABEL) == MISMATCH
    assert automatic_verdict(report("cause_candidate", [candidate()]), LABEL) is None


@pytest.mark.parametrize(
    ("path", "line", "expected"),
    [
        ("src/shop/pricing.py", 18, "line"),
        ("src/shop/pricing.py", 20, "line"),
        ("./src/shop/pricing.py", 21, "file"),
        ("tests/test_pricing.py", 18, "other"),
        (None, None, "none"),
    ],
)
def test_location_match_compares_top_candidate_with_label(path, line, expected):
    assert location_match(report(candidates=[candidate("high", path, line)]), LABEL) == expected


def test_location_match_is_not_applicable_without_a_labelled_file():
    assert location_match(report(candidates=[candidate("high", "a.py", 1)]), NO_FILE_LABEL) == "n/a"
    assert location_match(None, LABEL) == "none"
    assert location_match(report("out_of_scope", reason_code="no_junit"), OUT_OF_SCOPE_LABEL) == "n/a"


def test_wrong_high_candidates_excludes_the_matched_one():
    r = report(candidates=[candidate("high"), candidate("high"), candidate("low")])
    assert wrong_high_candidates(r, 1) == [2]
    assert wrong_high_candidates(r, None) == [1, 2]


def test_consistent_gradings_have_no_problems():
    two = report(candidates=[candidate("medium"), candidate("low")])
    assert grading_problems(grading(MATCH, 1), two, LABEL, SHA) == []
    assert grading_problems(grading(PARTIAL, 2, ["not_top"]), two, LABEL, SHA) == []
    assert grading_problems(grading(MISMATCH), two, LABEL, SHA) == []
    withheld = report("insufficient_evidence", [candidate("medium")])
    assert grading_problems(grading(PARTIAL, 1, ["withheld"]), withheld, LABEL, SHA) == []


@pytest.mark.parametrize(
    ("record", "conclusion", "fragment"),
    [
        (grading(MATCH, 2), "cause_candidate", "top candidate"),
        (grading(MATCH, 1), "insufficient_evidence", "allowed conclusion"),
        (grading(PARTIAL, 1, []), "cause_candidate", "needs partial_reasons"),
        (grading(PARTIAL, 2, ["unspecified"]), "cause_candidate", "not_top"),
        (grading(PARTIAL, 1, ["unspecified"]), "insufficient_evidence", "withheld"),
        (grading(PARTIAL, 1, ["withheld"]), "cause_candidate", "withheld"),
        (grading(MISMATCH, 1), "cause_candidate", "cannot have matched_candidate"),
        (grading(MATCH, 5), "cause_candidate", "not one of"),
        (grading(MATCH, 1, rationale=" "), "cause_candidate", "rationale"),
        (grading(MATCH, 1, report_sha256="b" * 64), "cause_candidate", "report_sha256"),
        (grading(None), "cause_candidate", "not graded"),
        (grading("maybe"), "cause_candidate", "unknown verdict"),
        (grading(MATCH, 1, review={"verdict": "ok"}), "cause_candidate", "review verdict"),
    ],
)
def test_inconsistent_gradings_are_reported(record, conclusion, fragment):
    r = report(conclusion, [candidate("medium"), candidate("low")])
    assert any(fragment in problem for problem in grading_problems(record, r, LABEL, SHA))


def test_score_run_uses_grading_and_flags_withheld():
    r = report("insufficient_evidence", [candidate("medium", "src/shop/pricing.py", 18)])
    score = score_run(manifest(), r, LABEL, grading(PARTIAL, 1, ["withheld"]), SHA)
    assert (score.verdict, score.verdict_source, score.withheld) == (PARTIAL, "grader", True)
    assert (score.conclusion_allowed, score.location, score.first_reply_passed) == (False, "line", True)
    assert score.wrong_high is False and score.top_candidate_key == "boundary"


def test_score_run_prefers_the_reviewers_verdict():
    r = report(candidates=[candidate("high")])
    reviewed = grading(MATCH, 1, review={"reviewer": "owner", "date": "2026-11-21", "verdict": PARTIAL, "note": ""})
    score = score_run(manifest(), r, LABEL, reviewed, SHA)
    assert (score.verdict, score.verdict_source, score.reviewed) == (PARTIAL, "reviewed", True)


def test_score_run_without_grading_or_with_a_bad_one_is_ungraded():
    r = report(candidates=[candidate("high")])
    assert score_run(manifest(), r, LABEL, None, SHA).verdict is None
    bad = score_run(manifest(), r, LABEL, grading(MISMATCH, 1), SHA)
    assert bad.verdict is None and bad.problems


def test_score_run_decides_out_of_scope_and_missing_reports_by_code():
    no_call = manifest(attempts=[])
    score = score_run(no_call, report("out_of_scope", reason_code="no_junit"), OUT_OF_SCOPE_LABEL, None, SHA)
    assert (score.verdict, score.verdict_source, score.first_reply_passed) == (MATCH, "code", None)
    failed = manifest(attempts=[{"stop_reason": "max_tokens", "format_problems": [], "citation_problems": []}])
    score = score_run(failed, None, LABEL, None, None)
    assert (score.verdict, score.has_report, score.first_reply_passed) == (MISMATCH, False, False)


def test_wrong_high_flag_counts_confident_candidates_that_miss():
    r = report(candidates=[candidate("high"), candidate("medium")])
    score = score_run(manifest(), r, LABEL, grading(PARTIAL, 2, ["not_top"]), SHA)
    assert score.wrong_high is True


def test_analysis_code_does_not_import_evaluation_or_read_labels():
    analysis = Path(__file__).resolve().parent.parent / "src" / "ci_failure_analyzer" / "analysis"
    for path in analysis.glob("*.py"):
        source = path.read_text(encoding="utf-8")
        for forbidden in ("ci_failure_analyzer.evaluation", "..evaluation", "gradings", "labels/"):
            assert forbidden not in source, f"{path.name} mentions {forbidden}"
