"""Lookup tools for analysis method C (the exploring agent). See docs/agent_design.md.

The tools answer only from one input bundle, through `BundleReader`: the code
snapshot taken at the commit the CI run checked out, the job log and the JUnit
XML. This module never touches the file system itself. A path is looked up as
an exact key among the snapshot's regular files, so `..`, absolute paths, drive
letters and links cannot reach anything outside the bundle: they are simply
names that are not in the snapshot.

A `ToolSession` enforces the per-run call limit and records which lines were
shown, so that the citation check can require evidence to come from lines the
analysis actually read.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ci_failure_analyzer.inputs.bundle import JOB_LOG, JUNIT_XML
from ci_failure_analyzer.inputs.reader import BundleReader

TOOL_LIST_FILES = "list_files"
TOOL_READ_FILE = "read_file"
TOOL_SEARCH_CODE = "search_code"

# Limits, fixed before any method C run. docs/agent_design.md explains each.
MAX_TOOL_CALLS = 12
MAX_READ_LINES = 200
MAX_SEARCH_MATCHES = 50
MAX_LISTED_FILES = 500
MAX_QUERY_CHARACTERS = 200
MAX_SHOWN_LINE_CHARACTERS = 300

# Bundle files outside the code snapshot that `read_file` may return.
_BUNDLE_TEXT_FILES = (JOB_LOG, JUNIT_XML)

TOOL_DEFINITIONS: list[dict[str, Any]] = [
    {
        "name": TOOL_LIST_FILES,
        "description": (
            "List the files of the repository snapshot taken at the commit the CI run checked out, "
            "with their line counts. Optionally only paths that start with `prefix`."
        ),
        "input_schema": {
            "type": "object",
            "properties": {"prefix": {"type": "string", "description": "Path prefix, for example `src/`."}},
            "additionalProperties": False,
        },
    },
    {
        "name": TOOL_READ_FILE,
        "description": (
            f"Read lines of one snapshot file, or of `{JOB_LOG}` or `{JUNIT_XML}`, with line numbers. "
            f"At most {MAX_READ_LINES} lines per call. The line numbers are the ones to cite as evidence."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Path exactly as `list_files` prints it."},
                "start_line": {"type": "integer", "description": "First line, 1-based. Default 1."},
                "end_line": {"type": "integer", "description": "Last line, inclusive. Default: as many as the limit allows."},
            },
            "required": ["path"],
            "additionalProperties": False,
        },
    },
    {
        "name": TOOL_SEARCH_CODE,
        "description": (
            "Find the lines of snapshot files that contain `query` as plain text (case-sensitive, not a pattern). "
            f"At most {MAX_SEARCH_MATCHES} matching lines. Optionally only files whose path starts with `prefix`."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Text to find, for example a function name."},
                "prefix": {"type": "string", "description": "Path prefix, for example `src/`."},
            },
            "required": ["query"],
            "additionalProperties": False,
        },
    },
]


@dataclass(frozen=True)
class ToolResult:
    text: str
    is_error: bool = False


class ToolSession:
    """The tools of one analysis run: call limit, call record and lines shown."""

    def __init__(self, reader: BundleReader, max_calls: int = MAX_TOOL_CALLS) -> None:
        self._reader = reader
        self._max_calls = max_calls
        self._seen: dict[str, set[int]] = {}
        self.calls: list[dict[str, Any]] = []
        self.refused_calls = 0

    @property
    def calls_left(self) -> int:
        return self._max_calls - len(self.calls)

    def seen_lines(self, path: str) -> frozenset[int]:
        """Line numbers of `path` that a tool result has shown in this session."""
        return frozenset(self._seen.get(path, ()))

    @property
    def seen_paths(self) -> tuple[str, ...]:
        return tuple(sorted(self._seen))

    def call(self, name: str, arguments: Any) -> ToolResult:
        """Run one tool call. Never raises: a bad call returns an error result.

        Every call counts towards the limit, including one that returns an
        error, so a run cannot loop on bad arguments for free. A call made after
        the limit is refused and counted separately.
        """
        if self.calls_left <= 0:
            self.refused_calls += 1
            return ToolResult("tool call limit reached; write the report from what you have read", is_error=True)
        if not isinstance(arguments, dict):
            result = ToolResult("arguments must be an object", is_error=True)
        elif name == TOOL_LIST_FILES:
            result = self._list_files(arguments)
        elif name == TOOL_READ_FILE:
            result = self._read_file(arguments)
        elif name == TOOL_SEARCH_CODE:
            result = self._search_code(arguments)
        else:
            result = ToolResult(f"unknown tool: {name!r}", is_error=True)
        self.calls.append(
            {
                "name": name,
                "arguments": arguments if isinstance(arguments, dict) else None,
                "is_error": result.is_error,
                "result_characters": len(result.text),
            }
        )
        return result

    def _code_paths(self, prefix: Any) -> list[str] | ToolResult:
        if prefix is None:
            prefix = ""
        if not isinstance(prefix, str):
            return ToolResult("prefix must be a string", is_error=True)
        prefix = prefix.replace("\\", "/").removeprefix("./")
        return [p for p in self._reader.code_paths if p.startswith(prefix)]

    def _list_files(self, arguments: dict) -> ToolResult:
        paths = self._code_paths(arguments.get("prefix"))
        if isinstance(paths, ToolResult):
            return paths
        if not paths:
            return ToolResult("no snapshot file has that prefix", is_error=True)
        out = []
        for path in paths[:MAX_LISTED_FILES]:
            lines = self._reader.lines(path)
            out.append(f"{path} ({'not readable as text' if lines is None else f'{len(lines)} lines'})")
        if len(paths) > MAX_LISTED_FILES:
            out.append(f"[{len(paths) - MAX_LISTED_FILES} more files not listed; narrow the prefix]")
        return ToolResult("\n".join(out))

    def _read_file(self, arguments: dict) -> ToolResult:
        path = arguments.get("path")
        if not isinstance(path, str) or not path:
            return ToolResult("path must be a non-empty string", is_error=True)
        path = path.replace("\\", "/").removeprefix("./")
        if path not in self._reader.code_paths and path not in _BUNDLE_TEXT_FILES:
            return ToolResult(f"{path} is not in the snapshot; use a path exactly as list_files prints it", is_error=True)
        lines = self._reader.lines(path)
        if lines is None:
            return ToolResult(f"{path} is not readable as text", is_error=True)
        start = arguments.get("start_line", 1)
        end = arguments.get("end_line")
        if not _is_line_number(start) or (end is not None and not _is_line_number(end)):
            return ToolResult("start_line and end_line must be integers of 1 or more", is_error=True)
        if end is not None and end < start:
            return ToolResult("end_line is before start_line", is_error=True)
        if start > max(len(lines), 1):
            return ToolResult(f"{path} has {len(lines)} lines", is_error=True)
        last = min(len(lines), start + MAX_READ_LINES - 1, end if end is not None else len(lines))
        out = [f"### {path} (lines {start}-{last} of {len(lines)})"]
        out += [f"{number:>5}| {lines[number - 1]}" for number in range(start, last + 1)]
        if end is not None and last < min(end, len(lines)) or end is None and last < len(lines):
            out.append(f"       [stopped at the {MAX_READ_LINES}-line limit; {len(lines) - last} more lines follow]")
        self._seen.setdefault(path, set()).update(range(start, last + 1))
        return ToolResult("\n".join(out))

    def _search_code(self, arguments: dict) -> ToolResult:
        query = arguments.get("query")
        if not isinstance(query, str) or not query.strip():
            return ToolResult("query must be a non-empty string", is_error=True)
        if len(query) > MAX_QUERY_CHARACTERS or "\n" in query:
            return ToolResult(f"query must be one line of at most {MAX_QUERY_CHARACTERS} characters", is_error=True)
        paths = self._code_paths(arguments.get("prefix"))
        if isinstance(paths, ToolResult):
            return paths
        out: list[str] = []
        total = 0
        for path in paths:
            for number, line in enumerate(self._reader.lines(path) or [], 1):
                if query not in line:
                    continue
                total += 1
                if len(out) < MAX_SEARCH_MATCHES:
                    shown = line if len(line) <= MAX_SHOWN_LINE_CHARACTERS else line[:MAX_SHOWN_LINE_CHARACTERS] + " [line cut]"
                    out.append(f"{path}:{number}| {shown}")
                    self._seen.setdefault(path, set()).add(number)
        if not out:
            return ToolResult(f"no line in {len(paths)} files contains that text")
        if total > len(out):
            out.append(f"[{total - len(out)} more matching lines not shown; narrow the query or the prefix]")
        return ToolResult("\n".join(out))


def _is_line_number(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value >= 1
