#!/usr/bin/env python3
"""Validate every benchmark ground-truth file. Needs pydantic (run it with the backend environment):

    cd backend && uv run --no-sync python ../evals/validate.py

Checks: the `ground_truth.v1` contract, synthetic-only, no identity keys anywhere, one file per case id,
and the
committed JSON Schema being the one the model generates.
"""

import json
import sys
from pathlib import Path

from pydantic import ValidationError

sys.path.insert(0, str(Path(__file__).resolve().parent))
from ground_truth import GroundTruthV1

HERE = Path(__file__).resolve().parent
SCHEMA = HERE / "schema" / "ground_truth.v1.schema.json"
IDENTITY_KEYS = {
    "name_of_patient",
    "patient_name",
    "full_name",
    "display_name",
    "email",
    "phone",
    "mobile",
    "address",
    "dob",
}


def schema_text() -> str:
    return json.dumps(GroundTruthV1.model_json_schema(), indent=2, sort_keys=True) + "\n"


def walk_keys(value: object) -> set[str]:
    if isinstance(value, dict):
        return set(value) | {k for v in value.values() for k in walk_keys(v)}
    if isinstance(value, list):
        return {k for v in value for k in walk_keys(v)}
    return set()


def problems() -> list[str]:
    found: list[str] = []
    if not SCHEMA.exists() or SCHEMA.read_text() != schema_text():
        found.append(
            "schema/ground_truth.v1.schema.json is out of date (run: python evals/validate.py --write-schema)"
        )
    seen: set[str] = set()
    files = sorted((HERE / "ground_truth").glob("*.json"))
    if not files:
        found.append("no ground-truth files")
    for path in files:
        try:
            raw = json.loads(path.read_text())
            truth = GroundTruthV1.model_validate(raw)
        except (ValueError, ValidationError) as exc:
            found.append(f"{path.name}: {str(exc).splitlines()[0]}")
            continue
        if truth.case_id != path.stem:
            found.append(f"{path.name}: case_id {truth.case_id!r} must equal the file name")
        if truth.case_id in seen:
            found.append(f"{path.name}: duplicate case id")
        seen.add(truth.case_id)
        leaked = walk_keys(raw) & IDENTITY_KEYS
        if leaked:
            found.append(f"{path.name}: identity keys {sorted(leaked)}")
        if truth.provenance == "derived_from_prototype_fixtures" and (
            truth.must_ask_questions or truth.timeline
        ):
            found.append(
                f"{path.name}: derived truth must not carry clinician-authored questions or a timeline"
            )
    return found


def main(argv: list[str]) -> int:
    if "--write-schema" in argv:
        SCHEMA.parent.mkdir(exist_ok=True)
        SCHEMA.write_text(schema_text())
    issues = problems()
    for issue in issues:
        print(issue, file=sys.stderr)
    if not issues:
        print(f"evals: {len(list((HERE / 'ground_truth').glob('*.json')))} ground-truth file(s) valid")
    return 1 if issues else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
