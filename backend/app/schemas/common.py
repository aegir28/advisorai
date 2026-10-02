"""Shared building blocks for the versioned wire contracts.

Wire rule (ADR 0001): every key on the wire is snake_case. The Zod schemas in
`frontend/src/domain/schemas.ts` are the shape reference; the frontend's explicit adapter
(`frontend/src/lib/api/http/casing.ts`) maps between this wire form and its camelCase domain model.
"""

from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, GetJsonSchemaHandler, StringConstraints, model_validator
from pydantic.json_schema import JsonSchemaValue
from pydantic_core import CoreSchema

# Non-empty identifier.
Id = Annotated[str, StringConstraints(min_length=1)]
NonEmpty = Annotated[str, StringConstraints(min_length=1)]
# The Zod contract only requires an ISO-looking date prefix, so the string is kept verbatim
# (no datetime parsing) and round-trips byte for byte.
IsoDate = Annotated[str, StringConstraints(pattern=r"^\d{4}-\d{2}-\d{2}")]
PageNumber = Annotated[int, Field(ge=1)]

FactKind = Literal["patient_fact", "interpretation", "external_evidence"]
ContentKind = Literal["patient_fact", "interpretation", "external_evidence", "template"]
Flag = Literal["uncertain", "missing", "disagreement"]
Confidence = Literal["high", "moderate", "low"]
Importance = Literal["high", "medium", "low"]
Sex = Literal["F", "M", "X"]
Rank = Literal[1, 2, 3]
VerificationStatus = Literal[
    "supported", "partially_supported", "unclear", "contradicted", "insufficient_evidence"
]

SpecialistId = Literal[
    "general_medicine",
    "cardiology",
    "interventional_cardiology",
    "medication_safety",
    "orthopedics",
    "neurology",
]


class WireModel(BaseModel):
    """Base for every wire contract.

    * `extra="forbid"`: an unknown key (for example a camelCase leak) is rejected, not ignored.
    * `strict=True`: no silent coercion ("52" is not an age).
    * Optional means ABSENT, never null. The Zod contracts use `.optional()`, which accepts a
      missing key and rejects `null`; this base class has the same semantics: an explicit `null`
      for any declared field is rejected, and the generated JSON Schema does not advertise null.
      (Free-form `extensions` / `meta` content is not a declared field and may hold nulls.)
    * Absent optional fields are omitted on output.
    """

    model_config = ConfigDict(extra="forbid", strict=True)

    @model_validator(mode="before")
    @classmethod
    def _reject_explicit_null(cls, data: Any) -> Any:
        if isinstance(data, dict):
            nulls = sorted(str(k) for k, v in data.items() if v is None and k in cls.model_fields)
            if nulls:
                raise ValueError(
                    f"null is not allowed for {', '.join(nulls)}; omit an optional field instead"
                )
        return data

    @classmethod
    def __get_pydantic_json_schema__(
        cls, core_schema: CoreSchema, handler: GetJsonSchemaHandler
    ) -> JsonSchemaValue:
        schema = handler(core_schema)
        for prop in handler.resolve_ref_schema(schema).get("properties", {}).values():
            # `X | None = None` is an implementation detail: on the wire the field is just optional.
            any_of = prop.get("anyOf")
            if any_of:
                kept = [option for option in any_of if option.get("type") != "null"]
                if len(kept) == 1:
                    prop.pop("anyOf")
                    prop.update(kept[0])
                elif kept:
                    prop["anyOf"] = kept
            if "default" in prop and prop["default"] is None:
                del prop["default"]
        return schema

    def model_dump(self, **kwargs: Any) -> dict[str, Any]:
        kwargs.setdefault("exclude_none", True)
        return super().model_dump(**kwargs)

    def model_dump_json(self, **kwargs: Any) -> str:
        kwargs.setdefault("exclude_none", True)
        return super().model_dump_json(**kwargs)


class SourceRef(WireModel):
    """A pointer into an uploaded document."""

    doc_id: Id
    page: PageNumber
    section: str | None = None
    snippet: NonEmpty


class ExternalSource(WireModel):
    """A curated reference source (never a patient document)."""

    id: Id
    title: str
    publisher: str
    year: int
    licence: str
    section: str
    snippet: str
