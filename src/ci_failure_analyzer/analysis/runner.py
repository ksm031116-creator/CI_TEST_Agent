"""Run analysis method A or B on one input bundle.

One run is at most two model calls: the analysis, and one correction request if
the reply fails the format or citation check. Every call is reserved in the
usage ledger before it is sent and recorded after it returns.
"""

from __future__ import annotations

from collections.abc import Collection, Mapping
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any, Protocol

from ci_failure_analyzer.analysis.budget import BudgetConfig, UsageLedger
from ci_failure_analyzer.analysis.context import AnalysisContext, build_context
from ci_failure_analyzer.analysis.prompt import SYSTEM_PROMPT, report_schema, retry_message
from ci_failure_analyzer.inputs.junit import JUnitReport
from ci_failure_analyzer.inputs.reader import BundleReader
from ci_failure_analyzer.report.citations import check_citations
from ci_failure_analyzer.report.schema import Conclusion, Report, ReportFormatError, parse_report

MAX_ATTEMPTS = 2

STATUS_OK = "ok"
STATUS_CHECK_FAILED = "check_failed"
STATUS_TRUNCATED = "truncated"
STATUS_REFUSED = "refused"


@dataclass(frozen=True)
class ToolUse:
    """One tool call requested by the model."""

    id: str
    name: str
    input: Any


@dataclass(frozen=True)
class ModelReply:
    text: str
    # Reply content in the form the API accepts back as an assistant turn.
    content: list[Any]
    stop_reason: str | None
    input_tokens: int
    output_tokens: int
    cache_write_tokens: int = 0
    cache_read_tokens: int = 0
    request_id: str | None = None
    raw: dict = field(default_factory=dict)
    tool_uses: tuple[ToolUse, ...] = ()


class ModelClient(Protocol):
    def complete(
        self,
        *,
        model: str,
        effort: str,
        max_tokens: int,
        system: str,
        messages: list[dict],
        schema: dict,
        tools: list[dict] | None = None,
        tool_choice: dict | None = None,
    ) -> ModelReply: ...


class AnthropicClient:
    """`ModelClient` backed by the Anthropic API. Reads the key from the environment."""

    def __init__(self) -> None:
        import anthropic

        self._client = anthropic.Anthropic()

    def complete(
        self,
        *,
        model: str,
        effort: str,
        max_tokens: int,
        system: str,
        messages: list[dict],
        schema: dict,
        tools: list[dict] | None = None,
        tool_choice: dict | None = None,
    ) -> ModelReply:
        # Methods A and B send no tools; the request is then exactly what it was
        # before tools existed.
        extra: dict[str, Any] = {}
        if tools is not None:
            extra["tools"] = tools
        if tool_choice is not None:
            extra["tool_choice"] = tool_choice
        with self._client.messages.stream(
            model=model,
            max_tokens=max_tokens,
            system=system,
            messages=messages,
            output_config={"effort": effort, "format": {"type": "json_schema", "schema": schema}},
            **extra,
        ) as stream:
            message = stream.get_final_message()
            request_id = stream.request_id
        usage = message.usage
        return ModelReply(
            text="".join(block.text for block in message.content if block.type == "text"),
            content=list(message.content),
            stop_reason=message.stop_reason,
            input_tokens=usage.input_tokens,
            output_tokens=usage.output_tokens,
            cache_write_tokens=usage.cache_creation_input_tokens or 0,
            cache_read_tokens=usage.cache_read_input_tokens or 0,
            request_id=request_id,
            raw=message.to_dict(),
            tool_uses=tuple(ToolUse(b.id, b.name, b.input) for b in message.content if b.type == "tool_use"),
        )


@dataclass(frozen=True)
class Attempt:
    reply: ModelReply
    cost_usd: Decimal
    format_problems: tuple[str, ...] = ()
    citation_problems: tuple[str, ...] = ()

    @property
    def passed(self) -> bool:
        return (
            self.reply.stop_reason == "end_turn"
            and not self.format_problems
            and not self.citation_problems
        )


@dataclass(frozen=True)
class AnalysisResult:
    status: str
    context: AnalysisContext
    attempts: tuple[Attempt, ...]
    # The report of the last attempt that parsed, whether or not its citations passed.
    report: Report | None

    @property
    def cost_usd(self) -> Decimal:
        return sum((a.cost_usd for a in self.attempts), Decimal("0"))


def check_reply(
    reply: ModelReply,
    reader: BundleReader,
    provided_code_paths: Collection[str],
    seen_code_lines: Mapping[str, Collection[int]] | None = None,
) -> tuple[Report | None, list[str], list[str]]:
    """Format and citation check of one reply: (report if it parsed, format problems, citation problems)."""
    try:
        report = parse_report(reply.text)
    except ReportFormatError as exc:
        return None, exc.problems, []
    format_problems: list[str] = []
    if report.conclusion is Conclusion.OUT_OF_SCOPE:
        # Bundles outside the scope never reach the model; see inputs/validation.py.
        format_problems.append("conclusion: out_of_scope is not allowed here")
    citation_problems = [
        f"evidence {p.evidence_id}: {p.code}: {p.detail}"
        for p in check_citations(report, reader, provided_code_paths, seen_code_lines)
    ]
    return report, format_problems, citation_problems


def run_analysis(
    reader: BundleReader,
    junit: JUnitReport,
    method: str,
    client: ModelClient,
    ledger: UsageLedger,
    purpose: str,
    ceiling_usd: Decimal | None = None,
) -> AnalysisResult:
    """Analyze one bundle. Raises `BudgetExceededError` before a call that may not fit."""
    config: BudgetConfig = ledger.config
    context = build_context(reader, junit, method)
    schema = report_schema()
    messages: list[dict] = [{"role": "user", "content": context.text}]
    sent_text = SYSTEM_PROMPT + context.text
    attempts: list[Attempt] = []
    report: Report | None = None
    status = STATUS_CHECK_FAILED

    for number in range(1, MAX_ATTEMPTS + 1):
        ledger.reserve(config.model, sent_text, ceiling_usd=ceiling_usd)
        reply = client.complete(
            model=config.model,
            effort=config.effort,
            max_tokens=config.max_output_tokens,
            system=SYSTEM_PROMPT,
            messages=messages,
            schema=schema,
        )
        cost = ledger.record(
            config.model,
            f"{purpose}#{number}",
            reply.input_tokens,
            reply.output_tokens,
            reply.cache_write_tokens,
            reply.cache_read_tokens,
        )
        if reply.stop_reason != "end_turn":
            # A cut-off or refused reply is not a report; asking again with the
            # same input and limit would only repeat it.
            attempts.append(Attempt(reply, cost))
            status = STATUS_REFUSED if reply.stop_reason == "refusal" else STATUS_TRUNCATED
            break
        parsed, format_problems, citation_problems = check_reply(reply, reader, context.provided_code_paths)
        report = parsed or report
        attempt = Attempt(reply, cost, tuple(format_problems), tuple(citation_problems))
        attempts.append(attempt)
        if attempt.passed:
            status = STATUS_OK
            break
        correction = retry_message(format_problems + citation_problems)
        messages = [*messages, {"role": "assistant", "content": reply.content}, {"role": "user", "content": correction}]
        # The reply's thinking is resent too, so count the whole output as input text.
        sent_text += "x" * (reply.output_tokens * 2) + correction

    return AnalysisResult(status=status, context=context, attempts=tuple(attempts), report=report)
