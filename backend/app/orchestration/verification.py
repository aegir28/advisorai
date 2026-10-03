"""Evidence verification: every specialist claim is checked against the record it cites.

This is the deterministic floor, and it never needs a model. For each claim it asks: does it cite anything that
exists, does the cited text actually share the claim's content, and do the claim's numbers appear in the cited
record? The answer is one of the contract's statuses:

  supported             cited record exists and clearly contains what the claim says
  partially_supported   cited record exists and overlaps, or the claim is an interpretation of it
  unclear               cited record exists but the overlap is too thin to say
  contradicted          a number in the claim is not in the cited record although the rest overlaps
  insufficient_evidence nothing valid is cited (or an external claim has no registered source)

`insufficient_evidence` and `contradicted` claims are REMOVED: they are kept in the evidence page with the
reason so people see what was filtered, but they never reach the synthesis or the patient report. `unclear`
claims survive only as flagged uncertainty. An optional model verifier (through the gateway, policy-enabled)
may refine `unclear`/`partially_supported`; it can never promote an `insufficient_evidence` or `contradicted`
claim, so the floor holds whatever a model says.
"""

import re
from collections.abc import Collection, Mapping
from dataclasses import dataclass

from app.evidence.contracts import EvidenceItem
from app.orchestration.contracts import VerificationModelResult
from app.orchestration.wire import make
from app.schemas.common import FactKind, SpecialistId, VerificationStatus
from app.schemas.evidence import Claim
from app.schemas.specialist_report import SpecialistReport

_WORD = re.compile(r"[a-z][a-z0-9'-]*")
_NUMBER = re.compile(r"\d+(?:\.\d+)?")
_STOP = frozenset(
    [
        "a",
        "an",
        "and",
        "are",
        "as",
        "at",
        "be",
        "been",
        "by",
        "for",
        "from",
        "has",
        "have",
        "in",
        "is",
        "it",
        "its",
        "of",
        "on",
        "or",
        "that",
        "the",
        "their",
        "this",
        "to",
        "was",
        "were",
        "with",
        "you",
        "your",
        "yours",
        "i",
        "we",
        "they",
        "he",
        "she",
        "them",
        "his",
        "her",
        "our",
        "not",
        "no",
        "may",
        "might",
        "can",
        "could",
        "would",
        "should",
        "will",
        "than",
        "then",
        "there",
        "these",
        "those",
        "which",
        "who",
        "whom",
        "what",
        "when",
        "where",
        "while",
        "about",
        "above",
        "after",
        "again",
        "also",
        "any",
        "because",
        "before",
        "between",
        "both",
        "but",
        "do",
        "does",
        "did",
        "each",
        "few",
        "more",
        "most",
        "other",
        "some",
        "such",
        "only",
        "own",
        "same",
        "so",
        "too",
        "very",
    ]
)
SUPPORT_REMOVED = frozenset({"insufficient_evidence", "contradicted"})
# Overlap thresholds (share of the claim's content words found in the cited evidence).
FULL, PARTIAL = 0.6, 0.25


def content_words(text: str) -> set[str]:
    return {w.strip("'-") for w in _WORD.findall(text.lower()) if w not in _STOP and len(w) > 2}


def _numbers(text: str) -> set[str]:
    """The numbers a statement commits to. A lone digit ("type 2", "stage 3", "once") is a label, not a
    measurement, so it is not compared; a wrong measurement ("8.2" vs "11.9", "500" vs "50") still is."""
    found = {n.rstrip("0").rstrip(".") if "." in n else n for n in _NUMBER.findall(text)}
    return {n for n in found if len(n) > 1}


@dataclass(frozen=True, slots=True)
class Verdict:
    status: VerificationStatus
    rationale: str


def judge(
    text: str,
    kind: FactKind,
    fact_refs: Collection[str],
    source_ids: Collection[str],
    evidence_by_fact: Mapping[str, EvidenceItem],
    known_sources: Collection[str],
    record_text: Mapping[str, str] | None = None,
) -> tuple[Verdict, list[str], list[str]]:
    """(verdict, valid fact ids, valid source ids)."""
    facts = [f for f in dict.fromkeys(fact_refs) if f in evidence_by_fact]
    sources = [s for s in dict.fromkeys(source_ids) if s in known_sources]
    if kind == "external_evidence":
        if not sources:
            return Verdict("insufficient_evidence", "No registered external source is cited."), facts, sources
        return (
            Verdict("unclear", "A registered source is cited; its content is not checked automatically."),
            facts,
            sources,
        )
    if not facts:
        return Verdict("insufficient_evidence", "No record item that exists is cited."), facts, sources

    # The quoted snippet plus what the structured record says about the same fact (value, unit, date): a
    # claim is checked against everything the record holds for the facts it cites, not only the quote.
    evidence_text = " ".join(f"{evidence_by_fact[f].snippet} {(record_text or {}).get(f, '')}" for f in facts)
    claim_words = content_words(text)
    overlap = len(claim_words & content_words(evidence_text)) / max(len(claim_words), 1)
    claim_numbers, evidence_numbers = _numbers(text), _numbers(evidence_text)
    if claim_numbers and evidence_numbers and not claim_numbers <= evidence_numbers:
        if overlap >= 0.3:
            return (
                Verdict("contradicted", "A number in the statement does not match the cited record."),
                facts,
                sources,
            )
        return (
            Verdict("unclear", "The cited record does not clearly contain the stated numbers."),
            facts,
            sources,
        )
    if overlap >= FULL:
        status: VerificationStatus = "supported" if kind == "patient_fact" else "partially_supported"
        return Verdict(status, "The cited record contains what the statement says."), facts, sources
    if overlap >= PARTIAL:
        return Verdict("partially_supported", "The cited record overlaps with the statement."), facts, sources
    return Verdict("unclear", "The cited record shares little with the statement."), facts, sources


def claims_from_reports(
    reports: list[SpecialistReport],
    evidence: list[EvidenceItem],
    known_sources: Collection[str] = (),
    *,
    medication_concerns: Mapping[SpecialistId, list[tuple[str, str, list[str], list[str]]]] | None = None,
    record_text: Mapping[str, str] | None = None,
) -> list[Claim]:
    """One `Claim` per finding/consideration of every usable report (and per medication concern)."""
    by_fact = {e.id.removeprefix("ev_"): e for e in evidence}
    claims: list[Claim] = []
    for report in reports:
        for finding in [*report.findings, *report.considerations]:
            claims.append(
                _claim(
                    f"cl_{report.specialist}_{finding.id}",
                    finding.statement,
                    finding.kind,
                    report.specialist,
                    finding.fact_refs,
                    finding.source_ids or [],
                    by_fact,
                    known_sources,
                    record_text,
                )
            )
    for agent, concerns in (medication_concerns or {}).items():
        for cid, statement, fact_refs, source_ids in concerns:
            kind: FactKind = "external_evidence" if source_ids and not fact_refs else "interpretation"
            claims.append(
                _claim(
                    f"cl_{agent}_{cid}",
                    statement,
                    kind,
                    agent,
                    fact_refs,
                    source_ids,
                    by_fact,
                    known_sources,
                    record_text,
                )
            )
    return claims


def _claim(
    claim_id: str,
    text: str,
    kind: FactKind,
    agent: SpecialistId,
    fact_refs: Collection[str],
    source_ids: Collection[str],
    by_fact: Mapping[str, EvidenceItem],
    known_sources: Collection[str],
    record_text: Mapping[str, str] | None = None,
) -> Claim:
    verdict, facts, sources = judge(text, kind, fact_refs, source_ids, by_fact, known_sources, record_text)
    removed = verdict.status in SUPPORT_REMOVED
    return make(
        Claim,
        id=claim_id,
        text=text,
        kind=kind,
        agent=agent,
        status=verdict.status,
        rationale=verdict.rationale,
        patient_fact_ids=facts,
        external_source_ids=sources,
        removed=True if removed else None,
        removal_reason=("Removed before the report: " + verdict.rationale) if removed else None,
    )


def apply_model_results(claims: list[Claim], results: list[VerificationModelResult]) -> list[Claim]:
    """Fold a verification model's refinements in, under the floor: it may only move an `unclear` or
    `partially_supported` claim between those and `supported`/`unclear`/`contradicted`; it can never revive a
    removed claim, and it can never name a claim that does not exist."""
    by_id = {r.claim_id: r for r in results}
    out: list[Claim] = []
    for claim in claims:
        result = by_id.get(claim.id)
        if result is None or claim.removed or claim.status not in {"unclear", "partially_supported"}:
            out.append(claim)
            continue
        if result.status == "insufficient_evidence":
            out.append(claim)  # a model cannot make a cited claim "uncited"
            continue
        removed = result.status == "contradicted"
        out.append(
            claim.model_copy(
                update={
                    "status": result.status,
                    "rationale": result.rationale,
                    "removed": True if removed else None,
                    "removal_reason": ("Removed before the report: " + result.rationale) if removed else None,
                }
            )
        )
    return out


def counts(claims: list[Claim]) -> dict[str, int]:
    out: dict[str, int] = {}
    for claim in claims:
        out[claim.status] = out.get(claim.status, 0) + 1
    out["removed"] = sum(1 for c in claims if c.removed)
    return out
