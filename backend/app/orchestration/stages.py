"""The 14 stages of one case analysis. `run.v1` shows exactly 14 steps, so a run is these stages.

Stage ids are the `workflow_steps.node` values and the names the n8n workflows use. The patient-facing
progress groups (frontend `analysis-groups.ts`) are: documents 1-4, history 5, perspectives 6-8,
evidence 9-10, summary 11-14.

Order note: personalised questions (13) come before the final report (14) because the report contains the
question sections; the report is assembled last from everything before it.
"""

from dataclasses import dataclass
from typing import Final


@dataclass(frozen=True, slots=True)
class Stage:
    n: int
    id: str
    # A failure of a critical stage fails the run; a non-critical one makes the run `partial`.
    critical: bool
    # Does the stage call a model (through the gateway)? Informational: used by cost reports and docs.
    uses_model: bool


STAGES: Final[tuple[Stage, ...]] = (
    Stage(1, "intake_safety", True, False),
    Stage(2, "document_text", True, False),
    Stage(3, "vision_ocr", False, False),
    Stage(4, "fact_extraction", True, True),
    Stage(5, "case_structuring", True, False),
    Stage(6, "routing", True, False),
    Stage(7, "specialist_fanout", True, True),
    Stage(8, "specialist_collect", True, False),
    Stage(9, "evidence_retrieval", False, False),
    Stage(10, "evidence_verification", True, True),
    Stage(11, "cross_review", False, False),
    Stage(12, "interim_review", False, True),
    Stage(13, "personalized_questions", False, True),
    Stage(14, "final_report", True, True),
)
STAGE_IDS: Final[tuple[str, ...]] = tuple(s.id for s in STAGES)
_BY_ID: Final[dict[str, Stage]] = {s.id: s for s in STAGES}
DEFINITION_ID: Final = "case_analysis"
DEFINITION_VERSION: Final = 1


def stage(stage_id: str) -> Stage:
    try:
        return _BY_ID[stage_id]
    except KeyError:
        raise KeyError("unknown_stage") from None
