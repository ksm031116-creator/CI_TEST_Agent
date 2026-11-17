"""Read-only access to the text of a stored input bundle.

Line numbers used in analysis contexts and in report citations both come from
`BundleReader.lines`, so a cited line always means the same line.
"""

from __future__ import annotations

import json
import re
import tarfile
from functools import cached_property
from pathlib import Path

from ci_failure_analyzer.inputs.bundle import CODE_TAR, JOB_LOG, JUNIT_XML, RUN_JSON

PYTHON_VERSION = "reports/python_version.txt"

# Files larger than this are listed but not readable as text.
MAX_CODE_FILE_BYTES = 1_000_000


_TIMESTAMP = re.compile(r"^\d{4}-\d{2}-\d{2}T[\d:.]+Z ?")
# Colour codes arrive either as a real ESC byte or, from `gh`, spelled as `^[`.
_ANSI = re.compile(r"(?:\x1b|\^\[)\[[0-9;]*m")


def clean_log_line(raw: str) -> tuple[str, str]:
    """Split a `gh run view --log` line into (step name, content).

    The job and step columns, the BOM, the timestamp and ANSI colour codes are
    removed. One raw line always gives one cleaned line, so numbering is unchanged.
    """
    parts = raw.split("\t", 2)
    step, content = (parts[1], parts[2]) if len(parts) == 3 else ("", raw)
    content = _TIMESTAMP.sub("", content.lstrip("\ufeff"))
    return step, _ANSI.sub("", content)


def split_lines(text: str) -> list[str]:
    """Split on `\\n` only, so numbering does not depend on other separators."""
    lines = [line.rstrip("\r") for line in text.split("\n")]
    if lines and lines[-1] == "":
        lines.pop()
    return lines


class BundleReader:
    def __init__(self, bundle_dir: Path) -> None:
        self.bundle_dir = bundle_dir

    @cached_property
    def run(self) -> dict:
        return json.loads((self.bundle_dir / RUN_JSON).read_text(encoding="utf-8"))

    @cached_property
    def python_version(self) -> str | None:
        path = self.bundle_dir / PYTHON_VERSION
        return path.read_text(encoding="utf-8").strip() if path.exists() else None

    @cached_property
    def _code(self) -> dict[str, bytes | None]:
        """Regular files in the code snapshot. The archive is read, never extracted."""
        tar_path = self.bundle_dir / CODE_TAR
        files: dict[str, bytes | None] = {}
        if not tar_path.exists():
            return files
        with tarfile.open(tar_path) as tar:
            for member in tar:
                if not member.isfile():
                    continue
                if member.size > MAX_CODE_FILE_BYTES:
                    files[member.name] = None
                    continue
                extracted = tar.extractfile(member)
                files[member.name] = extracted.read() if extracted else None
        return files

    @cached_property
    def code_paths(self) -> tuple[str, ...]:
        return tuple(sorted(self._code))

    @cached_property
    def _log(self) -> list[tuple[str, str]] | None:
        path = self.bundle_dir / JOB_LOG
        if not path.exists():
            return None
        return [clean_log_line(line) for line in split_lines(path.read_text(encoding="utf-8", errors="replace"))]

    @cached_property
    def log_steps(self) -> list[str]:
        """Step name of every log line, in the same order as `lines("job.log")`."""
        return [step for step, _ in self._log or []]

    def lines(self, path: str) -> list[str] | None:
        """Lines of `job.log`, `reports/junit.xml` or a file in the code snapshot.

        Log lines are returned cleaned (see `clean_log_line`). Returns None when
        the bundle has no such file or it is not readable text.
        """
        if path == JOB_LOG:
            return None if self._log is None else [content for _, content in self._log]
        if path == JUNIT_XML:
            file_path = self.bundle_dir / path
            if not file_path.exists():
                return None
            data: bytes | None = file_path.read_bytes()
        else:
            data = self._code.get(path)
        if data is None or b"\x00" in data:
            return None
        return split_lines(data.decode("utf-8", errors="replace"))
