import copy
import json

import pytest

from ci_failure_analyzer.report.schema import Conclusion, ReportFormatError, parse_report

VALID = {
    "schema_version": "1",
    "conclusion": "cause_candidate",
    "observed_facts": [{"statement": "test_a fails with KeyError", "evidence_ids": ["E1"]}],
    "cause_candidates": [
        {
            "summary": "lookup uses the wrong key",
            "reasoning": "the traceback ends in the lookup line",
            "confidence": "high",
            "location": {"path": "src/app.py", "line": 3},
            "evidence_ids": ["E1", "E2"],
        }
    ],
    "evidence": [
        {"id": "E1", "source": "log", "path": "job.log", "start_line": 2, "end_line": 2, "quote": "KeyError: 'x'"},
        {"id": "E2", "source": "code", "path": "src/app.py", "start_line": 3, "end_line": 3, "quote": "return d['x']"},
    ],
    "verification_steps": [{"description": "run the test locally", "command": "pytest tests/test_a.py"}],
    "limitations": [],
}


def changed(**updates):
    data = copy.deepcopy(VALID)
    data.update(updates)
    return data


def problems_of(data) -> str:
    with pytest.raises(ReportFormatError) as excinfo:
        parse_report(data)
    return " | ".join(excinfo.value.problems)


def test_valid_report_parses_from_dict_and_json():
    assert parse_report(VALID).conclusion is Conclusion.CAUSE_CANDIDATE
    assert parse_report(json.dumps(VALID)).cause_candidates[0].location.line == 3


def test_invalid_json_is_a_format_error():
    assert "JSON" in problems_of("{not json")


def test_missing_required_field_is_reported_with_its_path():
    data = copy.deepcopy(VALID)
    del data["cause_candidates"][0]["reasoning"]
    assert "cause_candidates.0.reasoning" in problems_of(data)


def test_unknown_field_is_rejected():
    assert "fix_patch" in problems_of(changed(fix_patch="..."))


def test_unknown_conclusion_is_rejected():
    assert "conclusion" in problems_of(changed(conclusion="root_cause_found"))


def test_blank_text_is_rejected():
    data = copy.deepcopy(VALID)
    data["observed_facts"][0]["statement"] = "   "
    assert "observed_facts.0.statement" in problems_of(data)


def test_fact_without_evidence_is_rejected():
    data = copy.deepcopy(VALID)
    data["observed_facts"][0]["evidence_ids"] = []
    assert "observed_facts.0.evidence_ids" in problems_of(data)


def test_reference_to_unknown_evidence_is_rejected():
    data = copy.deepcopy(VALID)
    data["cause_candidates"][0]["evidence_ids"] = ["E9"]
    assert "unknown evidence ids: E9" in problems_of(data)


def test_duplicate_evidence_id_is_rejected():
    data = copy.deepcopy(VALID)
    data["evidence"][1]["id"] = "E1"
    assert "duplicate evidence ids: E1" in problems_of(data)


def test_reversed_line_range_is_rejected():
    data = copy.deepcopy(VALID)
    data["evidence"][0]["end_line"] = 1
    assert "end_line" in problems_of(data)


def test_log_evidence_must_cite_the_job_log():
    data = copy.deepcopy(VALID)
    data["evidence"][0]["path"] = "src/app.py"
    assert "must be job.log" in problems_of(data)


def test_cause_candidate_conclusion_needs_a_candidate():
    assert "needs at least one cause candidate" in problems_of(changed(cause_candidates=[]))


def test_verification_step_is_required():
    assert "verification step" in problems_of(changed(verification_steps=[]))


def test_insufficient_evidence_needs_limitation_and_no_high_confidence():
    message = problems_of(changed(conclusion="insufficient_evidence"))
    assert "needs at least one limitation" in message
    assert "high-confidence" in message


def test_insufficient_evidence_may_keep_low_confidence_candidates():
    data = changed(conclusion="insufficient_evidence", limitations=["the data file is not in the input"])
    data["cause_candidates"][0]["confidence"] = "low"
    assert parse_report(data).conclusion is Conclusion.INSUFFICIENT_EVIDENCE


def test_out_of_scope_needs_reason_code_and_no_candidates():
    message = problems_of(changed(conclusion="out_of_scope"))
    assert "needs a reason_code" in message
    assert "must not list cause candidates" in message


def test_minimal_out_of_scope_report():
    report = parse_report({"conclusion": "out_of_scope", "reason_code": "no_junit"})
    assert report.reason_code == "no_junit"
    assert report.schema_version == "1"


def test_reason_code_is_only_for_out_of_scope():
    assert "only for out_of_scope" in problems_of(changed(reason_code="no_junit"))
