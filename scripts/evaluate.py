"""Score stored analysis runs of one evaluation split against labels and grading records.

Usage:
  uv run python scripts/evaluate.py --split dev > outputs/<name>.md
  uv run python scripts/evaluate.py --split dev --write-stubs

Reads work/runs/ (current model and prompt only), evals/labels/ and
evals/gradings/. Makes no model call. Code decides the conclusion type, the
location and the checks; whether a report names the labelled cause comes from
the grading records (docs/grading_spec.md). --write-stubs creates an empty
record for every run that needs one and has none.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import Counter
from pathlib import Path

from ci_failure_analyzer.analysis.budget import load_config
from ci_failure_analyzer.analysis.prompt import PROMPT_VERSION, prompt_sha256
from ci_failure_analyzer.evaluation.grading import (
    MATCH,
    MISMATCH,
    PARTIAL,
    SPEC_VERSION,
    RunScore,
    automatic_verdict,
    score_run,
    top_candidate_index,
)

ROOT = Path(__file__).resolve().parent.parent
RUNS_ROOT = ROOT / "work" / "runs"
GRADINGS_ROOT = ROOT / "evals" / "gradings"
KOREAN = {MATCH: "일치", PARTIAL: "부분", MISMATCH: "불일치", None: "미채점"}


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, data: object) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")


def stub(manifest: dict, report: dict, report_sha256: str) -> dict:
    index = top_candidate_index(report)
    top = None
    if index:
        candidate = report["cause_candidates"][index - 1]
        top = {"index": index, "confidence": candidate["confidence"], "summary": candidate["summary"]}
    return {
        "spec_version": SPEC_VERSION,
        "run_id": manifest["run_id"],
        "case_id": manifest["case_id"],
        "method": manifest["method"],
        "report_sha256": report_sha256,
        "conclusion": report["conclusion"],
        "top_candidate": top,
        "top_candidate_key": None,
        "verdict": None,
        "matched_candidate": None,
        "partial_reasons": [],
        "rationale": "",
        "grader": None,
        "graded_on": None,
        "review": None,
    }


def load_runs(case_ids: list[str], model: str, prompt_hash: str) -> dict[str, list[tuple[dict, dict | None, str | None]]]:
    """Runs of the current model and prompt per case: (manifest, report, report hash), oldest first."""
    runs: dict[str, list] = {case_id: [] for case_id in case_ids}
    for manifest_path in sorted(RUNS_ROOT.glob("*/manifest.json")):
        manifest = read_json(manifest_path)
        if manifest.get("case_id") not in runs:
            continue
        if manifest.get("model") != model or manifest.get("prompt_sha256") != prompt_hash:
            continue
        report_path = manifest_path.parent / "report.json"
        report = report_hash = None
        if report_path.exists():
            report = read_json(report_path)
            report_hash = hashlib.sha256(report_path.read_bytes()).hexdigest()
        runs[manifest["case_id"]].append((manifest, report, report_hash))
    return runs


def joined(values: list[str]) -> str:
    return " / ".join(values)


def print_method_summary(scores: list[RunScore], methods: list[str]) -> None:
    print("| 방식 | 실행 | 일치 | 부분 | 불일치 | 미채점 | 맞는 추정+보류 | high 오답 | 결론 유형 허용 | 위치: 줄 / 파일 / 다른 파일 / 없음 | 첫 응답 검사 통과 | 사람 검토 |")
    print("|---|---|---|---|---|---|---|---|---|---|---|---|")
    for method in methods:
        rows = [s for s in scores if s.method == method]
        verdicts = Counter(s.verdict for s in rows)
        located = [s for s in rows if s.location != "n/a"]
        location = Counter(s.location for s in located)
        called = [s for s in rows if s.first_reply_passed is not None]
        judged = [s for s in rows if s.verdict_source in ("grader", "reviewed")]
        print(
            f"| {method} | {len(rows)} | {verdicts[MATCH]} | {verdicts[PARTIAL]} | {verdicts[MISMATCH]} | {verdicts[None]} "
            f"| {sum(s.withheld for s in rows)} | {sum(bool(s.wrong_high) for s in rows)} "
            f"| {sum(s.conclusion_allowed for s in rows)}/{len(rows)} "
            f"| {location['line']} / {location['file']} / {location['other']} / {location['none']} (대상 {len(located)}) "
            f"| {sum(bool(s.first_reply_passed) for s in called)}/{len(called)} "
            f"| {sum(s.reviewed for s in judged)}/{len(judged)} |"
        )


def print_case_table(scores: list[RunScore], case_types: dict[str, str], methods: list[str]) -> None:
    print("| 사례 | 유형 | 방식 | 판정 (실행 순) | 결론 (실행 순) | 1순위 후보 (실행 순) | 판정이 같은가 | 1순위 후보가 같은가 |")
    print("|---|---|---|---|---|---|---|---|")
    for case_id, case_type in case_types.items():
        for method in methods:
            rows = [s for s in scores if s.case_id == case_id and s.method == method]
            if not rows:
                print(f"| {case_id} | {case_type} | {method} | 실행 없음 | | | | |")
                continue
            verdicts = [KOREAN[s.verdict] + ("*" if s.reviewed else "") for s in rows]
            keys = [s.top_candidate_key or "-" for s in rows]
            same_verdict = "예" if len({s.verdict for s in rows}) == 1 else "**아니오**"
            same_key = "-" if set(keys) == {"-"} else ("예" if len(set(keys)) == 1 else "**아니오**")
            print(
                f"| {case_id} | {case_type} | {method} | {joined(verdicts)} | {joined([s.conclusion or '-' for s in rows])} "
                f"| {joined(keys)} | {same_verdict} | {same_key} |"
            )


def print_case_summary(scores: list[RunScore], case_ids: list[str], methods: list[str]) -> None:
    print("| 방식 | 사례 | 모든 실행이 일치 | 일치가 과반 | 판정이 실행마다 같음 | 결론 유형이 실행마다 같음 | 1순위 후보가 실행마다 같음 |")
    print("|---|---|---|---|---|---|---|")
    for method in methods:
        groups = [[s for s in scores if s.case_id == case_id and s.method == method] for case_id in case_ids]
        groups = [g for g in groups if g]
        keyed = [g for g in groups if any(s.top_candidate_key for s in g)]
        print(
            f"| {method} | {len(groups)} | {sum(all(s.verdict == MATCH for s in g) for g in groups)} "
            f"| {sum(2 * sum(s.verdict == MATCH for s in g) > len(g) for g in groups)} "
            f"| {sum(len({s.verdict for s in g}) == 1 for g in groups)} "
            f"| {sum(len({s.conclusion for s in g}) == 1 for g in groups)} "
            f"| {sum(len({s.top_candidate_key for s in g}) == 1 for g in keyed)}/{len(keyed)} |"
        )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--split", default="dev")
    parser.add_argument("--methods", nargs="+", default=["A", "B"])
    parser.add_argument("--write-stubs", action="store_true", help="create empty grading records for ungraded runs")
    parser.add_argument("--allow-holdout", action="store_true", help="only for the final evaluation")
    args = parser.parse_args()
    sys.stdout.reconfigure(encoding="utf-8", newline="\n")
    if args.split == "holdout" and not args.allow_holdout:
        raise SystemExit("refusing to evaluate the holdout split without --allow-holdout")

    config = load_config(ROOT / "configs" / "analysis.toml")
    prompt_hash = prompt_sha256()
    case_ids = read_json(ROOT / "evals" / "splits" / f"{args.split}.json")["case_ids"]
    case_types = {c: read_json(ROOT / "evals" / "cases" / c / "metadata.json")["case_type"] for c in case_ids}
    labels = {c: read_json(ROOT / "evals" / "labels" / f"{c}.json") for c in case_ids}
    runs = load_runs(case_ids, config.model, prompt_hash)

    scores: list[RunScore] = []
    created = 0
    for case_id in case_ids:
        for manifest, report, report_hash in runs[case_id]:
            if manifest["method"] not in args.methods:
                continue
            grading_path = GRADINGS_ROOT / f"{manifest['run_id']}.json"
            grading = read_json(grading_path) if grading_path.exists() else None
            if args.write_stubs and grading is None and automatic_verdict(report, labels[case_id]) is None:
                GRADINGS_ROOT.mkdir(parents=True, exist_ok=True)
                write_json(grading_path, stub(manifest, report, report_hash))
                created += 1
            scores.append(score_run(manifest, report, labels[case_id], grading, report_hash))
    if args.write_stubs:
        print(f"created {created} grading stubs in {GRADINGS_ROOT.relative_to(ROOT).as_posix()}")
        return 0

    print(f"모델 `{config.model}` · effort `{config.effort}` · 프롬프트 `{PROMPT_VERSION}` (`{prompt_hash[:12]}`) · 분할 `{args.split}` · 실행 {len(scores)}건")
    print()
    print("**방식별 집계 (실행 단위)**")
    print()
    print_method_summary(scores, args.methods)
    print()
    print("**방식별 집계 (사례 단위)**")
    print()
    print_case_summary(scores, case_ids, args.methods)
    print()
    print("**사례별 결과**")
    print()
    print_case_table(scores, case_types, args.methods)
    print()
    print("- 판정 뒤의 `*`는 사람이 검토한 판정이다. 표시가 없으면 1차 채점자의 판정이거나 코드가 정한 판정이다.")
    problems = [(s.run_id, p) for s in scores for p in s.problems]
    if problems:
        print()
        print("**쓸 수 없는 채점 기록**")
        print()
        for run_id, problem in problems:
            print(f"- `{run_id}`: {problem}")
    return 1 if problems else 0


if __name__ == "__main__":
    raise SystemExit(main())
