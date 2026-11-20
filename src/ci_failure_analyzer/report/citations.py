"""Check that every piece of evidence in a report exists in the input bundle.

This checks existence only: the file, the line range and the quoted text.
Whether the evidence supports the claim is judged by a person during evaluation.
"""

from __future__ import annotations

from collections.abc import Collection, Mapping
from dataclasses import dataclass

from ci_failure_analyzer.inputs.reader import BundleReader
from ci_failure_analyzer.report.schema import EvidenceSource, Report

FILE_NOT_FOUND = "file_not_found"
NOT_IN_CONTEXT = "not_in_context"
LINE_OUT_OF_RANGE = "line_out_of_range"
QUOTE_MISMATCH = "quote_mismatch"


@dataclass(frozen=True)
class CitationProblem:
    evidence_id: str
    code: str
    detail: str


def _ranges(numbers: list[int]) -> str:
    """Sorted line numbers as ranges, e.g. `3-5, 9`."""
    out: list[str] = []
    start = previous = numbers[0]
    for number in [*numbers[1:], None]:
        if number is not None and number == previous + 1:
            previous = number
            continue
        out.append(str(start) if start == previous else f"{start}-{previous}")
        if number is not None:
            start = previous = number
    return ", ".join(out)


def normalize(text: str) -> str:
    """Collapse whitespace so indentation and line wrapping do not affect matching."""
    return " ".join(text.split())


def check_citations(
    report: Report,
    reader: BundleReader,
    provided_code_paths: Collection[str] | None = None,
    seen_code_lines: Mapping[str, Collection[int]] | None = None,
) -> list[CitationProblem]:
    """Return one problem per broken citation; an empty list means all exist.

    `provided_code_paths` is the set of code files the analysis was given. Code
    evidence outside it is reported even when the file exists in the snapshot,
    because the analysis could not have read it. None skips that check.

    `seen_code_lines` is for an analysis that reads code through tools: per
    file, the line numbers a tool result showed. Every cited code line must be
    among them. It replaces the `provided_code_paths` check when given.
    """
    problems: list[CitationProblem] = []
    for evidence in report.evidence:
        if evidence.source is EvidenceSource.CODE and seen_code_lines is not None:
            # A file or line that does not exist is reported as such below.
            existing = reader.lines(evidence.path)
            seen = seen_code_lines.get(evidence.path, ())
            unseen = [n for n in range(evidence.start_line, evidence.end_line + 1) if n not in seen]
            if unseen and existing is not None and evidence.end_line <= len(existing):
                what = "was not read with a tool" if not seen else f"lines {_ranges(unseen)} were not shown by a tool"
                problems.append(CitationProblem(evidence.id, NOT_IN_CONTEXT, f"{evidence.path}: {what}"))
                continue
        elif (
            evidence.source is EvidenceSource.CODE
            and provided_code_paths is not None
            and evidence.path not in provided_code_paths
        ):
            problems.append(
                CitationProblem(evidence.id, NOT_IN_CONTEXT, f"{evidence.path} was not provided to the analysis")
            )
            continue
        lines = reader.lines(evidence.path)
        if lines is None:
            problems.append(CitationProblem(evidence.id, FILE_NOT_FOUND, f"{evidence.path} is not in the bundle"))
            continue
        if evidence.end_line > len(lines):
            problems.append(
                CitationProblem(
                    evidence.id,
                    LINE_OUT_OF_RANGE,
                    f"{evidence.path} has {len(lines)} lines, cited {evidence.start_line}-{evidence.end_line}",
                )
            )
            continue
        cited = normalize("\n".join(lines[evidence.start_line - 1 : evidence.end_line]))
        if normalize(evidence.quote) not in cited:
            problems.append(
                CitationProblem(
                    evidence.id,
                    QUOTE_MISMATCH,
                    f"quote not found in {evidence.path}:{evidence.start_line}-{evidence.end_line}",
                )
            )
    return problems
