"""Structural verification of claims: deterministic, no model. It checks that a claim's status is consistent
with
what it cites and that everything cited exists. Whether a cited passage truly SUPPORTS a claim is a judgement
for the (later) verifier; this is the floor under it."""

from collections.abc import Collection

from app.schemas.evidence import Claim

SUPPORT_STATUSES = {"supported", "partially_supported"}


def check_claim_structure(
    claim: Claim, known_fact_ids: Collection[str], known_source_ids: Collection[str]
) -> list[str]:
    """Violation codes for one claim (empty = structurally sound)."""
    problems: list[str] = []
    cited = [*claim.patient_fact_ids, *claim.external_source_ids]
    if claim.status in SUPPORT_STATUSES and not cited:
        problems.append("supported_without_citation")
    problems.extend(f"unknown_fact:{i}" for i in claim.patient_fact_ids if i not in known_fact_ids)
    problems.extend(f"unknown_source:{i}" for i in claim.external_source_ids if i not in known_source_ids)
    if (
        claim.kind == "external_evidence"
        and claim.status in SUPPORT_STATUSES
        and not claim.external_source_ids
    ):
        problems.append("external_claim_without_source")
    if claim.removed and not (claim.removal_reason or "").strip():
        problems.append("removed_without_reason")
    if claim.status in SUPPORT_STATUSES and claim.removed:
        problems.append("removed_but_supported")
    return problems
