"""Spend control for the whole prototype, not just one run.

The prototype has a fixed model budget (INR 5,000 at the time of writing, a configuration value). Three
layers cooperate, all in integer micro-USD:

* `RunBudget` (usage.py): a per-run cap, so one runaway case cannot spend the whole budget.
* `LedgerBudgetGuard` (here): a cap on CUMULATIVE spend, read from the `model_usage` ledger, with a reserve
  kept back, alerts as the budget is consumed, and a hard stop. Every call reserves its worst-case cost BEFORE
  it is made (input estimate + the maximum output tokens), so parallel specialist calls cannot overshoot.
* a per-call cap (`GatewayRequest.max_call_cost_micro_usd`, from the agent's registry entry).

A model whose price is not entered has an unknown cost, and unknown cost cannot be budgeted: while a guard is
active such a call is refused (`budget_unpriced_model`) instead of being waved through.
"""

import asyncio
import itertools
import logging
import math
from dataclasses import dataclass
from decimal import Decimal
from typing import Protocol

from app.ai.types import GatewayError
from app.ai.usage import AIMetrics

logger = logging.getLogger("advisorai.ai")
_MICROS = 1_000_000


def inr_to_micro_usd(inr: Decimal, inr_per_usd: Decimal) -> int:
    """Budget in rupees to integer micro-USD at an explicit, configured exchange rate."""
    if inr_per_usd <= 0:
        raise ValueError("inr_per_usd must be positive")
    return int(inr / inr_per_usd * _MICROS)


def estimate_input_tokens(text: str) -> int:
    """Conservative (over-)estimate: one token per three characters."""
    return max(1, math.ceil(len(text) / 3))


class SpendReader(Protocol):
    async def total_micro_usd(self) -> int:
        """Cumulative recorded spend (priced calls only)."""
        ...


class InMemorySpendReader:
    """Reads an in-memory usage sink (tests and the fake-provider demo)."""

    def __init__(self, sink: "HasTotal") -> None:
        self._sink = sink

    async def total_micro_usd(self) -> int:
        return self._sink.total_cost_micro_usd()


class HasTotal(Protocol):
    def total_cost_micro_usd(self) -> int: ...


class BudgetGuard(Protocol):
    async def reserve(self, estimated_micro_usd: int | None) -> int:
        """Reserve the worst-case cost of one call. Raises GatewayError when the budget would be exceeded."""
        ...

    def release(self, reservation: int) -> None: ...


@dataclass(frozen=True, slots=True)
class BudgetStatus:
    cap_micro_usd: int
    reserve_micro_usd: int
    spent_micro_usd: int
    in_flight_micro_usd: int

    @property
    def usable_micro_usd(self) -> int:
        return self.cap_micro_usd - self.reserve_micro_usd

    @property
    def fraction_used(self) -> float:
        return self.spent_micro_usd / self.usable_micro_usd if self.usable_micro_usd else 1.0


class LedgerBudgetGuard:
    def __init__(
        self,
        cap_micro_usd: int,
        reader: SpendReader,
        *,
        reserve_fraction: float = 0.10,
        alert_fractions: tuple[float, ...] = (0.5, 0.8, 0.95),
        metrics: AIMetrics | None = None,
    ) -> None:
        if cap_micro_usd <= 0 or not 0 <= reserve_fraction < 1:
            raise ValueError("a positive cap and a reserve fraction in [0, 1) are required")
        self._cap = cap_micro_usd
        self._reserve = int(cap_micro_usd * reserve_fraction)
        self._reader = reader
        self._alerts = sorted(alert_fractions)
        self._alerted: set[float] = set()
        self._metrics = metrics or AIMetrics()
        self._lock = asyncio.Lock()
        self._reservations: dict[int, int] = {}
        self._ids = itertools.count(1)

    async def status(self) -> BudgetStatus:
        return BudgetStatus(
            self._cap, self._reserve, await self._reader.total_micro_usd(), sum(self._reservations.values())
        )

    async def reserve(self, estimated_micro_usd: int | None) -> int:
        if estimated_micro_usd is None:
            self._metrics.incr("budget_unpriced_refused")
            raise GatewayError("budget_unpriced_model")
        async with self._lock:
            status = await self.status()
            self._alert(status)
            if (
                status.spent_micro_usd + status.in_flight_micro_usd + estimated_micro_usd
                > status.usable_micro_usd
            ):
                self._metrics.incr("budget_total_refused")
                logger.warning("model budget stop: the next call would pass the usable budget")
                raise GatewayError("total_budget_exceeded")
            token = next(self._ids)
            self._reservations[token] = estimated_micro_usd
            return token

    def release(self, reservation: int) -> None:
        self._reservations.pop(reservation, None)

    def _alert(self, status: BudgetStatus) -> None:
        for fraction in self._alerts:
            if status.fraction_used >= fraction and fraction not in self._alerted:
                self._alerted.add(fraction)
                self._metrics.incr(f"budget_alert_{int(fraction * 100)}")
                logger.warning("model budget alert: %d%% of the usable budget is spent", int(fraction * 100))
