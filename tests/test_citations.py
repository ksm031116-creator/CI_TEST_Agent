import pytest

from ci_failure_analyzer.inputs.reader import BundleReader, split_lines
from ci_failure_analyzer.report.citations import (
    FILE_NOT_FOUND,
    LINE_OUT_OF_RANGE,
    NOT_IN_CONTEXT,
    QUOTE_MISMATCH,
    check_citations,
)
from ci_failure_analyzer.report.schema import parse_report

LOG = "pytest\tRun tests\tcollected 1 item\npytest\tRun tests\tE   KeyError: 'x'\n"
CODE = {
    "src/app.py": "def get(d):\n    # lookup\n    return d['x']\n",
    "tests/test_app.py": "def test_get():\n    assert get({}) == 1\n",
}


@pytest.fixture
def reader(make_bundle):
    return BundleReader(make_bundle(LOG, CODE, junit="<testsuites>\n</testsuites>\n"))


def report_with(*evidence):
    return parse_report(
        {
            "conclusion": "cause_candidate",
            "observed_facts": [{"statement": "fails", "evidence_ids": [evidence[0]["id"]]}],
            "cause_candidates": [
                {"summary": "s", "reasoning": "r", "confidence": "low", "evidence_ids": [evidence[0]["id"]]}
            ],
            "evidence": list(evidence),
            "verification_steps": [{"description": "rerun"}],
        }
    )


def log_evidence(**overrides):
    base = {"id": "E1", "source": "log", "path": "job.log", "start_line": 2, "end_line": 2, "quote": "KeyError: 'x'"}
    return {**base, **overrides}


def code_evidence(**overrides):
    base = {"id": "E2", "source": "code", "path": "src/app.py", "start_line": 3, "end_line": 3, "quote": "return d['x']"}
    return {**base, **overrides}


def codes(problems):
    return [(p.evidence_id, p.code) for p in problems]


def test_split_lines_counts_only_newlines():
    assert split_lines("a\r\nb\x0cc\n") == ["a", "b\x0cc"]


def test_existing_citations_pass(reader):
    report = report_with(log_evidence(), code_evidence())
    assert check_citations(report, reader) == []


def test_quote_matching_ignores_indentation_and_wrapping(reader):
    evidence = code_evidence(start_line=2, end_line=3, quote="# lookup\nreturn   d['x']")
    assert check_citations(report_with(evidence), reader) == []


def test_missing_file_is_detected(reader):
    problems = check_citations(report_with(code_evidence(path="src/missing.py")), reader)
    assert codes(problems) == [("E2", FILE_NOT_FOUND)]


def test_line_out_of_range_is_detected(reader):
    problems = check_citations(report_with(code_evidence(start_line=3, end_line=4)), reader)
    assert codes(problems) == [("E2", LINE_OUT_OF_RANGE)]


def test_quote_from_another_line_is_a_mismatch(reader):
    problems = check_citations(report_with(code_evidence(start_line=1, end_line=1)), reader)
    assert codes(problems) == [("E2", QUOTE_MISMATCH)]


def test_invented_log_quote_is_a_mismatch(reader):
    problems = check_citations(report_with(log_evidence(quote="KeyError: 'y'")), reader)
    assert codes(problems) == [("E1", QUOTE_MISMATCH)]


def test_code_outside_the_provided_context_is_detected(reader):
    report = report_with(log_evidence(), code_evidence())
    problems = check_citations(report, reader, provided_code_paths=["tests/test_app.py"])
    assert codes(problems) == [("E2", NOT_IN_CONTEXT)]


def test_log_only_analysis_cannot_cite_code(reader):
    report = report_with(code_evidence())
    assert codes(check_citations(report, reader, provided_code_paths=[])) == [("E2", NOT_IN_CONTEXT)]


def test_junit_evidence_is_checked_against_the_report_file(reader):
    evidence = {"id": "E3", "source": "junit", "path": "reports/junit.xml", "start_line": 1, "end_line": 1,
                "quote": "<testsuites>"}
    assert check_citations(report_with(evidence), reader) == []


def test_every_broken_citation_is_reported(reader):
    report = report_with(log_evidence(quote="nope"), code_evidence(path="x.py"))
    assert codes(check_citations(report, reader)) == [("E1", QUOTE_MISMATCH), ("E2", FILE_NOT_FOUND)]


def test_code_citation_must_be_within_lines_a_tool_showed(reader):
    report = report_with(log_evidence(), code_evidence(start_line=2, end_line=3))
    assert check_citations(report, reader, seen_code_lines={"src/app.py": {1, 2, 3}}) == []
    problems = check_citations(report, reader, seen_code_lines={"src/app.py": {3}})
    assert codes(problems) == [("E2", NOT_IN_CONTEXT)]
    assert "lines 2 were not shown" in problems[0].detail


def test_code_citation_of_a_file_no_tool_read_is_reported(reader):
    report = report_with(log_evidence(), code_evidence())
    problems = check_citations(report, reader, seen_code_lines={"tests/test_app.py": {1, 2}})
    assert codes(problems) == [("E2", NOT_IN_CONTEXT)]
    assert "was not read with a tool" in problems[0].detail


def test_seen_lines_replace_the_provided_paths_check_and_leave_log_citations_alone(reader):
    report = report_with(log_evidence(), code_evidence())
    assert check_citations(report, reader, provided_code_paths=[], seen_code_lines={"src/app.py": {3}}) == []
    assert check_citations(report_with(log_evidence()), reader, seen_code_lines={}) == []


def test_missing_file_and_line_are_still_reported_as_such_with_seen_lines(reader):
    report = report_with(log_evidence(), code_evidence(path="src/none.py"), code_evidence(id="E3", start_line=9, end_line=9))
    problems = check_citations(report, reader, seen_code_lines={})
    assert codes(problems) == [("E2", FILE_NOT_FOUND), ("E3", LINE_OUT_OF_RANGE)]


def test_quote_is_still_checked_for_seen_lines(reader):
    report = report_with(log_evidence(), code_evidence(quote="return d['y']"))
    assert codes(check_citations(report, reader, seen_code_lines={"src/app.py": {3}})) == [("E2", QUOTE_MISMATCH)]
