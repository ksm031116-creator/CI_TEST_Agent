"""API spending limit. Every model call must go through `UsageLedger`.

The ledger is an append-only JSONL file. Before a call, `reserve` refuses it if
the worst-case cost would take total spending over the limit. After the call,
`record` stores the actual usage. The limit and prices come from
configs/analysis.toml.
"""

from __future__ import annotations

import json
import tomllib
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

MTOK = Decimal(1_000_000)
# Cache writes cost more than plain input; reads cost less. Without measured
# rates, charge writes at 1.25x and reads at the full input price (never under).
CACHE_WRITE_FACTOR = Decimal("1.25")


class BudgetExceededError(RuntimeError):
    """The call was refused because it could exceed the spending limit."""


@dataclass(frozen=True)
class ModelPrice:
    input_per_mtok: Decimal
    output_per_mtok: Decimal


@dataclass(frozen=True)
class BudgetConfig:
    model: str
    effort: str
    max_output_tokens: int
    total_limit_usd: Decimal
    pricing_date: str
    prices: dict[str, ModelPrice]

    def price(self, model: str) -> ModelPrice:
        try:
            return self.prices[model]
        except KeyError:
            raise BudgetExceededError(f"no price configured for model {model}; refusing to call it") from None


def load_config(path: Path) -> BudgetConfig:
    data = tomllib.loads(path.read_text(encoding="utf-8"))
    prices = {
        name: ModelPrice(Decimal(str(p["input_per_mtok"])), Decimal(str(p["output_per_mtok"])))
        for name, p in data["pricing"]["models"].items()
    }
    limit = Decimal(str(data["budget"]["total_limit_usd"]))
    if limit <= 0:
        raise ValueError("budget.total_limit_usd must be positive")
    return BudgetConfig(
        model=data["model"],
        effort=data["effort"],
        max_output_tokens=int(data["max_output_tokens"]),
        total_limit_usd=limit,
        pricing_date=str(data["pricing"]["date"]),
        prices=prices,
    )


def cost_usd(
    price: ModelPrice,
    input_tokens: int,
    output_tokens: int,
    cache_write_tokens: int = 0,
    cache_read_tokens: int = 0,
) -> Decimal:
    input_cost = (
        Decimal(input_tokens) + Decimal(cache_read_tokens) + Decimal(cache_write_tokens) * CACHE_WRITE_FACTOR
    ) * price.input_per_mtok
    return (input_cost + Decimal(output_tokens) * price.output_per_mtok) / MTOK


def estimate_input_tokens(text: str) -> int:
    """Upper-bound token estimate used only for the pre-call check.

    One token per two UTF-8 bytes overestimates ordinary code and logs, so a
    call that passes the check cannot cost more than was reserved for input.
    """
    return len(text.encode("utf-8")) // 2 + 1


class UsageLedger:
    def __init__(self, path: Path, config: BudgetConfig) -> None:
        self.path = path
        self.config = config

    def entries(self) -> list[dict]:
        if not self.path.exists():
            return []
        return [json.loads(line) for line in self.path.read_text(encoding="utf-8").splitlines() if line.strip()]

    def total_usd(self) -> Decimal:
        return sum((Decimal(e["cost_usd"]) for e in self.entries()), Decimal("0"))

    def remaining_usd(self) -> Decimal:
        return self.config.total_limit_usd - self.total_usd()

    def reserve(
        self,
        model: str,
        prompt_text: str,
        max_output_tokens: int | None = None,
        ceiling_usd: Decimal | None = None,
    ) -> Decimal:
        """Check that the worst case of the next call fits. Returns that worst case.

        `ceiling_usd` is a lower limit on total spending for the current piece of
        work, such as one day's approved amount. The project limit always applies.
        """
        output_tokens = self.config.max_output_tokens if max_output_tokens is None else max_output_tokens
        worst = cost_usd(self.config.price(model), estimate_input_tokens(prompt_text), output_tokens)
        spent = self.total_usd()
        limit = self.config.total_limit_usd
        if ceiling_usd is not None:
            limit = min(limit, ceiling_usd)
        if spent + worst > limit:
            raise BudgetExceededError(
                f"spent ${spent:.4f} of ${limit}; the next call could cost up to ${worst:.4f}"
            )
        return worst

    def record(
        self,
        model: str,
        purpose: str,
        input_tokens: int,
        output_tokens: int,
        cache_write_tokens: int = 0,
        cache_read_tokens: int = 0,
    ) -> Decimal:
        """Append the actual usage of a finished call. Returns its cost."""
        cost = cost_usd(self.config.price(model), input_tokens, output_tokens, cache_write_tokens, cache_read_tokens)
        entry = {
            "at": datetime.now(UTC).isoformat(timespec="seconds"),
            "model": model,
            "purpose": purpose,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "cache_write_tokens": cache_write_tokens,
            "cache_read_tokens": cache_read_tokens,
            "cost_usd": str(cost),
            "pricing_date": self.config.pricing_date,
        }
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8", newline="\n") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        return cost
