import json
from decimal import Decimal

import pytest

from ci_failure_analyzer.analysis.budget import BudgetConfig, BudgetExceededError, ModelPrice, UsageLedger
from ci_failure_analyzer.analysis.context import METHOD_A, METHOD_B
from ci_failure_analyzer.analysis.prompt import SYSTEM_PROMPT, prompt_sha256, report_schema
from ci_failure_analyzer.analysis.runner import (
    STATUS_CHECK_FAILED,
    STATUS_OK,
    STATUS_REFUSED,
    STATUS_TRUNCATED,
    ModelReply,
    run_analysis,
)
from ci_failure_analyzer.inputs.junit import parse_junit_bytes
from ci_failure_analyzer.inputs.reader import BundleReader

LOG = (
    "pytest\tInstall\tinstalling\n"
    "pytest\tRun tests\tE   KeyError: 'x'\n"
    "pytest\tRun tests\ttests/test_app.py:2: KeyError\n"
)
CODE = {
    "src/app.py": "def get(d):\n    return d['x']\n",
    "tests/test_app.py": "def test_get():\n    assert get({}) == 1\n",
}
JUNIT = """<testsuites><testsuite>
<testcase classname="tests.test_app" name="test_get"><failure message="KeyError: 'x'">tests/test_app.py:2: KeyError</failure></testcase>
</testsuite></testsuites>
"""


def report(evidence, conclusion="cause_candidate"):
    return {
        "schema_version": "1",
        "conclusion": conclusion,
        "reason_code": "no_junit" if conclusion == "out_of_scope" else None,
        "observed_facts": [{"statement": "test_get fails", "evidence_ids": [evidence["id"]]}],
        "cause_candidates": []
        if conclusion == "out_of_scope"
        else [
            {
                "summary": "missing key",
                "reasoning": "the log shows KeyError",
                "confidence": "medium",
                "location": None,
                "evidence_ids": [evidence["id"]],
            }
        ],
        "evidence": [evidence],
        "verification_steps": [{"description": "run the test", "command": None}],
        "limitations": [],
    }


LOG_EVIDENCE = {"id": "E1", "source": "log", "path": "job.log", "start_line": 2, "end_line": 2, "quote": "KeyError: 'x'"}
BAD_QUOTE = {**LOG_EVIDENCE, "quote": "ValueError"}
CODE_EVIDENCE = {
    "id": "E1",
    "source": "code",
    "path": "tests/test_app.py",
    "start_line": 2,
    "end_line": 2,
    "quote": "assert get({}) == 1",
}


class FakeClient:
    def __init__(self, *replies):
        self.replies = list(replies)
        self.calls = []

    def complete(self, **kwargs):
        self.calls.append(kwargs)
        reply = self.replies.pop(0)
        if isinstance(reply, ModelReply):
            return reply
        text = reply if isinstance(reply, str) else json.dumps(reply)
        return ModelReply(
            text=text,
            content=[{"type": "text", "text": text}],
            stop_reason="end_turn",
            input_tokens=1000,
            output_tokens=500,
        )


@pytest.fixture
def reader(make_bundle):
    return BundleReader(make_bundle(LOG, CODE, junit=JUNIT))


@pytest.fixture
def junit():
    return parse_junit_bytes(JUNIT.encode())


@pytest.fixture
def ledger(tmp_path):
    config = BudgetConfig(
        model="m",
        effort="medium",
        max_output_tokens=1000,
        total_limit_usd=Decimal("1"),
        pricing_date="2026-11-03",
        prices={"m": ModelPrice(Decimal("4"), Decimal("20"))},
    )
    return UsageLedger(tmp_path / "usage.jsonl", config)


def test_valid_reply_is_accepted_in_one_call(reader, junit, ledger):
    client = FakeClient(report(LOG_EVIDENCE))
    result = run_analysis(reader, junit, METHOD_A, client, ledger, "t")
    assert result.status == STATUS_OK
    assert result.report.evidence[0].id == "E1"
    assert len(client.calls) == 1
    call = client.calls[0]
    assert call["system"] == SYSTEM_PROMPT
    assert call["messages"] == [{"role": "user", "content": result.context.text}]
    assert call["schema"] == report_schema()
    assert (call["model"], call["effort"], call["max_tokens"]) == ("m", "medium", 1000)


def test_every_call_is_recorded_in_the_ledger(reader, junit, ledger):
    result = run_analysis(reader, junit, METHOD_A, FakeClient(report(BAD_QUOTE), report(LOG_EVIDENCE)), ledger, "t")
    entries = ledger.entries()
    assert [e["purpose"] for e in entries] == ["t#1", "t#2"]
    assert ledger.total_usd() == result.cost_usd == Decimal("0.028")


def test_citation_failure_is_sent_back_once_and_the_correction_accepted(reader, junit, ledger):
    client = FakeClient(report(BAD_QUOTE), report(LOG_EVIDENCE))
    result = run_analysis(reader, junit, METHOD_A, client, ledger, "t")
    assert result.status == STATUS_OK
    assert result.attempts[0].citation_problems and not result.attempts[1].citation_problems
    retry = client.calls[1]["messages"]
    assert [m["role"] for m in retry] == ["user", "assistant", "user"]
    assert "quote_mismatch" in retry[2]["content"]


def test_format_failure_is_sent_back_with_the_problems(reader, junit, ledger):
    broken = report(LOG_EVIDENCE)
    broken["verification_steps"] = []
    client = FakeClient(broken, report(LOG_EVIDENCE))
    result = run_analysis(reader, junit, METHOD_A, client, ledger, "t")
    assert result.status == STATUS_OK
    assert result.attempts[0].format_problems
    assert "verification step" in client.calls[1]["messages"][2]["content"]


def test_second_failure_ends_the_run_as_failed(reader, junit, ledger):
    client = FakeClient(report(BAD_QUOTE), report(BAD_QUOTE))
    result = run_analysis(reader, junit, METHOD_A, client, ledger, "t")
    assert result.status == STATUS_CHECK_FAILED
    assert len(client.calls) == 2
    assert result.report is not None


def test_reply_that_is_not_json_fails_the_format_check(reader, junit, ledger):
    result = run_analysis(reader, junit, METHOD_A, FakeClient("not json", "still not json"), ledger, "t")
    assert result.status == STATUS_CHECK_FAILED
    assert result.report is None


def test_method_a_citing_code_fails_and_method_b_passes(reader, junit, ledger):
    result_a = run_analysis(
        reader, junit, METHOD_A, FakeClient(report(CODE_EVIDENCE), report(CODE_EVIDENCE)), ledger, "a"
    )
    assert result_a.status == STATUS_CHECK_FAILED
    assert "not_in_context" in result_a.attempts[0].citation_problems[0]
    result_b = run_analysis(reader, junit, METHOD_B, FakeClient(report(CODE_EVIDENCE)), ledger, "b")
    assert result_b.status == STATUS_OK


def test_out_of_scope_conclusion_from_the_model_is_rejected(reader, junit, ledger):
    client = FakeClient(report(LOG_EVIDENCE, "out_of_scope"), report(LOG_EVIDENCE))
    result = run_analysis(reader, junit, METHOD_A, client, ledger, "t")
    assert result.attempts[0].format_problems == ("conclusion: out_of_scope is not allowed here",)
    assert result.status == STATUS_OK


@pytest.mark.parametrize(("stop_reason", "status"), [("max_tokens", STATUS_TRUNCATED), ("refusal", STATUS_REFUSED)])
def test_cut_off_or_refused_reply_is_not_retried(reader, junit, ledger, stop_reason, status):
    reply = ModelReply(text="{", content=[], stop_reason=stop_reason, input_tokens=1000, output_tokens=1000)
    client = FakeClient(reply)
    result = run_analysis(reader, junit, METHOD_A, client, ledger, "t")
    assert result.status == status
    assert len(client.calls) == 1
    assert len(ledger.entries()) == 1


def test_no_call_is_made_when_the_limit_could_be_exceeded(reader, junit, ledger):
    client = FakeClient(report(LOG_EVIDENCE))
    with pytest.raises(BudgetExceededError):
        run_analysis(reader, junit, METHOD_A, client, ledger, "t", ceiling_usd=Decimal("0.001"))
    assert client.calls == []
    assert ledger.entries() == []


def test_ceiling_stops_the_retry_after_the_first_call_is_recorded(reader, junit, ledger):
    client = FakeClient(report(BAD_QUOTE), report(LOG_EVIDENCE))
    with pytest.raises(BudgetExceededError):
        run_analysis(reader, junit, METHOD_A, client, ledger, "t", ceiling_usd=Decimal("0.04"))
    assert len(client.calls) == 1
    assert len(ledger.entries()) == 1


def test_schema_sent_to_the_model_has_only_supported_keywords():
    schema = report_schema()
    text = json.dumps(schema)
    for keyword in ("minLength", "minimum", "minItems", '"default"', '"title"'):
        assert keyword not in text

    def objects(node):
        if isinstance(node, dict):
            if "properties" in node:
                yield node
            for value in node.values():
                yield from objects(value)
        elif isinstance(node, list):
            for value in node:
                yield from objects(value)

    found = list(objects(schema))
    assert len(found) >= 6
    for node in found:
        assert node["additionalProperties"] is False
        assert node["required"] == list(node["properties"])


def test_prompt_hash_is_stable():
    assert prompt_sha256() == prompt_sha256()
    assert len(prompt_sha256()) == 64
