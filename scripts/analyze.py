"""Analyze stored bundles with method A, B or C and save each run under work/runs/.

Usage:
  uv run python scripts/analyze.py <input_id> --method B
  uv run python scripts/analyze.py --case case-009 --method A B
  uv run python scripts/analyze.py --split dev --method A B --ceiling-usd 10
  uv run python scripts/analyze.py --case case-009 --method C --ceiling-usd 14.9

This calls the model API and costs money. The key is read from ANTHROPIC_API_KEY
or from .env in the project root. Every call goes through the usage ledger
(work/service_data/api_usage.jsonl), which enforces the limit in
configs/analysis.toml. A bundle outside the analysis scope gets an out_of_scope
report without a model call. A (bundle, method) pair that already has a run
with the same model and prompt is skipped unless --rerun is given. Method C makes
several model calls per run within the limits of analysis/agent.py.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import time
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

from ci_failure_analyzer.analysis.budget import UsageLedger, load_config
from ci_failure_analyzer.analysis.agent import MAX_MODEL_CALLS, MAX_RUN_COST_USD, AgentResult, run_agent
from ci_failure_analyzer.analysis.context import METHOD_A, METHOD_B, METHOD_C, build_context
from ci_failure_analyzer.analysis.prompt import prompt_identity
from ci_failure_analyzer.analysis.runner import AnalysisResult, AnthropicClient, ModelReply, run_analysis
from ci_failure_analyzer.analysis.tools import MAX_TOOL_CALLS
from ci_failure_analyzer.inputs.bundle import bundle_sha256, file_hashes
from ci_failure_analyzer.inputs.reader import BundleReader
from ci_failure_analyzer.inputs.validation import validate_bundle
from ci_failure_analyzer.report.schema import Conclusion, Report

ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = ROOT / "configs" / "analysis.toml"
LEDGER_PATH = ROOT / "work" / "service_data" / "api_usage.jsonl"
RUNS_ROOT = ROOT / "work" / "runs"
CASES_ROOT = ROOT / "evals" / "cases"
SPLITS_ROOT = ROOT / "evals" / "splits"
# Run folders are named in Korean time (folder_management.md). Korea has no DST.
KST = timezone(timedelta(hours=9))


def load_env_file(path: Path) -> None:
    """Put KEY=VALUE lines of a .env file into the environment without overriding it."""
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8-sig").splitlines():
        name, separator, value = line.strip().partition("=")
        if separator and name and not name.startswith("#"):
            os.environ.setdefault(name.strip(), value.strip().strip("\"'"))


def git_state() -> dict:
    def git(*args: str) -> str:
        return subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True, check=True).stdout.strip()

    return {"commit": git("rev-parse", "HEAD"), "dirty": bool(git("status", "--porcelain"))}


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, data: object) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")


def holdout_case_ids() -> set[str]:
    path = SPLITS_ROOT / "holdout.json"
    return set(read_json(path)["case_ids"]) if path.exists() else set()


def targets(args: argparse.Namespace) -> list[tuple[str | None, str]]:
    """(case_id, input_id) pairs named on the command line."""
    case_ids = list(args.case or [])
    if args.split:
        case_ids += read_json(SPLITS_ROOT / f"{args.split}.json")["case_ids"]
    blocked = sorted(set(case_ids) & holdout_case_ids())
    if blocked and not args.allow_holdout:
        raise SystemExit(f"refusing to run holdout cases without --allow-holdout: {', '.join(blocked)}")
    pairs: list[tuple[str | None, str]] = [(None, input_id) for input_id in args.input_id]
    pairs += [(case_id, read_json(CASES_ROOT / case_id / "metadata.json")["input_id"]) for case_id in case_ids]
    if not pairs:
        raise SystemExit("name an input_id, --case or --split")
    return pairs


def find_existing(input_id: str, method: str, model: str, prompt_hash: str, context_hash: str | None) -> Path | None:
    """A stored run of the same bundle with the same method, model, prompt and input text."""
    wanted = (input_id, method, model, prompt_hash, context_hash)
    for manifest_path in sorted(RUNS_ROOT.glob("*/manifest.json")):
        m = read_json(manifest_path)
        found = (m.get("input_id"), m.get("method"), m.get("model"), m.get("prompt_sha256"), m.get("context_sha256"))
        if found == wanted:
            return manifest_path.parent
    return None


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def new_run_dir(method: str, short_id: str) -> Path:
    stamp = datetime.now(KST).strftime("%Y%m%d-%H%M%S")
    run_dir = RUNS_ROOT / f"{stamp}_{method}_{short_id}"
    suffix = 1
    while run_dir.exists():
        suffix += 1
        run_dir = RUNS_ROOT / f"{stamp}_{method}_{short_id}-{suffix}"
    run_dir.mkdir(parents=True)
    return run_dir


def call_record(number: int, reply: ModelReply, cost: Decimal, format_problems, citation_problems, run_dir: Path) -> dict:
    """Store one model reply and return its entry for the manifest."""
    response_file = f"response_{number}.json"
    write_json(run_dir / response_file, reply.raw or {"text": reply.text})
    return {
        "response_file": response_file,
        "request_id": reply.request_id,
        "stop_reason": reply.stop_reason,
        "input_tokens": reply.input_tokens,
        "output_tokens": reply.output_tokens,
        "cache_write_tokens": reply.cache_write_tokens,
        "cache_read_tokens": reply.cache_read_tokens,
        "cost_usd": str(cost),
        "format_problems": list(format_problems),
        "citation_problems": list(citation_problems),
    }


def attempt_records(result: AnalysisResult, run_dir: Path) -> list[dict]:
    return [
        call_record(number, a.reply, a.cost_usd, a.format_problems, a.citation_problems, run_dir)
        for number, a in enumerate(result.attempts, 1)
    ]


def agent_records(result: AgentResult, run_dir: Path) -> list[dict]:
    """Like `attempt_records`, one entry per model call, with what kind of call it was."""
    return [
        call_record(number, c.reply, c.cost_usd, c.format_problems, c.citation_problems, run_dir)
        | {"kind": c.kind, "tools_allowed": c.tools_allowed, "tool_uses": len(c.reply.tool_uses)}
        for number, c in enumerate(result.calls, 1)
    ]


def analyze(case_id: str | None, input_id: str, method: str, args: argparse.Namespace, ledger: UsageLedger) -> dict:
    config = ledger.config
    bundle = args.inputs_root / input_id
    if not (bundle / "run.json").exists():
        raise SystemExit(f"bundle not found: {bundle}")
    validation = validate_bundle(bundle)
    context_hash = None
    if validation.analyzable:
        context_hash = sha256_text(build_context(BundleReader(bundle), validation.report, method).text)
    prompt_version, prompt_hash = prompt_identity(method)
    existing = find_existing(input_id, method, config.model, prompt_hash, context_hash)
    if existing is not None and not args.rerun:
        return {"case_id": case_id, "method": method, "skipped": existing.name}

    short_id = case_id or input_id.rsplit("-j", 1)[-1][-6:]
    run_dir = new_run_dir(method, short_id)
    manifest: dict = {
        "run_id": run_dir.name,
        "case_id": case_id,
        "input_id": input_id,
        "input_bundle_sha256": bundle_sha256(file_hashes(bundle)),
        "method": method,
        "code": git_state(),
        "config": CONFIG_PATH.relative_to(ROOT).as_posix(),
        "model": config.model,
        "effort": config.effort,
        "max_output_tokens": config.max_output_tokens,
        "prompt_version": prompt_version,
        "prompt_sha256": prompt_hash,
        "pricing_date": config.pricing_date,
        "started_at": datetime.now(KST).isoformat(timespec="seconds"),
    }

    started = time.monotonic()
    if not validation.analyzable:
        report = Report(conclusion=Conclusion.OUT_OF_SCOPE, reason_code=validation.reason_code)
        write_json(run_dir / "report.json", report.model_dump(mode="json"))
        manifest |= {
            "status": "ok",
            "conclusion": report.conclusion.value,
            "reason_code": validation.reason_code,
            "model_calls": 0,
            "attempts": [],
            "input_tokens": 0,
            "output_tokens": 0,
            "cost_usd": "0",
        }
    else:
        ceiling = None if args.ceiling_usd is None else Decimal(args.ceiling_usd)
        reader = BundleReader(bundle)
        purpose = f"analyze:{case_id or input_id}:{method}:{run_dir.name}"
        extra: dict = {}
        if method == METHOD_C:
            result = run_agent(reader, validation.report, args.client(), ledger, purpose, ceiling)
            attempts = agent_records(result, run_dir)
            extra = {
                "limits": {
                    "tool_calls": MAX_TOOL_CALLS,
                    "model_calls": MAX_MODEL_CALLS,
                    "run_cost_usd": str(MAX_RUN_COST_USD),
                },
                "tool_call_count": len(result.session.calls),
                "refused_tool_calls": result.session.refused_calls,
                "tool_calls": result.session.calls,
                "seen_files": result.seen_files,
                "limit_reached": result.limit_reached,
            }
        else:
            result = run_analysis(reader, validation.report, method, args.client(), ledger, purpose, ceiling)
            attempts = attempt_records(result, run_dir)
        context = result.context
        (run_dir / "context.txt").write_text(context.text, encoding="utf-8", newline="\n")
        if result.report is not None:
            write_json(run_dir / "report.json", result.report.model_dump(mode="json"))
        manifest |= {
            "status": result.status,
            "conclusion": result.report.conclusion.value if result.report else None,
            "context_sha256": sha256_text(context.text),
            "context_characters": len(context.text),
            "log_lines": [context.log_lines_included, context.log_lines_total],
            "selected_files": [[f.path, f.reason] for f in context.selected_files],
            "omitted_files": [f.path for f in context.omitted_files],
            "truncated_files": list(context.truncated_files),
            "model_calls": len(attempts),
            "attempts": attempts,
            "input_tokens": sum(a["input_tokens"] for a in attempts),
            "output_tokens": sum(a["output_tokens"] for a in attempts),
            "cost_usd": str(result.cost_usd),
        } | extra
    manifest["duration_seconds"] = round(time.monotonic() - started, 1)
    write_json(run_dir / "manifest.json", manifest)
    keys = ("run_id", "case_id", "method", "status", "conclusion", "model_calls", "input_tokens", "output_tokens", "cost_usd")
    return {key: manifest[key] for key in keys}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("input_id", nargs="*")
    parser.add_argument("--case", nargs="+", help="evaluation case ids, e.g. case-009")
    parser.add_argument("--split", help="run every case of evals/splits/<split>.json")
    parser.add_argument("--method", nargs="+", choices=[METHOD_A, METHOD_B, METHOD_C], default=[METHOD_B])
    parser.add_argument("--inputs-root", type=Path, default=ROOT / "work" / "inputs")
    parser.add_argument("--ceiling-usd", help="stop before total recorded spending could pass this amount")
    parser.add_argument("--rerun", action="store_true", help="run again even if a matching run exists")
    parser.add_argument("--allow-holdout", action="store_true", help="only for the final evaluation")
    args = parser.parse_args()

    load_env_file(ROOT / ".env")
    ledger = UsageLedger(LEDGER_PATH, load_config(CONFIG_PATH))
    client: list[AnthropicClient] = []

    def get_client() -> AnthropicClient:
        if not client:
            client.append(AnthropicClient())
        return client[0]

    args.client = get_client
    for case_id, input_id in targets(args):
        for method in args.method:
            print(json.dumps(analyze(case_id, input_id, method, args, ledger), ensure_ascii=False), flush=True)
    print(json.dumps({"ledger_total_usd": str(ledger.total_usd()), "limit_usd": str(ledger.config.total_limit_usd)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
