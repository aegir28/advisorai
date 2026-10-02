"""Benchmark ground truth: the committed files validate, match their generator, and the guards bite."""

import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

EVALS = Path(__file__).resolve().parents[3] / "evals"


def run(script: str, *args: str, cwd: Path = EVALS) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(cwd / script), *args], capture_output=True, text=True, check=False
    )


def test_the_committed_ground_truth_validates_and_the_schema_is_current() -> None:
    result = run("validate.py")
    assert result.returncode == 0, result.stderr
    assert "3 ground-truth file(s) valid" in result.stdout


def test_the_derived_files_match_the_prototype_fixtures() -> None:
    result = run("export_ground_truth.py", "--check")
    assert result.returncode == 0, result.stderr


def test_every_case_is_synthetic_derived_and_carries_no_clinician_authored_content_yet() -> None:
    for path in sorted((EVALS / "ground_truth").glob("*.json")):
        truth = json.loads(path.read_text())
        assert truth["synthetic"] is True and truth["provenance"] == "derived_from_prototype_fixtures"
        assert truth["must_ask_questions"] == [] and truth["timeline"] == []
        assert truth["case_id"] == path.stem and truth["expected_specialists"]
    assert (
        json.loads((EVALS / "ground_truth" / "conflicting.json").read_text())["planted_contradictions"] >= 1
    )


@pytest.fixture
def sandbox(tmp_path: Path) -> Path:
    copy = tmp_path / "evals"
    shutil.copytree(EVALS, copy, ignore=shutil.ignore_patterns("__pycache__"))
    return copy


def test_validation_rejects_real_looking_or_malformed_ground_truth(sandbox: Path) -> None:
    target = sandbox / "ground_truth" / "cardiology.json"
    good = json.loads(target.read_text())

    def broken(**change: object) -> subprocess.CompletedProcess[str]:
        target.write_text(json.dumps({**good, **change}))
        return run("validate.py", cwd=sandbox)

    assert broken(synthetic=False).returncode == 1
    assert broken(provenance="clinician_said_so").returncode == 1
    assert broken(case_id="somebody_else").returncode == 1
    assert broken(surprise=1).returncode == 1
    assert broken(expected_specialists=[]).returncode == 1
    assert broken(timeline=["2026-01-01 an event"]).returncode == 1  # derived truth cannot carry a timeline
    leaky = broken(expected_facts={**good["expected_facts"], "email": "x@example.test"})
    assert leaky.returncode == 1
    target.write_text(json.dumps(good, indent=2) + "\n")
    assert run("validate.py", cwd=sandbox).returncode == 0
