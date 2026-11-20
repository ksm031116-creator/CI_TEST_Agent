"""Score stored analysis runs of one evaluation split against labels and grading records.

Usage:
  uv run python scripts/evaluate.py --split dev > outputs/<name>.md
  uv run python scripts/evaluate.py --split dev --format json > <path>.json
  uv run python scripts/evaluate.py --split dev --write-stubs

Reads work/runs/ (current model, and each method's current prompt, only),
evals/labels/ and evals/gradings/. Makes no model call. Without --methods, every method that has
a run of the split is compared. Cost, tokens and duration come from the run
manifests. Code decides the conclusion type, the
location and the checks; whether a report names the labelled cause comes from
the grading records (docs/grading_spec.md). --write-stubs creates an empty
record for every run that needs one and has none.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from dataclasses import asdict
from pathlib import Path

from ci_failure_analyzer.analysis.budget import load_config
from ci_failure_analyzer.analysis.prompt import prompt_identity
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
from ci_failure_analyzer.evaluation.summary import (
    UNGRADED,
    case_summary,
    cost_summary,
    exploration_row,
    match_counts,
    method_summary,
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


def load_runs(case_ids: list[str], model: str) -> dict[str, list[tuple[dict, dict | None, str | None]]]:
    """Runs of the current model and of each method's current prompt per case: (manifest, report, report hash), oldest first."""
    runs: dict[str, list] = {case_id: [] for case_id in case_ids}
    for manifest_path in sorted(RUNS_ROOT.glob("*/manifest.json")):
        manifest = read_json(manifest_path)
        if manifest.get("case_id") not in runs:
            continue
        if manifest.get("model") != model or manifest.get("prompt_sha256") != prompt_identity(manifest.get("method"))[1]:
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


def print_method_summary(summaries: dict[str, dict]) -> None:
    print("| 방식 | 실행 | 일치 | 부분 | 불일치 | 미채점 | 맞는 추정+보류 | high 오답 | 결론 유형 허용 | 위치: 줄 / 파일 / 다른 파일 / 없음 | 첫 응답 검사 통과 | 사람 검토 |")
    print("|---|---|---|---|---|---|---|---|---|---|---|---|")
    for method, m in summaries.items():
        verdicts, location = m["verdicts"], m["location"]
        print(
            f"| {method} | {m['runs']} | {verdicts[MATCH]} | {verdicts[PARTIAL]} | {verdicts[MISMATCH]} | {verdicts[UNGRADED]} "
            f"| {m['correct_but_withheld']} | {m['wrong_high_confidence']} "
            f"| {m['conclusion_allowed']}/{m['runs']} "
            f"| {location['line']} / {location['file']} / {location['other']} / {location['none']} (대상 {location['applicable']}) "
            f"| {m['first_reply_passed']['passed']}/{m['first_reply_passed']['called']} "
            f"| {m['reviewed']['reviewed']}/{m['reviewed']['judged']} |"
        )


def _money(value: str | None) -> str:
    return "-" if value is None else f"{float(value):.4f}"


def _plain(value: float | None) -> str:
    return "-" if value is None else str(value)


def print_cost_summary(costs: dict[str, dict]) -> None:
    print("| 방식 | 호출한 실행 | 모델 호출 | 도구 호출 | 입력 토큰 | 출력 토큰 | 비용($) | 실행당 비용($) | 실행당 최대($) | 소요 시간 중앙값(초) | 최대(초) |")
    print("|---|---|---|---|---|---|---|---|---|---|---|")
    for method, c in costs.items():
        print(
            f"| {method} | {c['runs_with_calls']} | {c['model_calls']} | {c['tool_calls']} | {c['input_tokens']} | {c['output_tokens']} "
            f"| {_money(c['cost_usd'])} | {_money(c['cost_usd_per_run'])} | {_money(c['max_cost_usd'])} "
            f"| {_plain(c['median_duration_seconds'])} | {_plain(c['max_duration_seconds'])} |"
        )


def print_comparison(counts: dict[str, dict[str, dict | None]], case_types: dict[str, str], methods: list[str]) -> None:
    print("| 사례 | 유형 | " + " | ".join(methods) + " |")
    print("|---|---|" + "---|" * len(methods))
    for case_id, by_method in counts.items():
        cells = ["-" if by_method[m] is None else f"{by_method[m]['match']}/{by_method[m]['runs']}" for m in methods]
        print(f"| {case_id} | {case_types[case_id]} | " + " | ".join(cells) + " |")


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


def print_case_summary(summaries: dict[str, dict]) -> None:
    print("| 방식 | 사례 | 모든 실행이 일치 | 일치가 과반 | 판정이 실행마다 같음 | 결론 유형이 실행마다 같음 | 1순위 후보가 실행마다 같음 |")
    print("|---|---|---|---|---|---|---|")
    for method, c in summaries.items():
        print(
            f"| {method} | {c['cases']} | {c['all_runs_match']} | {c['majority_match']} | {c['same_verdict']} "
            f"| {c['same_conclusion']} | {c['same_top_candidate']}/{c['cases_with_top_candidate']} |"
        )


def print_exploration(rows: list[dict]) -> None:
    print("| 사례 | 실행 ID | 모델 호출 | 도구 호출 (거부) | 읽은 파일 | 원인 파일을 읽음 | 원인 줄을 봄 | 닿은 한도 | 비용($) | 소요 시간(초) |")
    print("|---|---|---|---|---|---|---|---|---|---|")
    yes_no = {True: "예", False: "**아니오**", None: "-"}
    for r in rows:
        print(
            f"| {r['case_id']} | `{r['run_id']}` | {r['model_calls']} | {r['tool_calls']} ({r['refused_tool_calls']}) "
            f"| {r['files_read']} | {yes_no[r['cause_file_read']]} | {yes_no[r['cause_line_read']]} "
            f"| {r['limit_reached'] or '-'} | {_money(r['cost_usd'])} | {_plain(r['duration_seconds'])} |"
        )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--split", default="dev")
    parser.add_argument("--methods", nargs="+", help="default: every method with a run of the split")
    parser.add_argument("--format", choices=["md", "json"], default="md")
    parser.add_argument("--write-stubs", action="store_true", help="create empty grading records for ungraded runs")
    parser.add_argument("--allow-holdout", action="store_true", help="only for the final evaluation")
    args = parser.parse_args()
    sys.stdout.reconfigure(encoding="utf-8", newline="\n")
    if args.split == "holdout" and not args.allow_holdout:
        raise SystemExit("refusing to evaluate the holdout split without --allow-holdout")

    config = load_config(ROOT / "configs" / "analysis.toml")
    case_ids = read_json(ROOT / "evals" / "splits" / f"{args.split}.json")["case_ids"]
    case_types = {c: read_json(ROOT / "evals" / "cases" / c / "metadata.json")["case_type"] for c in case_ids}
    labels = {c: read_json(ROOT / "evals" / "labels" / f"{c}.json") for c in case_ids}
    runs = load_runs(case_ids, config.model)

    methods = args.methods or sorted({m["method"] for case_runs in runs.values() for m, _, _ in case_runs})

    scores: list[RunScore] = []
    manifests: dict[str, dict] = {}
    created = 0
    for case_id in case_ids:
        for manifest, report, report_hash in runs[case_id]:
            if manifest["method"] not in methods:
                continue
            manifests[manifest["run_id"]] = manifest
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

    by_method = {m: [s for s in scores if s.method == m] for m in methods}
    run_summaries = {m: method_summary(rows) for m, rows in by_method.items()}
    case_summaries = {
        m: case_summary([[s for s in rows if s.case_id == case_id] for case_id in case_ids]) for m, rows in by_method.items()
    }
    costs = {m: cost_summary([manifests[s.run_id] for s in rows]) for m, rows in by_method.items()}
    counts = match_counts(scores, case_ids, methods)
    prompts = dict(zip(methods, map(prompt_identity, methods), strict=True))
    exploration = [
        row for s in scores if (row := exploration_row(manifests[s.run_id], labels[s.case_id])) is not None
    ]
    problems = [(s.run_id, p) for s in scores for p in s.problems]

    if args.format == "json":
        result = {
            "model": config.model,
            "effort": config.effort,
            "prompts": {m: {"version": version, "sha256": sha} for m, (version, sha) in prompts.items()},
            "grading_spec_version": SPEC_VERSION,
            "split": args.split,
            "methods": {m: {"runs": run_summaries[m], "cases": case_summaries[m], "cost": costs[m]} for m in methods},
            "match_by_case": counts,
            "exploration": exploration,
            "runs": [asdict(s) | {"cost_usd": manifests[s.run_id].get("cost_usd")} for s in scores],
        }
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 1 if problems else 0

    by_prompt: dict[tuple[str, str], list[str]] = {}
    for method, identity in prompts.items():
        by_prompt.setdefault(identity, []).append(method)
    prompt_text = ", ".join(f"{'/'.join(ms)} `{version}` (`{sha[:12]}`)" for (version, sha), ms in by_prompt.items())
    print(f"모델 `{config.model}` · effort `{config.effort}` · 프롬프트 {prompt_text} · 분할 `{args.split}` · 실행 {len(scores)}건")
    print()
    print("**방식별 집계 (실행 단위)**")
    print()
    print_method_summary(run_summaries)
    print()
    print("**방식별 집계 (사례 단위)**")
    print()
    print_case_summary(case_summaries)
    print()
    print("**방식별 비용과 소요 시간**")
    print()
    print_cost_summary(costs)
    print()
    print("- 평균과 중앙값은 모델을 호출한 실행만 센다. 비용은 실행 기록의 값이고, 사용량 장부와 같은 요금표로 계산한 것이다.")
    print()
    print("**사례별 일치 수 (일치한 실행 / 실행)**")
    print()
    print_comparison(counts, case_types, methods)
    print()
    print("**사례별 결과**")
    print()
    print_case_table(scores, case_types, methods)
    print()
    print("- 판정 뒤의 `*`는 사람이 검토한 판정이다. 표시가 없으면 1차 채점자의 판정이거나 코드가 정한 판정이다.")
    if exploration:
        print()
        print("**탐색 기록 (도구를 쓰는 방식의 실행)**")
        print()
        print_exploration(exploration)
        print()
        print("- 원인 파일과 줄은 정답 레이블의 위치다. 레이블에 코드 위치가 없는 사례는 `-`로 적는다.")
        print("- 닿은 한도: `tool_calls`(도구 호출), `model_calls`(모델 호출), `cost`(실행당 비용). `-`는 모델이 스스로 탐색을 끝낸 실행이다.")
    if problems:
        print()
        print("**쓸 수 없는 채점 기록**")
        print()
        for run_id, problem in problems:
            print(f"- `{run_id}`: {problem}")
    return 1 if problems else 0


if __name__ == "__main__":
    raise SystemExit(main())
