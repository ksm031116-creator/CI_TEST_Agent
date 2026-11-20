"""Build the input text for analysis methods A and B. See docs/analysis_methods.md.

Method A gets run information and the job log. Method B gets the same plus
code files chosen by a fixed rule. Everything here is derived from the input
bundle alone; nothing reads evaluation labels.
"""

from __future__ import annotations

import posixpath
import re
from dataclasses import dataclass, field

from ci_failure_analyzer.inputs.bundle import JOB_LOG
from ci_failure_analyzer.inputs.junit import JUnitReport
from ci_failure_analyzer.inputs.reader import BundleReader

METHOD_A = "A"
METHOD_B = "B"
# Method C starts from method A's text and reads code through tools (docs/agent_design.md).
METHOD_C = "C"

# Resource limits, fixed before any evaluation run.
MAX_LOG_LINES = 1500
MAX_FILES = 10
MAX_FILE_LINES = 400

REASON_TEST_FILE = "failing_test_file"
REASON_TRACEBACK = "traceback"
REASON_CONFTEST = "conftest"

_TRACEBACK_PATH = re.compile(r"^(\S+\.py):\d+: ", re.MULTILINE)
_LIBRARY_MARKERS = ("/site-packages/", "/dist-packages/", "/lib/python")


@dataclass(frozen=True)
class SelectedFile:
    path: str
    reason: str


@dataclass(frozen=True)
class AnalysisContext:
    method: str
    text: str
    selected_files: tuple[SelectedFile, ...] = ()
    omitted_files: tuple[SelectedFile, ...] = ()
    log_lines_total: int = 0
    log_lines_included: int = 0
    truncated_files: tuple[str, ...] = field(default=())

    @property
    def provided_code_paths(self) -> tuple[str, ...]:
        return tuple(f.path for f in self.selected_files)


def _resolve(path: str, code_paths: tuple[str, ...]) -> str | None:
    """Map a path printed by pytest to a file in the snapshot, or None.

    pytest prints repository files relative to the repository root, so a
    relative path must equal a snapshot path. An absolute path matches the
    longest snapshot path that is its suffix, unless it points into an
    installed library, where a same-named repository file would be a false match.
    """
    path = posixpath.normpath(path.replace("\\", "/"))
    if not path.startswith("/"):
        return path if path in code_paths else None
    if any(marker in path for marker in _LIBRARY_MARKERS):
        return None
    matches = [p for p in code_paths if path.endswith("/" + p)]
    return max(matches, key=len) if matches else None


def select_files(reader: BundleReader, junit: JUnitReport) -> tuple[list[SelectedFile], list[SelectedFile]]:
    """Choose code files for method B. Returns (selected, omitted by the file limit).

    Order: files of the failing tests, then repository files in their
    tracebacks in order of first appearance, then `conftest.py` next to each
    failing test file.
    """
    code_paths = reader.code_paths
    candidates: list[SelectedFile] = []
    seen: set[str] = set()

    def add(path: str | None, reason: str) -> None:
        if path is not None and path not in seen:
            seen.add(path)
            candidates.append(SelectedFile(path, reason))

    test_files: list[str] = []
    for case in junit.failed:
        resolved = _resolve(case.node_id.split("::", 1)[0], code_paths)
        if resolved is not None and resolved not in test_files:
            test_files.append(resolved)
    for path in test_files:
        add(path, REASON_TEST_FILE)
    for case in junit.failed:
        for match in _TRACEBACK_PATH.finditer(case.details):
            add(_resolve(match.group(1), code_paths), REASON_TRACEBACK)
    for path in test_files:
        conftest = posixpath.join(posixpath.dirname(path), "conftest.py")
        add(conftest if conftest in code_paths else None, REASON_CONFTEST)

    return candidates[:MAX_FILES], candidates[MAX_FILES:]


def _numbered(lines: list[str], start: int = 1) -> list[str]:
    return [f"{number:>5}| {line}" for number, line in enumerate(lines, start)]


def _render_log(reader: BundleReader, failed_steps: set[str]) -> tuple[list[str], int, int]:
    """Numbered log lines grouped by step. Returns (text lines, total, included).

    A log within the limit is included whole. A longer one keeps only the
    failed steps, and of those the last MAX_LOG_LINES lines.
    """
    lines = reader.lines(JOB_LOG) or []
    steps = reader.log_steps
    keep = list(range(len(lines)))
    if len(lines) > MAX_LOG_LINES:
        keep = [i for i in keep if steps[i] in failed_steps][-MAX_LOG_LINES:]
    out: list[str] = []
    previous = -1
    current_step: str | None = None
    for index in keep:
        if index != previous + 1:
            out.append(f"       [{index - previous - 1} lines omitted]")
        if steps[index] != current_step:
            current_step = steps[index]
            marker = " (failed)" if current_step in failed_steps else ""
            out.append(f"--- step: {current_step}{marker} ---")
        out.append(f"{index + 1:>5}| {lines[index]}")
        previous = index
    if keep and previous != len(lines) - 1:
        out.append(f"       [{len(lines) - 1 - previous} lines omitted]")
    return out, len(lines), len(keep)


def _render_run(reader: BundleReader, junit: JUnitReport) -> tuple[list[str], set[str]]:
    run = reader.run
    job = (run.get("jobs") or [{}])[0]
    steps = job.get("steps") or []
    failed_steps = {s["name"] for s in steps if s.get("conclusion") == "failure"}
    out = [
        "## Run",
        f"workflow: {run.get('workflowName')}",
        f"event: {run.get('event')}",
        f"job: {job.get('name')} (conclusion: {job.get('conclusion', run.get('conclusion'))})",
        f"python: {reader.python_version or 'unknown'}",
        "steps:",
    ]
    out += [f"  {s.get('number')}. {s.get('name')}: {s.get('conclusion')}" for s in steps]
    out += ["", "## Failed tests (from JUnit XML)"]
    for case in junit.failed:
        out.append(f"- {case.node_id} [{case.outcome}] {case.message}")
    counts = ", ".join(f"{name}: {junit.count(name)}" for name in ("passed", "failed", "error", "skipped"))
    out.append(f"totals: {counts}")
    return out, failed_steps


def build_context(reader: BundleReader, junit: JUnitReport, method: str) -> AnalysisContext:
    if method not in (METHOD_A, METHOD_B, METHOD_C):
        raise ValueError(f"unknown method: {method}")
    out, failed_steps = _render_run(reader, junit)
    log_text, log_total, log_included = _render_log(reader, failed_steps)
    out += ["", f"## Job log ({JOB_LOG}, line numbers are citable)", *log_text]

    selected: list[SelectedFile] = []
    omitted: list[SelectedFile] = []
    truncated: list[str] = []
    if method == METHOD_B:
        selected, omitted = select_files(reader, junit)
        out += ["", "## Code files (line numbers are citable)"]
        for item in selected:
            lines = reader.lines(item.path) or []
            shown = lines[:MAX_FILE_LINES]
            out += ["", f"### {item.path} (selected by: {item.reason}; lines 1-{len(shown)} of {len(lines)})"]
            out += _numbered(shown)
            if len(shown) < len(lines):
                truncated.append(item.path)
                out.append(f"       [{len(lines) - len(shown)} lines omitted]")
        if omitted:
            out += ["", "Not shown because of the file limit: " + ", ".join(f.path for f in omitted)]

    return AnalysisContext(
        method=method,
        text="\n".join(out) + "\n",
        selected_files=tuple(selected),
        omitted_files=tuple(omitted),
        log_lines_total=log_total,
        log_lines_included=log_included,
        truncated_files=tuple(truncated),
    )
