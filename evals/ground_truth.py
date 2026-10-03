"""Ground-truth contract for benchmark cases (`ground_truth.v1`), blueprint p. 47-48.

A benchmark case is a SYNTHETIC patient record plus what a correct pipeline must find in it. This module
is the
single definition; `evals/schema/ground_truth.v1.schema.json` is generated from it and checked by a test.

Provenance matters: the files committed today are `derived_from_prototype_fixtures`, bootstrapped
mechanically from
the three fictional prototype scenarios. They are NOT clinician-reviewed. The blueprint's targets (extraction
accuracy, routing recall, contradiction detection, question coverage...) are only meaningful against
`expert_reviewed` truth, which a clinician advisor authors in the benchmark phase. `must_ask_questions`
and the
timeline are deliberately empty until then: they cannot be derived honestly from a mock.

Nothing here scores anything or calls a model; scoring belongs to the AI phase.
"""

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

NonEmpty = Annotated[str, StringConstraints(min_length=1)]


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class ExpectedMedication(_Strict):
    name: NonEmpty
    dose: str | None = None
    freq: str | None = None


class ExpectedLab(_Strict):
    name: NonEmpty
    value: str | None = None
    flag: str | None = None
    date: NonEmpty


class ExpectedDiagnosis(_Strict):
    name: NonEmpty
    status: Literal["documented", "suspected"]


class ExpectedFacts(_Strict):
    symptoms: list[NonEmpty]
    diagnoses: list[ExpectedDiagnosis]
    medications: list[ExpectedMedication]
    labs: list[ExpectedLab]


class GroundTruthV1(_Strict):
    schema_version: Literal["ground_truth.v1"]
    # The benchmark case id (also the folder under backend/tests/fixtures/contracts/ it was derived from).
    case_id: Annotated[str, StringConstraints(pattern=r"^[a-z][a-z0-9_]{2,40}$")]
    # Must stay true: real or de-identified patient data is never benchmark data (blueprint p. 48).
    synthetic: Literal[True]
    provenance: Literal["derived_from_prototype_fixtures", "expert_reviewed"]
    expected_facts: ExpectedFacts
    expected_missing_information: list[NonEmpty]
    # Specialist ids the router must select (recall must be 100% for the mandatory ones).
    expected_specialists: Annotated[list[NonEmpty], Field(min_length=1)]
    # Disagreements deliberately planted in the records; each must be shown, not smoothed over.
    planted_contradictions: Annotated[int, Field(ge=0)]
    # Authored by a clinician advisor; empty while provenance is derived_from_prototype_fixtures.
    must_ask_questions: list[NonEmpty]
    timeline: list[NonEmpty]
