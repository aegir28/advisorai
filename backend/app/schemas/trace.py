"""trace.v1: the evidence chain from any patient-facing statement down to a source."""

from typing import Literal

from .common import ContentKind, ExternalSource, Flag, Id, SourceRef, VerificationStatus, WireModel

TRACE_SCHEMA_VERSION = "trace.v1"

TraceLevel = Literal[
    "report",
    "synthesis",
    "specialist",
    "verification",
    "evidence_source",
    "fact",
    "timeline",
    "matrix",
    "question",
    "comparison",
]


class TraceNode(WireModel):
    id: Id
    level: TraceLevel
    text: str
    kind: ContentKind | None = None
    flag: Flag | None = None
    status: VerificationStatus | None = None
    # Free-form label, e.g. "Cardiology perspective".
    label: str | None = None
    source: SourceRef | None = None
    external_source: ExternalSource | None = None
    children: list["TraceNode"]


class Trace(WireModel):
    schema_version: Literal["trace.v1"]
    item_id: Id
    root: TraceNode
