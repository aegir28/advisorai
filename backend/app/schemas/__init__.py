"""Pydantic v2 wire contracts. One module per versioned contract."""

from .case import CASE_SCHEMA_VERSION, CaseV1
from .common import WireModel
from .errors import ErrorBody, ErrorCode, ErrorEnvelope
from .report import REPORT_SCHEMA_VERSION, PatientReport
from .run import RUN_SCHEMA_VERSION, AnalysisRun
from .specialist_report import SPECIALIST_REPORT_SCHEMA_VERSION, SpecialistReport
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

__all__ = [
    "CONTRACTS",
    "AnalysisRun",
    "CaseV1",
    "ErrorBody",
    "ErrorCode",
    "ErrorEnvelope",
    "PatientReport",
    "SpecialistReport",
    "Trace",
]
