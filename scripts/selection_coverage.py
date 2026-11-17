"""Report whether method B's file rule includes each case's root-cause file.

Usage: uv run python scripts/selection_coverage.py [--split dev]

This is an evaluation-side tool: it reads the answer labels to judge the rule
after the fact. The rule itself (analysis/context.py) never sees them. Run it
on the dev split only until the final evaluation.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from ci_failure_analyzer.analysis.context import METHOD_A, METHOD_B, build_context
from ci_failure_analyzer.inputs.reader import BundleReader
from ci_failure_analyzer.inputs.validation import validate_bundle

ROOT = Path(__file__).resolve().parent.parent


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--split", default="dev")
    args = parser.parse_args()

    split = json.loads((ROOT / "evals" / "splits" / f"{args.split}.json").read_text(encoding="utf-8"))
    print("| case | type | selected | root-cause file | included | chars A | chars B |")
    print("|---|---|---|---|---|---|---|")
    for case_id in split["case_ids"]:
        metadata = json.loads((ROOT / "evals" / "cases" / case_id / "metadata.json").read_text(encoding="utf-8"))
        label = json.loads((ROOT / "evals" / "labels" / f"{case_id}.json").read_text(encoding="utf-8"))
        bundle = ROOT / "work" / "inputs" / metadata["input_id"]
        result = validate_bundle(bundle)
        cause = label["root_cause"]["file"]
        if not result.analyzable:
            print(f"| {case_id} | {metadata['case_type']} | - ({result.reason_code}) | {cause} | - | - | - |")
            continue
        reader = BundleReader(bundle)
        context_b = build_context(reader, result.report, METHOD_B)
        context_a = build_context(reader, result.report, METHOD_A)
        included = "n/a" if cause is None else ("yes" if cause in context_b.provided_code_paths else "no")
        files = ", ".join(posix.rsplit("/", 1)[-1] for posix in context_b.provided_code_paths)
        print(
            f"| {case_id} | {metadata['case_type']} | {files} | {cause} | {included} "
            f"| {len(context_a.text)} | {len(context_b.text)} |"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
