"""Decide whether a stored bundle can be analyzed, and why not if it cannot."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from ci_failure_analyzer.inputs.bundle import CHECKOUT_SHA, JUNIT_XML
from ci_failure_analyzer.inputs.junit import JUnitParseError, JUnitReport, parse_junit

NO_JUNIT = "no_junit"
NOT_TEST_FAILURE = "not_test_failure"
MISSING_CHECKOUT_SHA = "missing_checkout_sha"


@dataclass(frozen=True)
class ValidationResult:
    reason_code: str | None
    detail: str = ""
    report: JUnitReport | None = None

    @property
    def analyzable(self) -> bool:
        return self.reason_code is None


def validate_bundle(bundle_dir: Path) -> ValidationResult:
    checkout_path = bundle_dir / CHECKOUT_SHA
    if not checkout_path.exists() or not checkout_path.read_text(encoding="utf-8").strip():
        return ValidationResult(MISSING_CHECKOUT_SHA, f"{CHECKOUT_SHA} is missing or empty")

    junit_path = bundle_dir / JUNIT_XML
    if not junit_path.exists():
        return ValidationResult(NO_JUNIT, f"{JUNIT_XML} is missing; pytest may not have run")
    try:
        report = parse_junit(junit_path)
    except JUnitParseError as exc:
        return ValidationResult(NO_JUNIT, f"{JUNIT_XML} cannot be parsed: {exc}")

    if not report.failed:
        return ValidationResult(
            NOT_TEST_FAILURE, "JUnit XML has no failed or errored tests", report
        )
    return ValidationResult(None, report=report)
