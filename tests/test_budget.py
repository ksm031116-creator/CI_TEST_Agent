from decimal import Decimal
from pathlib import Path

import pytest

from ci_failure_analyzer.analysis.budget import (
    BudgetConfig,
    BudgetExceededError,
    ModelPrice,
    UsageLedger,
    cost_usd,
    estimate_input_tokens,
    load_config,
)

REPO_CONFIG = Path(__file__).parent.parent / "configs" / "analysis.toml"
PRICE = ModelPrice(Decimal("4"), Decimal("20"))


def config(limit: str) -> BudgetConfig:
    return BudgetConfig(
        model="m",
        max_output_tokens=1000,
        total_limit_usd=Decimal(limit),
        pricing_date="2026-11-03",
        prices={"m": PRICE},
    )


def test_repository_config_sets_the_agreed_limit_and_model():
    loaded = load_config(REPO_CONFIG)
    assert loaded.total_limit_usd == Decimal("100")
    assert loaded.model in loaded.prices


def test_cost_of_one_analysis():
    assert cost_usd(PRICE, 8000, 4000) == Decimal("0.112")


def test_cache_tokens_are_never_charged_below_input_price():
    assert cost_usd(PRICE, 0, 0, cache_write_tokens=1_000_000) == Decimal("5")
    assert cost_usd(PRICE, 0, 0, cache_read_tokens=1_000_000) == Decimal("4")


def test_input_estimate_is_an_upper_bound_for_ascii_text():
    assert estimate_input_tokens("x" * 1000) == 501


def test_new_ledger_is_empty(tmp_path):
    ledger = UsageLedger(tmp_path / "usage.jsonl", config("100"))
    assert ledger.total_usd() == Decimal("0")
    assert ledger.remaining_usd() == Decimal("100")


def test_recorded_usage_accumulates_across_instances(tmp_path):
    path = tmp_path / "data" / "usage.jsonl"
    assert UsageLedger(path, config("100")).record("m", "case-001/A", 8000, 4000) == Decimal("0.112")
    UsageLedger(path, config("100")).record("m", "case-001/B", 8000, 4000)
    ledger = UsageLedger(path, config("100"))
    assert ledger.total_usd() == Decimal("0.224")
    assert [e["purpose"] for e in ledger.entries()] == ["case-001/A", "case-001/B"]


def test_call_within_the_limit_is_allowed(tmp_path):
    ledger = UsageLedger(tmp_path / "usage.jsonl", config("100"))
    # 501 input tokens and 1000 output tokens at the worst case.
    assert ledger.reserve("m", "x" * 1000) == cost_usd(PRICE, 501, 1000)


def test_call_that_could_cross_the_limit_is_refused(tmp_path):
    ledger = UsageLedger(tmp_path / "usage.jsonl", config("0.05"))
    ledger.record("m", "earlier", 5000, 1000)  # $0.04 spent
    with pytest.raises(BudgetExceededError, match="spent"):
        ledger.reserve("m", "x" * 1000)  # worst case about $0.022


def test_refused_call_records_nothing(tmp_path):
    ledger = UsageLedger(tmp_path / "usage.jsonl", config("0.001"))
    with pytest.raises(BudgetExceededError):
        ledger.reserve("m", "x" * 1000)
    assert ledger.entries() == []


def test_model_without_a_price_is_refused(tmp_path):
    ledger = UsageLedger(tmp_path / "usage.jsonl", config("100"))
    with pytest.raises(BudgetExceededError, match="no price"):
        ledger.reserve("other-model", "prompt")


def test_non_positive_limit_is_rejected(tmp_path):
    text = REPO_CONFIG.read_text(encoding="utf-8").replace("total_limit_usd = 100", "total_limit_usd = 0")
    path = tmp_path / "analysis.toml"
    path.write_text(text, encoding="utf-8")
    with pytest.raises(ValueError):
        load_config(path)
