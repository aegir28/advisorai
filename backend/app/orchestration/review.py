"""The interim clinical review: from verified specialist claims to a structured synthesis.

The reviewer is an AI and says so. It is not a doctor, issues no diagnosis and no instruction. What this module
guarantees, whatever a reviewer model returns:

1. Only claims that survived verification can be used. An item that rests on a removed claim, or on an id that
   does not exist, is dropped (never repaired by guessing).
2. Every item is linted (`output_lint`): no stop/start/change, no "doctor is wrong", no winner, no unsupported
   certainty, no invented citation.
3. Disagreement and missing information are PRESERVED by construction: any cross-review row of those kinds
   that no reviewer item covers is added back as a fixed-text item. A model cannot smooth a conflict away.
4. If the reviewer is unavailable or unusable, a fallback synthesis is assembled from the verified claims
   themselves (`produced_by: "fallback"`): nothing is invented and the pipeline continues.
"""

from collections.abc import Iterable

from app.orchestration.contracts import ReviewItem, ReviewModelOutput, SynthesisArtifact
from app.orchestration.wire import make
from app.safety.output_lint import TextKind, lint_text
from app.schemas.cross_review import CrossReviewData
from app.schemas.evidence import Claim
from app.schemas.specialist_report import SpecialistReport
from app.schemas.synthesis import RubricRow, Synthesis, SynthesisGroup, SynthesisItem, SynthesisReviewer

RUBRIC = [
    RubricRow(factor="Evidence from your own documents comes first", weight="highest"),
    RubricRow(factor="How well each statement was checked against the record", weight="high"),
    RubricRow(factor="Disagreements are kept visible, never voted away", weight="fixed"),
    RubricRow(factor="Missing information and uncertainty are stated, not filled in", weight="fixed"),
]
# Which report sections a synthesis group may be placed in (a reviewer's hint must be one of these).
SECTIONS_FOR_GROUP: dict[str, tuple[int, ...]] = {
    "fact": (1, 2, 4, 6, 7),
    "interpretation": (8, 9, 11),
    "agreement": (13,),
    "disagreement": (14,),
    "missing": (10,),
    "uncertainty": (9,),
    "clarification": (11, 17),
    "medication": (6, 11),
    "proposal": (7,),
}
_STATUS_CONFIDENCE = {"supported": "high", "partially_supported": "moderate", "unclear": "low"}


def usable(claims: Iterable[Claim]) -> list[Claim]:
    return [c for c in claims if not c.removed]


def known_ids(
    claims: Iterable[Claim], cross: CrossReviewData, reports: Iterable[SpecialistReport]
) -> tuple[set[str], set[str]]:
    """(ids a reviewer item may cite, ids of removed claims it may not)."""
    claims = list(claims)
    ok: set[str] = {c.id for c in claims if not c.removed}
    for c in claims:
        if not c.removed:
            ok.update(c.patient_fact_ids)
            ok.update(c.external_source_ids)
    for row in cross.rows:
        ok.add(row.id)
        ok.update(row.item_ids)
    for r in reports:
        for u in r.uncertainties:
            ok.add(f"unc_{r.specialist}_{u.id}")
        for m in r.missing_info:
            ok.add(f"miss_{r.specialist}_{m.id}")
    removed = {c.id for c in claims if c.removed}
    return ok - removed, removed


def validate_items(
    items: Iterable[ReviewItem], claims: list[Claim], ok_ids: set[str], removed_ids: set[str]
) -> tuple[list[ReviewItem], dict[str, int]]:
    claim_by_id = {c.id: c for c in claims}
    kept: list[ReviewItem] = []
    dropped: dict[str, int] = {}
    seen: set[str] = set()

    def drop(code: str) -> None:
        dropped[code] = dropped.get(code, 0) + 1

    for item in items:
        if any(d in removed_ids for d in item.derived_from):
            drop("uses_removed_claim")
            continue
        if not all(d in ok_ids for d in item.derived_from):
            drop("unknown_source_id")
            continue
        kind: TextKind = item.kind
        if lint_text(item.text, kind):
            drop("unsafe_text")
            continue
        norm = " ".join(item.text.casefold().split())
        if norm in seen:
            drop("duplicate")
            continue
        seen.add(norm)
        cited_claims = [claim_by_id[d] for d in item.derived_from if d in claim_by_id]
        if item.kind == "external_evidence" and not any(c.external_source_ids for c in cited_claims):
            drop("external_without_source")
            continue
        if item.kind == "patient_fact" and not (
            any(c.patient_fact_ids for c in cited_claims)
            or any(d.startswith("f_") or d in ok_ids for d in item.derived_from)
        ):
            item = item.model_copy(update={"kind": "interpretation"})
        kept.append(item)
    return kept, dropped


def fallback_items(claims: list[Claim]) -> list[ReviewItem]:
    out: list[ReviewItem] = []
    for c in usable(claims):
        group: SynthesisGroup = "fact" if c.kind == "patient_fact" else "interpretation"
        out.append(
            make(
                ReviewItem,
                text=c.text,
                kind=c.kind,
                group=group,
                confidence=_STATUS_CONFIDENCE.get(c.status, "low"),
                flag="uncertain" if c.status == "unclear" else None,
                derived_from=[c.id],
            )
        )
    return out


def _covered(row_ids: set[str], items: Iterable[ReviewItem], groups: set[str]) -> bool:
    return any(i.group in groups and row_ids & set(i.derived_from) for i in items)


def preserve(items: list[ReviewItem], cross: CrossReviewData) -> list[ReviewItem]:
    """Add back, as fixed-text items, every disagreement / medication conflict / missing item the reviewer left out."""
    out = list(items)
    for row in cross.rows:
        ids = {row.id, *row.item_ids}
        if row.relationship == "disagreement" and not _covered(ids, out, {"disagreement"}):
            out.append(
                make(
                    ReviewItem,
                    text=f"Records or perspectives differ here, and both views are kept: {row.topic}",
                    kind="interpretation",
                    group="disagreement",
                    confidence="moderate",
                    flag="disagreement",
                    derived_from=[row.id],
                )
            )
        elif row.relationship == "medication_conflict" and not _covered(ids, out, {"medication"}):
            out.append(
                make(
                    ReviewItem,
                    text=f"A medicine point to discuss with your prescriber: {row.topic}",
                    kind="interpretation",
                    group="medication",
                    confidence="moderate",
                    derived_from=[row.id],
                )
            )
        elif row.relationship == "missing_info" and not _covered(ids, out, {"missing"}):
            out.append(
                make(
                    ReviewItem,
                    text=row.topic.replace("Missing: ", "Not in your records: ", 1),
                    kind="interpretation",
                    group="missing",
                    confidence="high",
                    flag="missing",
                    derived_from=[row.id],
                )
            )
    return out


def assemble(
    run_id: str,
    items: list[ReviewItem],
    cross: CrossReviewData,
    *,
    produced_by: str,
    reviewer: SynthesisReviewer,
    dropped: dict[str, int],
) -> SynthesisArtifact:
    final = preserve(items, cross)
    syn_items: list[SynthesisItem] = []
    hints: dict[str, int] = {}
    for n, item in enumerate(final, start=1):
        sid = f"syn_{n}"
        syn_items.append(
            make(
                SynthesisItem,
                id=sid,
                text=item.text,
                kind=item.kind,
                group=item.group,
                confidence=item.confidence,
                flag=item.flag,
                derived_from=item.derived_from,
                impact=item.impact,
            )
        )
        if item.section is not None and item.section in SECTIONS_FOR_GROUP.get(item.group, ()):
            hints[sid] = item.section
    return SynthesisArtifact(
        schema_version="synthesis_artifact.v1",
        synthesis=Synthesis(id=f"synthesis_{run_id}", reviewer=reviewer, items=syn_items, rubric=RUBRIC),
        section_hints=hints,
        produced_by="model" if produced_by == "model" else "fallback",
        dropped=dropped,
    )


def model_output_items(output: ReviewModelOutput) -> list[ReviewItem]:
    return list(output.items)
