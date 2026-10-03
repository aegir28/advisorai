"""Second-opinion comparison: rows from the model, validated; no winner, no scoring, no advice to switch.

The `Comparison` contract has no field that could carry a verdict. This module additionally lints every row's
text, drops rows that cite unknown ids, and downgrades a claimed `agreement` to `unresolved` when either side
has no evidence behind it, so a comparison never looks more settled than the record allows.
"""

from collections.abc import Collection

from app.orchestration.contracts import ComparisonModelOutput
from app.orchestration.wire import make
from app.safety.output_lint import lint_text
from app.schemas.comparison import Comparison, ComparisonRow, NextQuestion

MAX_ROWS = 30


def build_comparison(
    output: ComparisonModelOutput,
    known_ids: Collection[str],
    *,
    label_a: str,
    label_b: str,
) -> tuple[Comparison, dict[str, int]]:
    rows: list[ComparisonRow] = []
    dropped: dict[str, int] = {}

    def drop(code: str) -> None:
        dropped[code] = dropped.get(code, 0) + 1

    for n, r in enumerate(output.rows[:MAX_ROWS], start=1):
        cited = [*r.evidence_a, *r.evidence_b, *r.item_ids]
        if any(c not in known_ids for c in cited):
            drop("unknown_id")
            continue
        if any(lint_text(t) for t in (r.topic, r.opinion_a, r.opinion_b)):
            drop("unsafe_text")
            continue
        relationship = r.relationship
        if relationship == "agreement" and not (r.evidence_a and r.evidence_b):
            relationship = "unresolved"
            drop("agreement_downgraded")
        rows.append(
            make(
                ComparisonRow,
                id=f"cmp_{n}",
                topic=r.topic,
                opinion_a=r.opinion_a,
                opinion_b=r.opinion_b,
                evidence_a=r.evidence_a,
                evidence_b=r.evidence_b,
                relationship=relationship,
                item_ids=r.item_ids,
            )
        )
    questions: list[NextQuestion] = []
    for q in output.next_questions:
        if (
            not q.text.rstrip().endswith("?")
            or lint_text(q.text)
            or any(i not in known_ids for i in q.linked_item_ids)
        ):
            drop("question_dropped")
            continue
        questions.append(NextQuestion(audience=q.audience, text=q.text, item_ids=q.linked_item_ids))
    return (
        Comparison(
            opinion_a_label=label_a,
            opinion_b_label=label_b,
            rows=rows,
            next_questions=questions,
            answered_by_opinion=[],
        ),
        dropped,
    )
