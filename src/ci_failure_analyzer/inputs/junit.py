"""Parse pytest JUnit XML into test results."""

from __future__ import annotations

import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path

FAILED_OUTCOMES = ("failed", "error")


class JUnitParseError(ValueError):
    """The file is not a JUnit XML report this service can read."""


@dataclass(frozen=True)
class TestCaseResult:
    __test__ = False  # not a pytest test class

    classname: str
    name: str
    outcome: str  # "passed" | "failed" | "error" | "skipped"
    message: str = ""
    details: str = ""

    @property
    def node_id(self) -> str:
        """Best-effort pytest node id, e.g. `tests/test_a.py::TestX::test_y`.

        JUnit XML only has a dotted classname. Segments starting with an
        uppercase letter are treated as test classes, the rest as the module path.
        """
        module_parts: list[str] = []
        class_parts: list[str] = []
        for part in self.classname.split("."):
            if class_parts or part[:1].isupper():
                class_parts.append(part)
            else:
                module_parts.append(part)
        path = "/".join(module_parts) + ".py" if module_parts else ""
        return "::".join([p for p in (path, *class_parts, self.name) if p])


@dataclass(frozen=True)
class JUnitReport:
    cases: tuple[TestCaseResult, ...]

    @property
    def failed(self) -> tuple[TestCaseResult, ...]:
        return tuple(c for c in self.cases if c.outcome in FAILED_OUTCOMES)

    def count(self, outcome: str) -> int:
        return sum(1 for c in self.cases if c.outcome == outcome)


def parse_junit(path: Path) -> JUnitReport:
    return parse_junit_bytes(path.read_bytes())


def parse_junit_bytes(data: bytes) -> JUnitReport:
    # CI output is untrusted: refuse DTDs so entity expansion cannot be used.
    if b"<!DOCTYPE" in data or b"<!ENTITY" in data:
        raise JUnitParseError("DTD or entity declarations are not allowed")
    try:
        root = ET.fromstring(data)
    except ET.ParseError as exc:
        raise JUnitParseError(f"invalid XML: {exc}") from exc
    if root.tag not in ("testsuites", "testsuite"):
        raise JUnitParseError(f"unexpected root element: {root.tag}")

    cases = tuple(_parse_case(el) for el in root.iter("testcase"))
    return JUnitReport(cases=cases)


def _parse_case(el: ET.Element) -> TestCaseResult:
    outcome, message, details = "passed", "", ""
    # A testcase can carry both <failure> and <error> (e.g. teardown error); failure wins.
    for tag, name in (("failure", "failed"), ("error", "error"), ("skipped", "skipped")):
        child = el.find(tag)
        if child is not None:
            outcome = name
            message = child.get("message", "")
            details = child.text or ""
            break
    return TestCaseResult(
        classname=el.get("classname", ""),
        name=el.get("name", ""),
        outcome=outcome,
        message=message,
        details=details,
    )
