"""Run analysis method C (the exploring agent) on one input bundle. See docs/agent_design.md.

The model starts from method A's input and reads code through the lookup tools
of `analysis/tools.py`. A run is a loop of model calls: a reply either asks for
tool calls, which are answered from the bundle, or is the report. The loop is
bounded three ways, all enforced here and not left to the model:

- tool calls, by `ToolSession`;
- model calls: the last two are kept back, one to write the report without
  tools and one to correct it, so a run that explores to the end still reports;
- cost: once the next call and a report call after it would not fit, the next
  call must be the report.

Every model call is reserved in the usage ledger before it is sent and recorded
after it returns, like methods A and B.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from decimal import Decimal

from ci_failure_analyzer.analysis.budget import BudgetConfig, UsageLedger, cost_usd, estimate_input_tokens
from ci_failure_analyzer.analysis.context import METHOD_C, AnalysisContext, build_context
from ci_failure_analyzer.analysis.prompt import (
    AGENT_FINAL_TEMPLATE,
    AGENT_LIMIT_REASONS,
    AGENT_SYSTEM_PROMPT,
    AGENT_TOOL_STATUS_TEMPLATE,
    report_schema,
    retry_message,
)
from ci_failure_analyzer.analysis.runner import (
    STATUS_CHECK_FAILED,
    STATUS_OK,
    STATUS_REFUSED,
    STATUS_TRUNCATED,
    ModelClient,
    ModelReply,
    check_reply,
)
from ci_failure_analyzer.analysis.tools import MAX_TOOL_CALLS, TOOL_DEFINITIONS, ToolSession
from ci_failure_analyzer.inputs.junit import JUnitReport
from ci_failure_analyzer.inputs.reader import BundleReader
from ci_failure_analyzer.report.schema import Report

# Limits per run, fixed before any method C run. docs/agent_design.md explains each.
MAX_MODEL_CALLS = 8
MAX_RUN_COST_USD = Decimal("0.60")
# Model calls kept back from exploring: the report without tools, and its correction.
RESERVED_MODEL_CALLS = 2
# Output tokens assumed for the next call when checking the cost limit. A report
# with its reasoning took about 2,000 tokens in the method A and B runs.
OUTPUT_TOKEN_ALLOWANCE = 3000

KIND_EXPLORE = "explore"
KIND_REPORT = "report"

LIMIT_TOOL_CALLS = "tool_calls"
LIMIT_MODEL_CALLS = "model_calls"
LIMIT_COST = "cost"

_NO_TOOLS = {"type": "none"}


@dataclass(frozen=True)
class AgentCall:
    """One model call of a run."""

    # KIND_EXPLORE: the reply asked for tool calls. KIND_REPORT: anything else,
    # which is checked as a report (or is a cut-off or refused reply).
    kind: str
    reply: ModelReply
    cost_usd: Decimal
    tools_allowed: bool
    format_problems: tuple[str, ...] = ()
    citation_problems: tuple[str, ...] = ()

    @property
    def passed(self) -> bool:
        return (
            self.kind == KIND_REPORT
            and self.reply.stop_reason == "end_turn"
            and not self.format_problems
            and not self.citation_problems
        )


@dataclass(frozen=True)
class AgentResult:
    status: str
    context: AnalysisContext
    calls: tuple[AgentCall, ...]
    # The report of the last reply that parsed, whether or not its citations passed.
    report: Report | None
    session: ToolSession
    # The limit that ended the exploring, or None when the model stopped by itself.
    limit_reached: str | None

    @property
    def cost_usd(self) -> Decimal:
        return sum((c.cost_usd for c in self.calls), Decimal("0"))

    @property
    def seen_files(self) -> dict[str, list[list[int]]]:
        """Per file, the line ranges tool results showed, as [first, last] pairs."""
        return {path: _ranges(sorted(self.session.seen_lines(path))) for path in self.session.seen_paths}


def _ranges(numbers: list[int]) -> list[list[int]]:
    out: list[list[int]] = []
    for number in numbers:
        if out and number == out[-1][1] + 1:
            out[-1][1] = number
        else:
            out.append([number, number])
    return out


def _estimate_next_cost(config: BudgetConfig, last: ModelReply, added_text: str) -> Decimal:
    """Expected cost of the next call: everything sent so far, the last reply and the new text."""
    input_tokens = (
        last.input_tokens
        + last.cache_write_tokens
        + last.cache_read_tokens
        + last.output_tokens
        + estimate_input_tokens(added_text)
    )
    return cost_usd(config.price(config.model), input_tokens, OUTPUT_TOKEN_ALLOWANCE)


def run_agent(
    reader: BundleReader,
    junit: JUnitReport,
    client: ModelClient,
    ledger: UsageLedger,
    purpose: str,
    ceiling_usd: Decimal | None = None,
    *,
    max_model_calls: int = MAX_MODEL_CALLS,
    max_tool_calls: int = MAX_TOOL_CALLS,
    max_run_cost_usd: Decimal = MAX_RUN_COST_USD,
) -> AgentResult:
    """Analyze one bundle with method C. Raises `BudgetExceededError` before a call that may not fit."""
    if max_model_calls <= RESERVED_MODEL_CALLS:
        raise ValueError(f"max_model_calls must be more than {RESERVED_MODEL_CALLS}")
    config: BudgetConfig = ledger.config
    context = build_context(reader, junit, METHOD_C)
    session = ToolSession(reader, max_tool_calls)
    schema = report_schema()
    messages: list[dict] = [{"role": "user", "content": context.text}]
    sent_text = AGENT_SYSTEM_PROMPT + json.dumps(TOOL_DEFINITIONS) + context.text
    calls: list[AgentCall] = []
    report: Report | None = None
    status = STATUS_CHECK_FAILED
    limit_reached: str | None = None
    tools_allowed = True
    corrected = False

    def spent() -> Decimal:
        return sum((c.cost_usd for c in calls), Decimal("0"))

    while True:
        ledger.reserve(config.model, sent_text, ceiling_usd=ceiling_usd)
        reply = client.complete(
            model=config.model,
            effort=config.effort,
            max_tokens=config.max_output_tokens,
            system=AGENT_SYSTEM_PROMPT,
            messages=messages,
            schema=schema,
            tools=TOOL_DEFINITIONS,
            # The tool list stays the same for the whole run; only the choice changes.
            tool_choice=None if tools_allowed else _NO_TOOLS,
        )
        cost = ledger.record(
            config.model,
            f"{purpose}#{len(calls) + 1}",
            reply.input_tokens,
            reply.output_tokens,
            reply.cache_write_tokens,
            reply.cache_read_tokens,
        )
        # The reply's reasoning is resent with it, so count the whole output as input text.
        sent_text += "x" * (reply.output_tokens * 2)

        if reply.stop_reason == "tool_use" and reply.tool_uses and tools_allowed:
            calls.append(AgentCall(KIND_EXPLORE, reply, cost, tools_allowed))
            results = [(use, session.call(use.name, use.input)) for use in reply.tool_uses]
            result_text = "".join(result.text for _, result in results)
            if session.calls_left <= 0:
                limit_reached = LIMIT_TOOL_CALLS
            elif len(calls) >= max_model_calls - RESERVED_MODEL_CALLS:
                limit_reached = LIMIT_MODEL_CALLS
            elif spent() + 2 * _estimate_next_cost(config, reply, result_text) > max_run_cost_usd:
                # Room is needed for the next call and for a report call after it.
                limit_reached = LIMIT_COST
            if limit_reached is not None:
                tools_allowed = False
                note = AGENT_FINAL_TEMPLATE.format(reason=AGENT_LIMIT_REASONS[limit_reached])
            else:
                note = AGENT_TOOL_STATUS_TEMPLATE.format(
                    calls_left=session.calls_left,
                    turns_left=max_model_calls - RESERVED_MODEL_CALLS - len(calls),
                )
            content: list[dict] = [
                {"type": "tool_result", "tool_use_id": use.id, "content": result.text, "is_error": result.is_error}
                for use, result in results
            ]
            content.append({"type": "text", "text": note})
            messages = [*messages, {"role": "assistant", "content": reply.content}, {"role": "user", "content": content}]
            sent_text += result_text + note
            continue

        if reply.stop_reason != "end_turn":
            # A cut-off or refused reply is not a report; asking again with the
            # same input and limit would only repeat it. A tool call made after
            # tools were switched off is treated the same way.
            calls.append(AgentCall(KIND_REPORT, reply, cost, tools_allowed))
            status = STATUS_REFUSED if reply.stop_reason == "refusal" else STATUS_TRUNCATED
            break

        seen = {path: session.seen_lines(path) for path in session.seen_paths}
        parsed, format_problems, citation_problems = check_reply(reply, reader, (), seen)
        report = parsed or report
        call = AgentCall(KIND_REPORT, reply, cost, tools_allowed, tuple(format_problems), tuple(citation_problems))
        calls.append(call)
        if call.passed:
            status = STATUS_OK
            break
        if corrected or len(calls) >= max_model_calls:
            break
        correction = retry_message(format_problems + citation_problems)
        if spent() + _estimate_next_cost(config, reply, correction) > max_run_cost_usd:
            limit_reached = limit_reached or LIMIT_COST
            break
        corrected = True
        tools_allowed = False
        messages = [*messages, {"role": "assistant", "content": reply.content}, {"role": "user", "content": correction}]
        sent_text += correction

    return AgentResult(
        status=status,
        context=context,
        calls=tuple(calls),
        report=report,
        session=session,
        limit_reached=limit_reached,
    )
