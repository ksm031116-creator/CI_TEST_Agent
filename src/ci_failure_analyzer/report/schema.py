"""Report data model shared by every analysis method. See docs/report_spec.md."""

from __future__ import annotations

from enum import StrEnum
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, ValidationError, model_validator

from ci_failure_analyzer.inputs.bundle import JOB_LOG, JUNIT_XML

SCHEMA_VERSION = "1"

Text = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]


class Conclusion(StrEnum):
    CAUSE_CANDIDATE = "cause_candidate"
    INSUFFICIENT_EVIDENCE = "insufficient_evidence"
    OUT_OF_SCOPE = "out_of_scope"


class EvidenceSource(StrEnum):
    LOG = "log"
    JUNIT = "junit"
    CODE = "code"


FIXED_PATHS = {EvidenceSource.LOG: JOB_LOG, EvidenceSource.JUNIT: JUNIT_XML}


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Evidence(_Model):
    """A quoted span of the input. `quote` must be copied from the cited lines."""

    id: Text
    source: EvidenceSource
    path: Text
    start_line: int = Field(ge=1)
    end_line: int = Field(ge=1)
    quote: Text

    @model_validator(mode="after")
    def _check_span(self) -> Evidence:
        if self.end_line < self.start_line:
            raise ValueError("end_line must not be before start_line")
        fixed = FIXED_PATHS.get(self.source)
        if fixed is not None and self.path != fixed:
            raise ValueError(f"path for {self.source.value} evidence must be {fixed}")
        if self.source is EvidenceSource.CODE and self.path in FIXED_PATHS.values():
            raise ValueError("code evidence must cite a file in the code snapshot")
        return self


class ObservedFact(_Model):
    statement: Text
    evidence_ids: list[Text] = Field(min_length=1)


class CodeLocation(_Model):
    path: Text
    line: int = Field(ge=1)


class CauseCandidate(_Model):
    summary: Text
    reasoning: Text
    confidence: Literal["low", "medium", "high"]
    location: CodeLocation | None = None
    evidence_ids: list[Text] = Field(min_length=1)


class VerificationStep(_Model):
    description: Text
    command: str | None = None


class Report(_Model):
    schema_version: Literal["1"] = SCHEMA_VERSION
    conclusion: Conclusion
    reason_code: str | None = None
    observed_facts: list[ObservedFact] = Field(default_factory=list)
    cause_candidates: list[CauseCandidate] = Field(default_factory=list)
    evidence: list[Evidence] = Field(default_factory=list)
    verification_steps: list[VerificationStep] = Field(default_factory=list)
    limitations: list[Text] = Field(default_factory=list)

    @model_validator(mode="after")
    def _check_consistency(self) -> Report:
        problems: list[str] = []
        ids = [e.id for e in self.evidence]
        duplicates = sorted({i for i in ids if ids.count(i) > 1})
        if duplicates:
            problems.append(f"duplicate evidence ids: {', '.join(duplicates)}")
        known = set(ids)
        referenced = [i for f in self.observed_facts for i in f.evidence_ids]
        referenced += [i for c in self.cause_candidates for i in c.evidence_ids]
        unknown = sorted(set(referenced) - known)
        if unknown:
            problems.append(f"unknown evidence ids: {', '.join(unknown)}")

        if self.conclusion is Conclusion.OUT_OF_SCOPE:
            if not self.reason_code:
                problems.append("out_of_scope needs a reason_code")
            if self.cause_candidates:
                problems.append("out_of_scope must not list cause candidates")
        else:
            if self.reason_code:
                problems.append("reason_code is only for out_of_scope")
            if not self.observed_facts:
                problems.append("at least one observed fact is required")
            if not self.verification_steps:
                problems.append("at least one verification step is required")

        if self.conclusion is Conclusion.CAUSE_CANDIDATE and not self.cause_candidates:
            problems.append("cause_candidate needs at least one cause candidate")
        if self.conclusion is Conclusion.INSUFFICIENT_EVIDENCE:
            if not self.limitations:
                problems.append("insufficient_evidence needs at least one limitation")
            if any(c.confidence == "high" for c in self.cause_candidates):
                problems.append("insufficient_evidence must not have a high-confidence candidate")

        if problems:
            raise ValueError("; ".join(problems))
        return self


class ReportFormatError(ValueError):
    """The data is not a valid report. `problems` lists every violation found."""

    def __init__(self, problems: list[str]) -> None:
        super().__init__("; ".join(problems))
        self.problems = problems


def parse_report(data: dict | str | bytes) -> Report:
    """Validate a report given as a dict or as JSON text."""
    try:
        if isinstance(data, dict):
            return Report.model_validate(data)
        return Report.model_validate_json(data)
    except ValidationError as exc:
        problems = [
            f"{'.'.join(str(part) for part in error['loc']) or 'report'}: {error['msg']}"
            for error in exc.errors()
        ]
        raise ReportFormatError(problems) from exc
