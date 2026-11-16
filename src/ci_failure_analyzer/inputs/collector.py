"""Collect one GitHub Actions run into an input bundle using the `gh` CLI."""

from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
from collections.abc import Callable, Sequence
from pathlib import Path

from ci_failure_analyzer.inputs.bundle import (
    CHECKOUT_SHA,
    CODE_TAR,
    JOB_LOG,
    RUN_JSON,
    make_input_id,
    write_manifest,
)

RUN_FIELDS = "databaseId,attempt,headSha,headBranch,event,createdAt,conclusion,workflowName,url,jobs"
ARTIFACT_NAME = "pytest-reports"

# Runs a command and returns its stdout bytes; raises CommandError on failure.
Runner = Callable[[Sequence[str], Path | None], bytes]


class CommandError(RuntimeError):
    pass


class BundleExistsError(FileExistsError):
    """A bundle with this input id is already stored. Bundles are never overwritten."""


def run_command(args: Sequence[str], cwd: Path | None = None) -> bytes:
    proc = subprocess.run(list(args), cwd=cwd, capture_output=True)
    if proc.returncode != 0:
        stderr = proc.stderr.decode("utf-8", errors="replace").strip()
        raise CommandError(f"{args[0]} exited with {proc.returncode}: {stderr}")
    return proc.stdout


def collect_run(
    repository: str,
    run_id: int,
    inputs_root: Path,
    repo_path: Path,
    *,
    gh: str = "gh",
    runner: Runner = run_command,
) -> Path:
    """Store run metadata, log, reports artifact and code snapshot under `inputs_root`.

    `repo_path` is a local clone of `repository`, used to archive the checked-out commit.
    Returns the bundle directory. A missing reports artifact is not an error here:
    validation reports it later as `no_junit` or `missing_checkout_sha`.
    """
    run_json = runner(
        [gh, "run", "view", str(run_id), "--repo", repository, "--json", RUN_FIELDS], None
    )
    run = json.loads(run_json)
    jobs = run.get("jobs") or []
    if len(jobs) != 1:
        raise ValueError(f"expected exactly one job in run {run_id}, found {len(jobs)}")
    input_id = make_input_id(run["databaseId"], run["attempt"], jobs[0]["databaseId"])

    final_dir = inputs_root / input_id
    if final_dir.exists():
        raise BundleExistsError(str(final_dir))

    inputs_root.mkdir(parents=True, exist_ok=True)
    # Build in a sibling temp dir so a failed collection never leaves a partial bundle.
    work_dir = Path(tempfile.mkdtemp(prefix=f".{input_id}-", dir=inputs_root))
    try:
        (work_dir / RUN_JSON).write_bytes(run_json)
        (work_dir / JOB_LOG).write_bytes(
            runner([gh, "run", "view", str(run_id), "--repo", repository, "--log"], None)
        )

        reports_dir = work_dir / "reports"
        try:
            runner(
                [
                    gh, "run", "download", str(run_id), "--repo", repository,
                    "--name", ARTIFACT_NAME, "--dir", str(reports_dir),
                ],
                None,
            )
        except CommandError:
            reports_dir.mkdir(exist_ok=True)

        checkout_path = work_dir / CHECKOUT_SHA
        if checkout_path.exists():
            checkout_sha = checkout_path.read_text(encoding="utf-8").strip()
            runner(["git", "fetch", "--quiet", "origin", checkout_sha], repo_path)
            runner(
                ["git", "archive", "--format=tar", "-o", str(work_dir / CODE_TAR), checkout_sha],
                repo_path,
            )

        write_manifest(work_dir, repository)
        work_dir.rename(final_dir)
    except BaseException:
        shutil.rmtree(work_dir, ignore_errors=True)
        raise
    return final_dir
