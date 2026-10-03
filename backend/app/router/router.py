"""The router pipeline: strategies propose -> merge -> registry filter -> guardrails -> cap -> plan.

Nothing here knows a specialty's clinical meaning. Everything it decides is mechanical and explained in
`RoutingDecision.trace`: a disabled agent is dropped, a guardrail removes a candidate, the active-agent cap
drops the lowest-ranked optional ones first. A mandatory candidate is never dropped silently: if there are
more mandatory candidates than the cap allows, routing fails loudly (`too_many_mandatory`).
"""

from collections.abc import Sequence

from app.agents.registry import SpecialtyRegistry
from app.router.contracts import (
    Candidate,
    Guardrail,
    Priority,
    RouterInput,
    RoutingDecision,
    RoutingError,
    RoutingStrategy,
)
from app.schemas.routing import RoutingNotSelected, RoutingPlan, RoutingSelection


class Router:
    def __init__(
        self,
        registry: SpecialtyRegistry,
        strategies: Sequence[RoutingStrategy] = (),
        guardrails: Sequence[Guardrail] = (),
        *,
        max_active_agents: int = 5,
    ) -> None:
        if max_active_agents < 1:
            raise ValueError("max_active_agents must be at least 1")
        self._registry = registry
        self._strategies = list(strategies)
        self._guardrails = list(guardrails)
        self._max_active = max_active_agents

    async def route(self, routing_input: RouterInput) -> RoutingDecision:
        trace: list[str] = []
        missing: list[str] = []
        proposed: list[Candidate] = []

        if not self._strategies:
            trace.append("no routing strategy is configured")
            missing.append("No routing rules are configured yet.")
        for strategy in self._strategies:
            try:
                proposal = await strategy.propose(routing_input)
            except Exception as exc:
                # Type only: the message could contain case content.
                trace.append(f"strategy {strategy.name} failed ({type(exc).__name__})")
                raise RoutingError("strategy_failed") from None
            trace.append(f"strategy {strategy.name} proposed {len(proposal.candidates)}")
            proposed.extend(proposal.candidates)
            missing.extend(proposal.missing)

        merged = self._merge(proposed)
        not_selected: list[RoutingNotSelected] = []

        kept: list[Candidate] = []
        for candidate in merged:
            if self._registry.is_enabled(candidate.specialty):
                kept.append(candidate)
            else:
                not_selected.append(RoutingNotSelected(name=candidate.specialty, why="agent is not enabled"))
                trace.append(f"dropped {candidate.specialty}: not registered/enabled")

        for guardrail in self._guardrails:
            before = {c.specialty for c in kept}
            outcome = guardrail.apply(kept, routing_input)
            kept = list(outcome.candidates)
            for specialty in sorted(before - {c.specialty for c in kept}):
                note = "; ".join(outcome.notes) or "removed by guardrail"
                not_selected.append(RoutingNotSelected(name=specialty, why=f"{guardrail.name}: {note}"))
            trace.extend(f"guardrail {guardrail.name}: {n}" for n in outcome.notes)

        kept, capped = self._cap(kept)
        for dropped in capped:
            not_selected.append(RoutingNotSelected(name=dropped.specialty, why="active-agent limit reached"))
            trace.append(f"dropped {dropped.specialty}: active-agent limit ({self._max_active})")

        plan = RoutingPlan(
            selected=[
                RoutingSelection(specialist=c.specialty, priority=c.priority, reason=c.reason) for c in kept
            ],
            not_selected=not_selected,
            missing_for_routing=list(dict.fromkeys(missing)),
        )
        return RoutingDecision(plan=plan, trace=trace)

    @staticmethod
    def _merge(candidates: Sequence[Candidate]) -> list[Candidate]:
        """One entry per specialty, in first-seen order. Mandatory beats optional; reasons are joined."""
        merged: dict[str, Candidate] = {}
        for c in candidates:
            existing = merged.get(c.specialty)
            if existing is None:
                merged[c.specialty] = c
                continue
            priority: Priority = "mandatory" if "mandatory" in (existing.priority, c.priority) else "optional"
            reason = existing.reason if c.reason in existing.reason else f"{existing.reason}; {c.reason}"
            merged[c.specialty] = Candidate(
                existing.specialty, priority, reason, f"{existing.proposed_by}+{c.proposed_by}"
            )
        return list(merged.values())

    def _cap(self, candidates: list[Candidate]) -> tuple[list[Candidate], list[Candidate]]:
        mandatory = [c for c in candidates if c.priority == "mandatory"]
        if len(mandatory) > self._max_active:
            raise RoutingError("too_many_mandatory")
        room = self._max_active - len(mandatory)
        optional = [c for c in candidates if c.priority == "optional"]
        keep_optional = optional[:room]
        keep_ids = {id(c) for c in mandatory} | {id(c) for c in keep_optional}
        kept = [c for c in candidates if id(c) in keep_ids]  # original order
        return kept, [c for c in candidates if id(c) not in keep_ids]
