"""Print the analysis input that method A or B would receive for a stored bundle.

Usage: uv run python scripts/build_context.py <input_id> --method B [--stats]
No model is called.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from ci_failure_analyzer.analysis.budget import estimate_input_tokens
from ci_failure_analyzer.analysis.context import METHOD_A, METHOD_B, build_context
from ci_failure_analyzer.inputs.reader import BundleReader
from ci_failure_analyzer.inputs.validation import validate_bundle

ROOT = Path(__file__).resolve().parent.parent


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input_id")
    parser.add_argument("--method", choices=[METHOD_A, METHOD_B], default=METHOD_B)
    parser.add_argument("--inputs-root", type=Path, default=ROOT / "work" / "inputs")
    parser.add_argument("--stats", action="store_true", help="print a JSON summary instead of the text")
    args = parser.parse_args()

    bundle = args.inputs_root / args.input_id
    result = validate_bundle(bundle)
    if not result.analyzable:
        print(json.dumps({"input_id": args.input_id, "analyzable": False, "reason_code": result.reason_code}))
        return 1
    context = build_context(BundleReader(bundle), result.report, args.method)
    if args.stats:
        summary = {
            "input_id": args.input_id,
            "method": context.method,
            "log_lines": [context.log_lines_included, context.log_lines_total],
            "selected_files": [[f.path, f.reason] for f in context.selected_files],
            "omitted_files": [f.path for f in context.omitted_files],
            "truncated_files": list(context.truncated_files),
            "characters": len(context.text),
            "input_tokens_upper_bound": estimate_input_tokens(context.text),
        }
        print(json.dumps(summary, ensure_ascii=False, indent=2))
    else:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stdout.write(context.text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
