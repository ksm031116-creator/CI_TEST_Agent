"""Collect a GitHub Actions run into work/inputs/ and report whether it can be analyzed.

Usage:
    uv run python scripts/collect_run.py <owner/repo> <run_id> --repo-path <local clone>
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from ci_failure_analyzer.inputs.bundle import MANIFEST_NAME
from ci_failure_analyzer.inputs.collector import BundleExistsError, collect_run
from ci_failure_analyzer.inputs.validation import validate_bundle

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("repository", help="owner/name of the analysis target repository")
    parser.add_argument("run_id", type=int)
    parser.add_argument("--repo-path", type=Path, required=True, help="local clone of the repository")
    parser.add_argument("--inputs-root", type=Path, default=PROJECT_ROOT / "work" / "inputs")
    parser.add_argument("--gh", default="gh", help="path to the gh executable")
    args = parser.parse_args()

    try:
        bundle_dir = collect_run(
            args.repository, args.run_id, args.inputs_root, args.repo_path, gh=args.gh
        )
    except BundleExistsError as exc:
        print(f"already collected: {exc}", file=sys.stderr)
        return 1

    manifest = json.loads((bundle_dir / MANIFEST_NAME).read_text(encoding="utf-8"))
    result = validate_bundle(bundle_dir)
    print(
        json.dumps(
            {
                "input_id": manifest["input_id"],
                "bundle_sha256": manifest["bundle_sha256"],
                "checkout_sha": manifest["checkout_sha"],
                "analyzable": result.analyzable,
                "reason_code": result.reason_code,
                "failed_tests": [c.node_id for c in result.report.failed] if result.report else [],
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
