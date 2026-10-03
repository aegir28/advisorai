"""Cross-agent review: how the specialists' views relate, topic by topic. Deterministic, and never a vote.

Principles (ADR 0012):
* No majority voting. How many perspectives say something is never evidence that it is true. A row records
  that perspectives cite the same record, or conflict, or flag a gap; strength comes from verification
  statuses of the claims, not from counting specialists.
* Disagreement is preserved. A contradiction a specialist reports, or a claim verification found contradicted,
  becomes a `disagreement` row. Nothing here resolves it.
* Missing evidence is surfaced: every distinct missing-information item raised by any perspective is a row.
* Medication concerns (from the medication review) become `medication_conflict` rows.

The model-written interpretation of these rows happens later, in the interim clinical review; this stage only
establishes the structure, with fixed-text summaries.
"""

import re

from app.evidence.contracts import EvidenceItem
from app.orchestration.wire import make
from app.schemas.common import SpecialistId
from app.schemas.cross_review import (
    CellStance,
    CrossReviewData,
    MatrixPerspective,
    MatrixRelationship,
    MatrixRow,
    MatrixSpecialist,
)
from app.schemas.evidence import Claim
from app.schemas.medication_review import MedicationReview
from app.schemas.specialist_report import SpecialistReport

_SPACE = re.compile(r"\s+")
_CONFLICT_KINDS = {"possible_interaction", "possible_duplication", "documented_conflict"}


def _norm(text: str) -> str:
    return _SPACE.sub(" ", text).strip().casefold()


def cross_review(
    reports: list[SpecialistReport],
    claims: list[Claim],
    evidence: list[EvidenceItem],
    medication_reviews: dict[SpecialistId, MedicationReview] | None = None,
) -> CrossReviewData:
    fact_text = {e.id.removeprefix("ev_"): e.snippet for e in evidence}
    removed = {c.id for c in claims if c.removed}
    claim_by_id = {c.id: c for c in claims}
    rows: list[MatrixRow] = []

    # 1. Record items cited by two or more perspectives (kept separate per perspective).
    cited: dict[str, dict[SpecialistId, list[tuple[str, str]]]] = {}
    for report in reports:
        for finding in [*report.findings, *report.considerations]:
            if f"cl_{report.specialist}_{finding.id}" in removed:
                continue
            for ref in finding.fact_refs:
                cited.setdefault(ref, {}).setdefault(report.specialist, []).append(
                    (finding.id, finding.statement)
                )
    contradicted_refs = {r for c in claims if c.status == "contradicted" for r in c.patient_fact_ids}
    reported_conflict_refs = {ref for rep in reports for con in rep.contradictions for ref in con.between}
    for n, (ref, by_agent) in enumerate(sorted(cited.items()), start=1):
        if len(by_agent) < 2:
            continue
        in_conflict = ref in contradicted_refs or ref in reported_conflict_refs
        statuses = [
            claim_by_id[f"cl_{agent}_{fid}"].status
            for agent, items in by_agent.items()
            for fid, _ in items
            if f"cl_{agent}_{fid}" in claim_by_id
        ]
        relationship: MatrixRelationship = (
            "disagreement"
            if in_conflict
            else "agreement"
            if all(s == "supported" for s in statuses)
            else "partial"
        )
        cells: dict[SpecialistId, CellStance] = {
            a: ("differs" if in_conflict else "supports") for a in by_agent
        }
        rows.append(
            make(
                MatrixRow,
                id=f"mx_rec_{n}",
                topic=f"What the record says: {fact_text.get(ref, ref)[:140]}",
                cells=cells,
                relationship=relationship,
                summary=f"Cited by {len(by_agent)} perspectives. Verification: "
                + ", ".join(f"{s}" for s in sorted(set(statuses)))
                + ". This is not a vote.",
                perspectives=[
                    MatrixPerspective(specialist=a, reasoning=items[0][1][:300])
                    for a, items in by_agent.items()
                ],
                item_ids=[ref, *[fid for items in by_agent.values() for fid, _ in items]],
            )
        )

    # 2. Contradictions the perspectives themselves reported: kept, never resolved.
    for report in reports:
        for con in report.contradictions:
            rows.append(
                make(
                    MatrixRow,
                    id=f"mx_con_{report.specialist}_{con.id}",
                    topic=con.description[:160] or "Two parts of the record conflict",
                    cells={report.specialist: "flags_issue"},
                    relationship="disagreement",
                    summary="A perspective found these parts of the record in conflict. Both are kept.",
                    perspectives=[
                        MatrixPerspective(specialist=report.specialist, reasoning=con.description[:300])
                    ],
                    item_ids=[con.id, *con.between],
                )
            )

    # 3. Missing information, once per distinct item.
    seen: dict[str, tuple[str, list[SpecialistId], list[str]]] = {}
    for report in reports:
        for gap in report.missing_info:
            key = _norm(gap.item)
            text, agents, ids = seen.get(key, (gap.item, [], []))
            seen[key] = (text, [*agents, report.specialist], [*ids, gap.id])
    for n, (text, agents, ids) in enumerate(seen.values(), start=1):
        rows.append(
            make(
                MatrixRow,
                id=f"mx_gap_{n}",
                topic=f"Missing: {text}"[:160],
                cells={a: "flags_issue" for a in agents},
                relationship="missing_info",
                summary=f"Raised by {len(set(agents))} perspective(s). The record does not contain it.",
                perspectives=[
                    MatrixPerspective(specialist=a, reasoning=text[:300]) for a in dict.fromkeys(agents)
                ],
                item_ids=ids,
            )
        )

    # 4. Medication concerns that point at a conflict, a duplication or an interaction.
    for agent, review in (medication_reviews or {}).items():
        for concern in review.concerns:
            if concern.kind in _CONFLICT_KINDS:
                rows.append(
                    make(
                        MatrixRow,
                        id=f"mx_med_{agent}_{concern.id}",
                        topic=concern.statement[:160],
                        cells={agent: "flags_issue"},
                        relationship="medication_conflict",
                        summary="A medication review concern backed by the record or a registered source.",
                        perspectives=[MatrixPerspective(specialist=agent, reasoning=concern.statement[:300])],
                        item_ids=[concern.id, *concern.fact_refs, *concern.source_ids],
                    )
                )

    return CrossReviewData(
        specialists=[MatrixSpecialist(id=r.specialist, name=r.name) for r in reports], rows=rows
    )
