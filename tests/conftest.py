import io
import json
import tarfile
from pathlib import Path

import pytest

RUN = {
    "databaseId": 111,
    "attempt": 1,
    "headSha": "a" * 40,
    "headBranch": "case/x",
    "event": "push",
    "createdAt": "2026-11-17T00:00:00Z",
    "conclusion": "failure",
    "workflowName": "tests",
    "url": "https://example.invalid/run/111",
    "jobs": [
        {
            "databaseId": 222,
            "name": "pytest",
            "steps": [
                {"name": "Install", "number": 1, "conclusion": "success"},
                {"name": "Run tests", "number": 2, "conclusion": "failure"},
            ],
        }
    ],
}


@pytest.fixture
def make_bundle(tmp_path):
    """Build a bundle directory from log text, JUnit XML text and code files."""

    def build(log: str, code: dict[str, str], junit: str | None = None) -> Path:
        bundle = tmp_path / "bundle"
        (bundle / "reports").mkdir(parents=True)
        (bundle / "run.json").write_text(json.dumps(RUN), encoding="utf-8")
        (bundle / "job.log").write_bytes(log.encode("utf-8"))
        (bundle / "reports" / "checkout_sha.txt").write_text("b" * 40 + "\n", encoding="utf-8")
        (bundle / "reports" / "python_version.txt").write_text("Python 3.12.16\n", encoding="utf-8")
        if junit is not None:
            (bundle / "reports" / "junit.xml").write_bytes(junit.encode("utf-8"))
        with tarfile.open(bundle / "code.tar", "w") as tar:
            for name, text in code.items():
                data = text.encode("utf-8")
                info = tarfile.TarInfo(name)
                info.size = len(data)
                tar.addfile(info, io.BytesIO(data))
        return bundle

    return build
