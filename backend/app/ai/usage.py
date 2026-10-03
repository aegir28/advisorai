"""Usage, cost and budget tracking. One `UsageRecord` per gateway call, never any content.

Cost is integer micro-USD, or None when the model has no price entered yet (unknown, not invented).
"""

import logging
import uuid
from collections import Counter
from dataclasses import dataclass
from typing import Protocol

from sqlalchemy import text

from app.db.database import Database, SystemOperation

logger = logging.getLogger("advisorai.ai")


@dataclass(frozen=True, slots=True)
class UsageRecord:
    purpose: str
    provider: str
    model: str
    tier: int
    input_tokens: int
    output_tokens: int
    cost_micro_usd: int | None
    latency_ms: int
    attempts: int
    outcome: str  # "success" or a short failure code
    request_id: str | None = None
    run_id: str | None = None
    case_id: str | None = None
    owner_user_id: str | None = None
    node_id: str | None = None


class UsageSink(Protocol):
    async def record(self, record: UsageRecord) -> None: ...


class InMemoryUsageSink:
    """For tests and the fake-provider demo."""

    def __init__(self) -> None:
        self.records: list[UsageRecord] = []

    async def record(self, record: UsageRecord) -> None:
        self.records.append(record)

    def total_cost_micro_usd(self) -> int:
        return sum(r.cost_micro_usd or 0 for r in self.records)


_INSERT = text(
    "insert into public.model_usage (owner_user_id, case_id, run_id, node, purpose, provider, model, tier,"
    " input_tokens, output_tokens, cost_micro_usd, latency_ms, attempts, outcome, request_id)"
    " values (:owner, :case, :run, :node, :purpose, :provider, :model, :tier,"
    " :input_tokens, :output_tokens, :cost, :latency_ms, :attempts, :outcome, :request_id)"
)


class PostgresUsageSink:
    """Writes `public.model_usage` on the SYSTEM path (INSERT only). A call with no case context (a demo, a
    health probe) has no row to belong to, so it is counted in metrics but not persisted."""

    def __init__(self, database: Database) -> None:
        self._database = database

    async def record(self, record: UsageRecord) -> None:
        if record.case_id is None or record.owner_user_id is None:
            return
        try:
            async with self._database.system_session(SystemOperation.AI_USAGE_RECORD) as connection:
                await connection.execute(
                    _INSERT,
                    {
                        "owner": uuid.UUID(record.owner_user_id),
                        "case": uuid.UUID(record.case_id),
                        "run": uuid.UUID(record.run_id) if record.run_id else None,
                        "node": record.node_id,
                        "purpose": record.purpose,
                        "provider": record.provider,
                        "model": record.model,
                        "tier": record.tier,
                        "input_tokens": record.input_tokens,
                        "output_tokens": record.output_tokens,
                        "cost": record.cost_micro_usd,
                        "latency_ms": record.latency_ms,
                        "attempts": record.attempts,
                        "outcome": record.outcome,
                        "request_id": record.request_id,
                    },
                )
        except Exception:
            # A ledger failure must not turn a successful call into a failed step; it is loud in the logs.
            logger.error("model_usage write failed (request %s)", record.request_id, exc_info=True)


class RunBudget:
    """Per-run spend cap in micro-USD. Checked before every call; charged after. 0 disables the cap."""

    def __init__(self, cap_micro_usd: int) -> None:
        self._cap = cap_micro_usd
        self._spent: Counter[str] = Counter()

    def exceeded(self, run_id: str | None) -> bool:
        return bool(self._cap) and run_id is not None and self._spent[run_id] >= self._cap

    def charge(self, run_id: str | None, micro_usd: int | None) -> None:
        if run_id is not None and micro_usd:
            self._spent[run_id] += micro_usd

    def spent(self, run_id: str) -> int:
        return self._spent[run_id]


class AIMetrics:
    """Process-local counters for observability (docs/observability.md). Counts and sums only."""

    def __init__(self) -> None:
        self.counters: Counter[str] = Counter()

    def incr(self, name: str, by: int = 1) -> None:
        self.counters[name] += by

    def snapshot(self) -> dict[str, int]:
        return dict(sorted(self.counters.items()))
