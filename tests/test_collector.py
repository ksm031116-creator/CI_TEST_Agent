import json
from pathlib import Path

import pytest

from ci_failure_analyzer.inputs.collector import (
    BundleExistsError,
    CommandError,
    collect_run,
)

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
    "jobs": [{"databaseId": 222, "name": "pytest"}],
}
CHECKOUT = "b" * 40


class FakeRunner:
    """Stands in for gh and git: returns canned output and writes the files they would."""

    def __init__(self, *, run=RUN, artifact=True, fail_on=None):
        self.run = run
        self.artifact = artifact
        self.fail_on = fail_on
        self.calls: list[tuple[list[str], Path | None]] = []

    def __call__(self, args, cwd):
        args = list(args)
        self.calls.append((args, cwd))
        if self.fail_on and self.fail_on in args:
            raise CommandError(f"simulated failure of {self.fail_on}")
        if args[:3] == ["gh", "run", "view"] and "--json" in args:
            return json.dumps(self.run).encode()
        if args[:3] == ["gh", "run", "view"] and "--log" in args:
            return b"pytest\tRun tests\tFAILED tests/test_x.py::test_y\n"
        if args[:3] == ["gh", "run", "download"]:
            if not self.artifact:
                raise CommandError("no artifact found")
            out = Path(args[args.index("--dir") + 1])
            out.mkdir(parents=True)
            (out / "checkout_sha.txt").write_text(CHECKOUT + "\n", encoding="utf-8")
            (out / "junit.xml").write_text("<testsuites/>", encoding="utf-8")
            return b""
        if args[:2] == ["git", "archive"]:
            Path(args[args.index("-o") + 1]).write_bytes(b"tar-bytes")
            return b""
        if args[:2] == ["git", "fetch"]:
            return b""
        raise AssertionError(f"unexpected command: {args}")


def test_collects_all_bundle_files(tmp_path):
    runner = FakeRunner()
    bundle = collect_run("owner/repo", 111, tmp_path / "inputs", tmp_path / "clone", runner=runner)

    assert bundle == tmp_path / "inputs" / "gha-111-a1-j222"
    assert sorted(p.relative_to(bundle).as_posix() for p in bundle.rglob("*") if p.is_file()) == [
        "code.tar",
        "job.log",
        "manifest.json",
        "reports/checkout_sha.txt",
        "reports/junit.xml",
        "run.json",
    ]
    manifest = json.loads((bundle / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["checkout_sha"] == CHECKOUT
    assert manifest["repository"] == "owner/repo"


def test_code_is_archived_from_checkout_sha_in_the_local_clone(tmp_path):
    runner = FakeRunner()
    clone = tmp_path / "clone"
    collect_run("owner/repo", 111, tmp_path / "inputs", clone, runner=runner)

    archive_args, archive_cwd = next(c for c in runner.calls if c[0][:2] == ["git", "archive"])
    assert archive_args[-1] == CHECKOUT
    assert archive_cwd == clone


def test_existing_bundle_is_not_overwritten(tmp_path):
    inputs = tmp_path / "inputs"
    bundle = collect_run("owner/repo", 111, inputs, tmp_path / "clone", runner=FakeRunner())
    original = (bundle / "job.log").read_bytes()

    with pytest.raises(BundleExistsError):
        collect_run("owner/repo", 111, inputs, tmp_path / "clone", runner=FakeRunner())
    assert (bundle / "job.log").read_bytes() == original


def test_rerun_attempt_gets_its_own_bundle(tmp_path):
    inputs = tmp_path / "inputs"
    collect_run("owner/repo", 111, inputs, tmp_path / "clone", runner=FakeRunner())
    rerun = {**RUN, "attempt": 2, "jobs": [{"databaseId": 333, "name": "pytest"}]}
    bundle = collect_run("owner/repo", 111, inputs, tmp_path / "clone", runner=FakeRunner(run=rerun))
    assert bundle.name == "gha-111-a2-j333"


def test_missing_artifact_still_stores_log_without_code(tmp_path):
    runner = FakeRunner(artifact=False)
    bundle = collect_run("owner/repo", 111, tmp_path / "inputs", tmp_path / "clone", runner=runner)

    assert (bundle / "job.log").exists()
    assert not (bundle / "code.tar").exists()
    manifest = json.loads((bundle / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["checkout_sha"] is None


def test_failed_collection_leaves_no_partial_bundle(tmp_path):
    inputs = tmp_path / "inputs"
    with pytest.raises(CommandError):
        collect_run(
            "owner/repo", 111, inputs, tmp_path / "clone", runner=FakeRunner(fail_on="archive")
        )
    assert list(inputs.iterdir()) == []


def test_run_with_multiple_jobs_is_rejected(tmp_path):
    run = {**RUN, "jobs": RUN["jobs"] * 2}
    with pytest.raises(ValueError, match="exactly one job"):
        collect_run(
            "owner/repo", 111, tmp_path / "inputs", tmp_path / "clone", runner=FakeRunner(run=run)
        )
