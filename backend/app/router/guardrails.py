"""Generic guardrails. They enforce structure (every selection explains itself, only allowed specialties),
never
clinical content."""

from collections.abc import Collection, Sequence

from app.router.contracts import Candidate, GuardrailOutcome, RouterInput


class RequireReasonGuardrail:
    """Drops any candidate that does not say why it was chosen: an unexplained selection is not auditable."""

    name = "require_reason"

    def apply(self, candidates: Sequence[Candidate], routing_input: RouterInput) -> GuardrailOutcome:
        del routing_input
        kept = [c for c in candidates if c.reason.strip()]
        notes = [f"dropped {c.specialty}: no reason given" for c in candidates if not c.reason.strip()]
        return GuardrailOutcome(kept, notes)


class AllowedSpecialtiesGuardrail:
    """Restricts routing to an explicit allow-list (for example while only some agents are ready)."""

    name = "allowed_specialties"

    def __init__(self, allowed: Collection[str]) -> None:
        self._allowed = set(allowed)

    def apply(self, candidates: Sequence[Candidate], routing_input: RouterInput) -> GuardrailOutcome:
        del routing_input
        kept = [c for c in candidates if c.specialty in self._allowed]
        notes = [
            f"dropped {c.specialty}: not on the allow-list"
            for c in candidates
            if c.specialty not in self._allowed
        ]
        return GuardrailOutcome(kept, notes)
