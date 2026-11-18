"""Print a Markdown table of stored analysis runs for one evaluation split.

Usage: uv run python scripts/summarize_runs.py --split dev > outputs/<name>.md

Reads work/runs/*/manifest.json and case metadata only. It fills in what code
can decide (status, checks, tokens, cost); it does not read answer labels and
does not judge whether a cause is correct. For each case and method it takes
the latest run made with the current model and prompt.
"""

from __future__ import annotations

import argparse
import json
import sys
from decimal import Decimal
from pathlib import Path

from ci_failure_analyzer.analysis.budget import load_config
from ci_failure_analyzer.analysis.prompt import PROMPT_VERSION, prompt_sha256

ROOT = Path(__file__).resolve().parent.parent


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def first_check(manifest: dict, key: str) -> str:
    attempts = manifest["attempts"]
    if not attempts:
        return "-"
    if attempts[0]["stop_reason"] != "end_turn":
        return attempts[0]["stop_reason"]
    return "통과" if not attempts[0][key] else f"실패({len(attempts[0][key])})"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--split", default="dev")
    parser.add_argument("--methods", nargs="+", default=["A", "B"])
    args = parser.parse_args()
    sys.stdout.reconfigure(encoding="utf-8", newline="\n")

    config = load_config(ROOT / "configs" / "analysis.toml")
    prompt_hash = prompt_sha256()
    latest: dict[tuple[str, str], dict] = {}
    for path in sorted((ROOT / "work" / "runs").glob("*/manifest.json")):
        m = read_json(path)
        if m.get("model") == config.model and m.get("prompt_sha256") == prompt_hash:
            latest[(m["input_id"], m["method"])] = m

    print(f"모델 `{config.model}` · effort `{config.effort}` · 프롬프트 `{PROMPT_VERSION}` (`{prompt_hash[:12]}`)")
    print()
    print("| 사례 | 유형 | 방식 | 상태 | 결론 | 호출 | 형식(1차) | 인용(1차) | 코드 파일 | 입력 토큰 | 출력 토큰 | 비용($) | 실행 ID |")
    print("|---|---|---|---|---|---|---|---|---|---|---|---|---|")
    total_cost = Decimal("0")
    total_calls = 0
    commits: set[str] = set()
    for case_id in read_json(ROOT / "evals" / "splits" / f"{args.split}.json")["case_ids"]:
        metadata = read_json(ROOT / "evals" / "cases" / case_id / "metadata.json")
        for method in args.methods:
            m = latest.get((metadata["input_id"], method))
            if m is None:
                print(f"| {case_id} | {metadata['case_type']} | {method} | 실행 없음 | | | | | | | | | |")
                continue
            total_cost += Decimal(m["cost_usd"])
            total_calls += m["model_calls"]
            commits.add(m["code"]["commit"][:7] + ("+dirty" if m["code"]["dirty"] else ""))
            conclusion = m["conclusion"] or "-"
            if m.get("reason_code"):
                conclusion += f" ({m['reason_code']})"
            files = len(m["selected_files"]) if "selected_files" in m else "-"
            print(
                f"| {case_id} | {metadata['case_type']} | {method} | {m['status']} | {conclusion} | {m['model_calls']} "
                f"| {first_check(m, 'format_problems')} | {first_check(m, 'citation_problems')} | {files} "
                f"| {m['input_tokens']} | {m['output_tokens']} | {Decimal(m['cost_usd']):.4f} | `{m['run_id']}` |"
            )
    print()
    print(f"모델 호출 {total_calls}회 · 비용 합계 ${total_cost:.4f} · 요금 기준일 {config.pricing_date} · 코드 커밋 {', '.join(sorted(commits))}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
