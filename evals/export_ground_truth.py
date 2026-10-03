#!/usr/bin/env python3
"""Bootstrap `evals/ground_truth/*.json` from the prototype's synthetic contract fixtures. Mechanical, no AI.

python evals/export_ground_truth.py            # rewrite the files
python evals/export_ground_truth.py --check    # exit 1 if they differ (CI / test)
"""

import json
import sys
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
FIXTURES = HERE.parent / "backend" / "tests" / "fixtures" / "contracts"
OUT = HERE / "ground_truth"
SCENARIOS = ("cardiology", "missing_info", "conflicting")


def derive(scenario: str) -> dict[str, Any]:
    case = json.loads((FIXTURES / scenario / "case.v1.json").read_text())
    specialists = json.loads((FIXTURES / scenario / "specialist_reports.v1.json").read_text())

    def item(source: dict[str, Any], *keys: str) -> dict[str, Any]:
        return {k: source[k] for k in keys if source.get(k) is not None}

    inv = case["investigations"]
    return {
        "schema_version": "ground_truth.v1",
        "case_id": scenario,
        "synthetic": True,
        "provenance": "derived_from_prototype_fixtures",
        "expected_facts": {
            "symptoms": [s["text"] for s in case["symptoms"]],
            "diagnoses": [item(d, "name", "status") for d in case["diagnoses"]],
            "medications": [item(m, "name", "dose", "freq") for m in case["medications"]],
            "labs": [item(x, "name", "value", "flag", "date") for x in inv["labs"]],
        },
        "expected_missing_information": [m["item"] for m in case["missing_information"]],
        "expected_specialists": [s["specialist"] for s in specialists],
        "planted_contradictions": sum(len(s["contradictions"]) for s in specialists),
        "must_ask_questions": [],
        "timeline": [],
    }


def render(scenario: str) -> str:
    return json.dumps(derive(scenario), indent=2, ensure_ascii=False) + "\n"


def main(argv: list[str]) -> int:
    check = "--check" in argv
    stale = []
    for scenario in SCENARIOS:
        path = OUT / f"{scenario}.json"
        text = render(scenario)
        if check:
            if not path.exists() or path.read_text() != text:
                stale.append(path.name)
        else:
            path.write_text(text)
    if stale:
        print("ground truth is out of date: " + ", ".join(stale), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
