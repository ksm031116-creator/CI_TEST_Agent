import json
import shutil
from pathlib import Path

import pytest

from ci_failure_analyzer.inputs.bundle import (
    build_manifest,
    bundle_sha256,
    file_hashes,
    make_input_id,
    write_manifest,
)
from ci_failure_analyzer.inputs.validation import (
    MISSING_CHECKOUT_SHA,
    NO_JUNIT,
    NOT_TEST_FAILURE,
    validate_bundle,
)

FIXTURES = Path(__file__).parent / "fixtures"

RUN = {
    "databaseId": 111,
    "attempt": 2,
    "headSha": "a" * 40,
    "headBranch": "case/x",
    "event": "push",
    "createdAt": "2026-11-17T00:00:00Z",
    "conclusion": "failure",
    "workflowName": "tests",
    "url": "https://example.invalid/run/111",
    "jobs": [{"databaseId": 222, "name": "pytest"}],
}


@pytest.fixture
def bundle(tmp_path):
    (tmp_path / "reports").mkdir()
    (tmp_path / "run.json").write_text(json.dumps(RUN), encoding="utf-8")
    (tmp_path / "job.log").write_text("log line\n", encoding="utf-8")
    (tmp_path / "reports" / "checkout_sha.txt").write_text("b" * 40 + "\n", encoding="utf-8")
    shutil.copyfile(FIXTURES / "junit_mixed.xml", tmp_path / "reports" / "junit.xml")
    return tmp_path


def test_input_id_distinguishes_attempt_and_job():
    assert make_input_id(111, 2, 222) == "gha-111-a2-j222"


def test_manifest_uses_checkout_sha_not_head_sha(bundle):
    manifest = build_manifest(bundle, "owner/repo")
    assert manifest["input_id"] == "gha-111-a2-j222"
    assert manifest["checkout_sha"] == "b" * 40
    assert manifest["head_sha"] == "a" * 40


def test_file_hashes_use_posix_paths_and_skip_manifest(bundle):
    write_manifest(bundle, "owner/repo")
    assert sorted(file_hashes(bundle)) == [
        "job.log",
        "reports/checkout_sha.txt",
        "reports/junit.xml",
        "run.json",
    ]


def test_bundle_hash_is_stable_after_manifest_is_written(bundle):
    before = bundle_sha256(file_hashes(bundle))
    manifest = write_manifest(bundle, "owner/repo")
    assert manifest["bundle_sha256"] == before == bundle_sha256(file_hashes(bundle))


def test_bundle_hash_changes_when_a_file_changes(bundle):
    before = bundle_sha256(file_hashes(bundle))
    (bundle / "job.log").write_text("different\n", encoding="utf-8")
    assert bundle_sha256(file_hashes(bundle)) != before


def test_manifest_rejects_run_with_multiple_jobs(bundle):
    run = {**RUN, "jobs": RUN["jobs"] * 2}
    (bundle / "run.json").write_text(json.dumps(run), encoding="utf-8")
    with pytest.raises(ValueError, match="exactly one job"):
        build_manifest(bundle, "owner/repo")


def test_bundle_with_failed_tests_is_analyzable(bundle):
    result = validate_bundle(bundle)
    assert result.analyzable
    assert len(result.report.failed) == 3


def test_missing_junit_is_reported(bundle):
    (bundle / "reports" / "junit.xml").unlink()
    result = validate_bundle(bundle)
    assert not result.analyzable
    assert result.reason_code == NO_JUNIT


def test_unparseable_junit_is_reported(bundle):
    (bundle / "reports" / "junit.xml").write_text("<testsuites>", encoding="utf-8")
    assert validate_bundle(bundle).reason_code == NO_JUNIT


def test_run_without_failed_tests_is_reported(bundle):
    shutil.copyfile(FIXTURES / "junit_all_passed.xml", bundle / "reports" / "junit.xml")
    assert validate_bundle(bundle).reason_code == NOT_TEST_FAILURE


@pytest.mark.parametrize("content", [None, "", "  \n"])
def test_missing_or_empty_checkout_sha_is_reported(bundle, content):
    path = bundle / "reports" / "checkout_sha.txt"
    path.unlink()
    if content is not None:
        path.write_text(content, encoding="utf-8")
    assert validate_bundle(bundle).reason_code == MISSING_CHECKOUT_SHA
