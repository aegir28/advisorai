"""Router infrastructure: registry-aware, strategy-pluggable, guard-railed, with a cap on active agents.

It contains NO clinical routing rules. Which specialties apply to a case is decided by the strategies and
guardrails that are plugged in (a deterministic `RuleStrategy`, an LLM-assisted strategy, or both), by whoever
designs them. With nothing plugged in, the router selects nobody and says why."""
