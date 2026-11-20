import json
from decimal import Decimal

import pytest

from ci_failure_analyzer.analysis import prompt
from ci_failure_analyzer.analysis.agent import (
    KIND_EXPLORE,
    KIND_REPORT,
    LIMIT_COST,
    LIMIT_MODEL_CALLS,
    LIMIT_TOOL_CALLS,
    MAX_MODEL_CALLS,
    RESERVED_MODEL_CALLS,
    run_agent,
)
from ci_failure_analyzer.analysis.budget import BudgetConfig, BudgetExceededError, ModelPrice, UsageLedger
from ci_failure_analyzer.analysis.context import METHOD_A, METHOD_C, build_context
from ci_failure_analyzer.analysis.runner import (
    STATUS_CHECK_FAILED,
    STATUS_OK,
    STATUS_REFUSED,
    STATUS_TRUNCATED,
    ModelReply,
    ToolUse,
)
from ci_failure_analyzer.analysis.tools import MAX_TOOL_CALLS, TOOL_DEFINITIONS
from ci_failure_analyzer.evaluation.grading import score_run
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

LOG_EVIDENCE = {"id": "E1", "source": "log", "path": "job.log", "start_line": 2, "end_line": 2, "quote": "KeyError: 'x'"}
CODE_EVIDENCE = {"id": "E1", "source": "code", "path": "src/app.py", "start_line": 2, "end_line": 2, "quote": "return d['x']"}
READ_APP = ("read_file", {"path": "src/app.py"})
# One fake reply costs 1000 * 4 / 1M + 500 * 20 / 1M dollars.
REPLY_COST = Decimal("0.014")


def report(evidence):
    return {
        "schema_version": "1",
        "conclusion": "cause_candidate",
        "reason_code": None,
        "observed_facts": [{"statement": "test_get fails", "evidence_ids": [evidence["id"]]}],
        "cause_candidates": [
            {
                "summary": "missing key",
                "reasoning": "the code reads a key that is not there",
                "confidence": "medium",
                "location": None,
                "evidence_ids": [evidence["id"]],
            }
        ],
        "evidence": [evidence],
        "verification_steps": [{"description": "run the test", "command": None}],
        "limitations": [],
    }


def tools(*uses):
    """A reply that asks for the given (name, input) tool calls."""
    return ("tools", uses)


class FakeClient:
    """Returns the scripted replies in order; `forever` is repeated once they run out."""

    def __init__(self, *replies, forever=None):
        self.replies = list(replies)
        self.forever = forever
        self.calls = []

    def complete(self, **kwargs):
        self.calls.append(kwargs)
        reply = self.replies.pop(0) if self.replies else self.forever
        if isinstance(reply, ModelReply):
            return reply
        if isinstance(reply, tuple):
            number = len(self.calls)
            uses = tuple(ToolUse(f"tu_{number}_{i}", name, arguments) for i, (name, arguments) in enumerate(reply[1], 1))
            content = [{"type": "tool_use", "id": u.id, "name": u.name, "input": u.input} for u in uses]
            return ModelReply(
                text="", content=content, stop_reason="tool_use", input_tokens=1000, output_tokens=500, tool_uses=uses
            )
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


def last_text(call):
    """The text block that ends the last user message of a model call."""
    block = call["messages"][-1]["content"][-1]
    assert block["type"] == "text"
    return block["text"]


def tool_results(call):
    return [b for b in call["messages"][-1]["content"] if b["type"] == "tool_result"]


def test_reads_code_with_a_tool_then_reports(reader, junit, ledger):
    client = FakeClient(tools(READ_APP), report(CODE_EVIDENCE))
    result = run_agent(reader, junit, client, ledger, "t")
    assert result.status == STATUS_OK
    assert result.limit_reached is None
    assert [c.kind for c in result.calls] == [KIND_EXPLORE, KIND_REPORT]
    assert result.report.evidence[0].path == "src/app.py"
    assert result.seen_files == {"src/app.py": [[1, 2]]}
    assert result.session.calls[0]["name"] == "read_file"

    first, second = client.calls
    assert first["system"] == prompt.AGENT_SYSTEM_PROMPT
    assert first["messages"] == [{"role": "user", "content": result.context.text}]
    assert first["tools"] == second["tools"] == TOOL_DEFINITIONS
    assert first["tool_choice"] is None and second["tool_choice"] is None
    assert [m["role"] for m in second["messages"]] == ["user", "assistant", "user"]
    (shown,) = tool_results(second)
    assert shown["tool_use_id"] == "tu_1_1"
    assert shown["is_error"] is False
    assert "    2|     return d['x']" in shown["content"]
    assert last_text(second) == prompt.AGENT_TOOL_STATUS_TEMPLATE.format(
        calls_left=MAX_TOOL_CALLS - 1, turns_left=MAX_MODEL_CALLS - RESERVED_MODEL_CALLS - 1
    )


def test_starts_from_the_input_of_method_a(reader, junit, ledger):
    result = run_agent(reader, junit, FakeClient(report(LOG_EVIDENCE)), ledger, "t")
    assert result.context.method == METHOD_C
    assert result.context.text == build_context(reader, junit, METHOD_A).text
    assert "## Code files" not in result.context.text


def test_a_report_without_any_tool_call_is_accepted(reader, junit, ledger):
    client = FakeClient(report(LOG_EVIDENCE))
    result = run_agent(reader, junit, client, ledger, "t")
    assert result.status == STATUS_OK
    assert len(client.calls) == 1
    assert result.session.calls == []
    assert result.seen_files == {}


def test_every_model_call_is_recorded_in_the_ledger(reader, junit, ledger):
    result = run_agent(reader, junit, FakeClient(tools(READ_APP), tools(READ_APP), report(CODE_EVIDENCE)), ledger, "t")
    assert [e["purpose"] for e in ledger.entries()] == ["t#1", "t#2", "t#3"]
    assert ledger.total_usd() == result.cost_usd == 3 * REPLY_COST


def test_citing_code_no_tool_showed_is_sent_back_once_without_tools(reader, junit, ledger):
    client = FakeClient(report(CODE_EVIDENCE), report(LOG_EVIDENCE))
    result = run_agent(reader, junit, client, ledger, "t")
    assert result.status == STATUS_OK
    assert "not_in_context" in result.calls[0].citation_problems[0]
    correction = client.calls[1]
    assert correction["tool_choice"] == {"type": "none"}
    assert correction["tools"] == TOOL_DEFINITIONS
    assert "was not read with a tool" in correction["messages"][-1]["content"]
    assert result.limit_reached is None


def test_citing_a_line_outside_what_a_tool_showed_fails(reader, junit, ledger):
    read_first_line = ("read_file", {"path": "src/app.py", "start_line": 1, "end_line": 1})
    client = FakeClient(tools(read_first_line), report(CODE_EVIDENCE), report(CODE_EVIDENCE))
    result = run_agent(reader, junit, client, ledger, "t")
    assert result.status == STATUS_CHECK_FAILED
    assert "lines 2 were not shown" in result.calls[1].citation_problems[0]


def test_a_line_found_by_search_can_be_cited(reader, junit, ledger):
    client = FakeClient(tools(("search_code", {"query": "return d"})), report(CODE_EVIDENCE))
    assert run_agent(reader, junit, client, ledger, "t").status == STATUS_OK


def test_second_failed_report_ends_the_run(reader, junit, ledger):
    client = FakeClient(report(CODE_EVIDENCE), report(CODE_EVIDENCE), report(LOG_EVIDENCE))
    result = run_agent(reader, junit, client, ledger, "t")
    assert result.status == STATUS_CHECK_FAILED
    assert len(client.calls) == 2
    assert result.report is not None


def test_a_bad_tool_call_gets_an_error_result_and_the_run_goes_on(reader, junit, ledger):
    client = FakeClient(tools(("read_file", {"path": "../labels/case-001.json"})), report(LOG_EVIDENCE))
    result = run_agent(reader, junit, client, ledger, "t")
    assert result.status == STATUS_OK
    (shown,) = tool_results(client.calls[1])
    assert shown["is_error"] is True
    assert "not in the snapshot" in shown["content"]
    assert result.session.calls[0]["is_error"] is True
    assert result.seen_files == {}


def test_tool_call_limit_refuses_further_calls_and_asks_for_the_report(reader, junit, ledger):
    client = FakeClient(tools(READ_APP, READ_APP, READ_APP), report(CODE_EVIDENCE))
    result = run_agent(reader, junit, client, ledger, "t", max_tool_calls=2)
    assert result.status == STATUS_OK
    assert result.limit_reached == LIMIT_TOOL_CALLS
    assert len(result.session.calls) == 2
    assert result.session.refused_calls == 1
    final = client.calls[1]
    assert [r["is_error"] for r in tool_results(final)] == [False, False, True]
    assert final["tool_choice"] == {"type": "none"}
    assert "the tool call limit is reached" in last_text(final)
    assert "Do not call tools" in last_text(final)


def test_model_call_limit_keeps_two_calls_for_the_report_and_its_correction(reader, junit, ledger):
    client = FakeClient(forever=tools(("list_files", {})))
    client.replies = [tools(("list_files", {})), tools(("list_files", {})), report(CODE_EVIDENCE), report(LOG_EVIDENCE)]
    result = run_agent(reader, junit, client, ledger, "t", max_model_calls=4)
    assert result.status == STATUS_OK
    assert result.limit_reached == LIMIT_MODEL_CALLS
    assert [c.kind for c in result.calls] == [KIND_EXPLORE, KIND_EXPLORE, KIND_REPORT, KIND_REPORT]
    assert [c["tool_choice"] for c in client.calls] == [None, None, {"type": "none"}, {"type": "none"}]
    assert last_text(client.calls[1]).endswith("turns left in which you can call tools: 1]")
    assert "the turn limit is reached" in last_text(client.calls[2])


def test_default_limits_bound_a_model_that_never_stops_exploring(reader, junit, ledger):
    # The fake keeps asking for tools even when told not to; a real reply to a
    # request with tools switched off cannot. The run must still end.
    client = FakeClient(forever=tools(("list_files", {})))
    result = run_agent(reader, junit, client, ledger, "t")
    assert len(client.calls) == MAX_MODEL_CALLS - RESERVED_MODEL_CALLS + 1
    assert result.limit_reached == LIMIT_MODEL_CALLS
    assert result.status == STATUS_TRUNCATED
    assert result.report is None
    assert len(result.session.calls) == MAX_MODEL_CALLS - RESERVED_MODEL_CALLS


def test_cost_limit_asks_for_the_report_while_two_calls_still_fit(reader, junit, ledger):
    client = FakeClient(tools(READ_APP), report(CODE_EVIDENCE))
    result = run_agent(reader, junit, client, ledger, "t", max_run_cost_usd=Decimal("0.10"))
    assert result.status == STATUS_OK
    assert result.limit_reached == LIMIT_COST
    assert client.calls[1]["tool_choice"] == {"type": "none"}
    assert "the cost limit of this analysis is reached" in last_text(client.calls[1])
    assert result.cost_usd <= Decimal("0.10")


def test_no_correction_is_requested_when_it_would_pass_the_cost_limit(reader, junit, ledger):
    client = FakeClient(report(CODE_EVIDENCE), report(LOG_EVIDENCE))
    result = run_agent(reader, junit, client, ledger, "t", max_run_cost_usd=Decimal("0.05"))
    assert result.status == STATUS_CHECK_FAILED
    assert result.limit_reached == LIMIT_COST
    assert len(client.calls) == 1


@pytest.mark.parametrize(("stop_reason", "status"), [("max_tokens", STATUS_TRUNCATED), ("refusal", STATUS_REFUSED)])
def test_cut_off_or_refused_reply_is_not_retried(reader, junit, ledger, stop_reason, status):
    reply = ModelReply(text="{", content=[], stop_reason=stop_reason, input_tokens=1000, output_tokens=1000)
    client = FakeClient(tools(READ_APP), reply)
    result = run_agent(reader, junit, client, ledger, "t")
    assert result.status == status
    assert len(client.calls) == 2
    assert len(ledger.entries()) == 2


def test_no_call_is_made_when_the_spending_limit_could_be_exceeded(reader, junit, ledger):
    client = FakeClient(report(LOG_EVIDENCE))
    with pytest.raises(BudgetExceededError):
        run_agent(reader, junit, client, ledger, "t", ceiling_usd=Decimal("0.001"))
    assert client.calls == []
    assert ledger.entries() == []


def test_spending_ceiling_stops_the_run_between_calls(reader, junit, ledger):
    client = FakeClient(tools(READ_APP), report(CODE_EVIDENCE))
    with pytest.raises(BudgetExceededError):
        run_agent(reader, junit, client, ledger, "t", ceiling_usd=Decimal("0.04"))
    assert len(client.calls) == 1
    assert len(ledger.entries()) == 1


def test_model_call_limit_must_leave_room_to_explore(reader, junit, ledger):
    with pytest.raises(ValueError):
        run_agent(reader, junit, FakeClient(), ledger, "t", max_model_calls=RESERVED_MODEL_CALLS)


def test_agent_prompt_changes_only_the_code_sentences_and_adds_the_tools_section():
    base, agent = prompt.SYSTEM_PROMPT, prompt.AGENT_SYSTEM_PROMPT
    assert '"Code files"' in base and '"Code files"' not in agent
    assert "## Tools" in agent and "## Tools" not in base
    assert f"at most {MAX_TOOL_CALLS} tool calls" in agent
    for name in ("list_files", "read_file", "search_code"):
        assert f"`{name}`" in agent
    # Everything before the first replaced sentence and the whole Language section are untouched.
    assert agent.startswith(base[: base.index('- "Code files"')])
    assert agent.endswith(base[base.index("## Language") :])
    assert agent.index("## Tools") < agent.index("## Language")


def test_prompt_identity_differs_by_method_and_the_ab_prompt_is_unchanged():
    # The A/B runs of 2026-11-18 to 2026-11-20 were made with this prompt.
    assert prompt.prompt_sha256().startswith("1d7b7066cb90")
    assert prompt.prompt_identity("A") == prompt.prompt_identity("B") == (prompt.PROMPT_VERSION, prompt.prompt_sha256())
    assert prompt.prompt_identity("C") == (prompt.AGENT_PROMPT_VERSION, prompt.agent_prompt_sha256())
    assert prompt.agent_prompt_sha256() != prompt.prompt_sha256()


LABEL = {"case_id": "case-x", "acceptable_conclusions": ["cause_candidate"], "root_cause": {"file": None}}


def attempt(kind, stop_reason="end_turn", citation_problems=()):
    return {"kind": kind, "stop_reason": stop_reason, "format_problems": [], "citation_problems": list(citation_problems)}


@pytest.mark.parametrize(
    ("attempts", "expected"),
    [
        ([attempt("explore", "tool_use"), attempt("report")], True),
        ([attempt("explore", "tool_use"), attempt("report", citation_problems=["x"]), attempt("report")], False),
        ([attempt("explore", "tool_use")], False),
        ([attempt("report", "max_tokens")], False),
    ],
)
def test_first_reply_check_of_a_method_c_run_looks_at_its_first_report(attempts, expected):
    manifest = {"run_id": "r", "method": "C", "attempts": attempts}
    assert score_run(manifest, report(LOG_EVIDENCE), LABEL, None, None).first_reply_passed is expected
