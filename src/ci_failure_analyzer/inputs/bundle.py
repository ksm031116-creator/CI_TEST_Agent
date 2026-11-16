"""Input bundle identity: ids, file hashes and the manifest."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

MANIFEST_NAME = "manifest.json"
RUN_JSON = "run.json"
JOB_LOG = "job.log"
CODE_TAR = "code.tar"
JUNIT_XML = "reports/junit.xml"
CHECKOUT_SHA = "reports/checkout_sha.txt"


def make_input_id(run_id: int, run_attempt: int, job_id: int) -> str:
    return f"gha-{run_id}-a{run_attempt}-j{job_id}"


def file_hashes(bundle_dir: Path) -> dict[str, str]:
    """SHA-256 of every file in the bundle except the manifest, keyed by posix path."""
    hashes: dict[str, str] = {}
    for path in sorted(p for p in bundle_dir.rglob("*") if p.is_file()):
        rel = path.relative_to(bundle_dir).as_posix()
        if rel == MANIFEST_NAME:
            continue
        hashes[rel] = hashlib.sha256(path.read_bytes()).hexdigest()
    return hashes


def bundle_sha256(hashes: dict[str, str]) -> str:
    listing = "".join(f"{rel} {digest}\n" for rel, digest in sorted(hashes.items()))
    return hashlib.sha256(listing.encode()).hexdigest()


def build_manifest(bundle_dir: Path, repository: str) -> dict:
    run = json.loads((bundle_dir / RUN_JSON).read_text(encoding="utf-8"))
    job = _single_job(run)
    checkout_path = bundle_dir / CHECKOUT_SHA
    checkout_sha = checkout_path.read_text(encoding="utf-8").strip() if checkout_path.exists() else None
    hashes = file_hashes(bundle_dir)
    return {
        "input_id": make_input_id(run["databaseId"], run["attempt"], job["databaseId"]),
        "source": "github_actions",
        "repository": repository,
        "run_id": run["databaseId"],
        "run_attempt": run["attempt"],
        "job_id": job["databaseId"],
        "job_name": job["name"],
        "workflow": run["workflowName"],
        "event": run["event"],
        "head_branch": run["headBranch"],
        "head_sha": run["headSha"],
        "checkout_sha": checkout_sha,
        "created_at": run["createdAt"],
        "conclusion": run["conclusion"],
        "files": hashes,
        "bundle_sha256": bundle_sha256(hashes),
    }


def write_manifest(bundle_dir: Path, repository: str) -> dict:
    manifest = build_manifest(bundle_dir, repository)
    (bundle_dir / MANIFEST_NAME).write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    return manifest


def _single_job(run: dict) -> dict:
    jobs = run.get("jobs") or []
    if len(jobs) != 1:
        # First version: one pytest job per run. See docs/input_spec.md.
        raise ValueError(f"expected exactly one job in run, found {len(jobs)}")
    return jobs[0]
