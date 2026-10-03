"""Personalised questions: validated model output plus a deterministic coverage floor.

A question is kept only if it is linked to ids that exist (a synthesis item, a gap, a claim) and passes the
output lint (a question may *ask* about a medicine; it may never instruct). After validation the floor adds a
fixed-text question for every disagreement, missing-information and medicine item that no model question
covers, so what matters most always reaches the visit even if the question model is unavailable.
"""

from collections.abc import Collection

from app.orchestration.contracts import ModelQuestion, QuestionsModelOutput
from app.safety.output_lint import lint_text
from app.schemas.common import Rank
from app.schemas.questions import Question
from app.schemas.synthesis import Synthesis, SynthesisItem

MAX_QUESTIONS = 20
_TRIGGER_TEXT = {
    "patient_question": "You asked about this",
    "missing_information": "Something is missing from your records",
    "uncertainty": "The analysis was unsure about this",
    "disagreement": "The records or perspectives differ here",
    "evidence_gap": "Evidence for this was thin",
    "medication": "This involves a medicine",
    "treatment": "This is about the proposed treatment",
    "unresolved": "This is still open",
}


def validate_questions(
    output: QuestionsModelOutput, known_ids: Collection[str]
) -> tuple[list[ModelQuestion], dict[str, int]]:
    kept: list[ModelQuestion] = []
    dropped: dict[str, int] = {}
    seen: set[str] = set()

    def drop(code: str) -> None:
        dropped[code] = dropped.get(code, 0) + 1

    for q in output.questions:
        text_key = " ".join(q.text.lower().split())
        if text_key in seen:
            drop("duplicate")
        elif not q.text.rstrip().endswith("?"):
            drop("not_a_question")
        elif any(link not in known_ids for link in q.linked_item_ids):
            drop("unknown_link")
        elif lint_text(q.text, "interpretation"):
            drop("unsafe_text")
        else:
            seen.add(text_key)
            kept.append(q)
    return kept[:MAX_QUESTIONS], dropped


def _floor_question(item: SynthesisItem) -> ModelQuestion | None:
    if item.group == "disagreement":
        text, trigger = (
            "Could you explain why these views differ, and what would help settle it?",
            "disagreement",
        )
    elif item.group == "missing":
        text, trigger = (
            "Would this missing information change anything, and should it be checked?",
            "missing_information",
        )
    elif item.group == "medication":
        text, trigger = (
            "Is there anything about my medicines that we should review together?",
            "medication",
        )
    else:
        return None
    return ModelQuestion(
        audience="current_doctor",
        priority=1,
        category=trigger.replace("_", " "),
        text=text,
        trigger_kind=trigger,  # type: ignore[arg-type]
        linked_item_ids=[item.id],
    )


def with_floor(questions: list[ModelQuestion], synthesis: Synthesis) -> list[ModelQuestion]:
    covered = {link for q in questions for link in q.linked_item_ids}
    out = list(questions)
    for item in synthesis.items:
        if item.id in covered:
            continue
        added = _floor_question(item)
        if added is not None:
            out.append(added)
    return out


def to_questions(items: list[ModelQuestion], run_id: str) -> list[Question]:
    ordered = sorted(enumerate(items), key=lambda p: (p[1].priority, p[0]))
    out: list[Question] = []
    for n, (_, q) in enumerate(ordered, start=1):
        rank: Rank = q.priority
        out.append(
            Question(
                id=f"q_{run_id[:8]}_{n}",
                audience=q.audience,
                priority=rank,
                category=q.category,
                text=q.text,
                trigger=_TRIGGER_TEXT[q.trigger_kind],
                linked_item_ids=q.linked_item_ids,
                status="not_asked",
            )
        )
    return out
