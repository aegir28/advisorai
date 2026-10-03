"""Pydantic v2 wire contracts. One module per versioned contract."""

from .case import CASE_SCHEMA_VERSION, CaseV1
from .common import WireModel
from .comparison import Comparison, ComparisonRow, SecondOpinionState
from .cross_review import CrossReviewData
from .errors import ErrorBody, ErrorCode, ErrorEnvelope
from .evidence import Claim, EvidenceData
from .questions import Question
from .report import REPORT_SCHEMA_VERSION, PatientReport
from .routing import RoutingPlan
from .run import RUN_SCHEMA_VERSION, AnalysisRun
from .specialist_report import SPECIALIST_REPORT_SCHEMA_VERSION, SpecialistReport
from .synthesis import Synthesis
from .trace import TRACE_SCHEMA_VERSION, Trace

# The five versioned contracts, keyed by their `schema_version` value. Mirrors SCHEMA_VERSIONS in
# frontend/src/domain/schemas.ts; a contract test keeps the two in step.
CONTRACTS: dict[str, type[WireModel]] = {
    CASE_SCHEMA_VERSION: CaseV1,
    SPECIALIST_REPORT_SCHEMA_VERSION: SpecialistReport,
    REPORT_SCHEMA_VERSION: PatientReport,
    TRACE_SCHEMA_VERSION: Trace,
    RUN_SCHEMA_VERSION: AnalysisRun,
}

# Unversioned wire shapes the UI already consumes (mirrors of the Zod schemas without a `schema_version`).
# The AI steps that produce them return exactly these models.
WIRE_SHAPES: dict[str, type[WireModel]] = {
    "claim": Claim,
    "evidence": EvidenceData,
    "routing_plan": RoutingPlan,
    "cross_review": CrossReviewData,
    "synthesis": Synthesis,
    "question": Question,
    "comparison": Comparison,
}

__all__ = [
    "CONTRACTS",
    "WIRE_SHAPES",
    "AnalysisRun",
    "CaseV1",
    "Claim",
    "Comparison",
    "ComparisonRow",
    "CrossReviewData",
    "ErrorBody",
    "ErrorCode",
    "ErrorEnvelope",
    "EvidenceData",
    "PatientReport",
    "Question",
    "RoutingPlan",
    "SecondOpinionState",
    "SpecialistReport",
    "Synthesis",
    "Trace",
]
