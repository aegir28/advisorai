# evals

Benchmark infrastructure for the later AI phase (blueprint p. 47-48). **No scoring and no model calls yet.**

```
evals/
  ground_truth.py            the ground_truth.v1 contract (Pydantic); the single definition
  schema/                    ground_truth.v1.schema.json, generated from it (a test keeps them in step)
  ground_truth/              one JSON per benchmark case: what a correct pipeline must find
  export_ground_truth.py     bootstraps ground_truth/ from the prototype's synthetic fixtures (mechanical)
  validate.py                validates every file: contract, synthetic-only, no identity keys
  reports/                   score history (written by the AI phase; empty now)
```

```bash
cd backend
uv run --no-sync python ../evals/validate.py                  # contract + safety checks
uv run --no-sync python ../evals/export_ground_truth.py --check   # derived files match the fixtures
```

## What is, and is not, ground truth today

The three files are `provenance: derived_from_prototype_fixtures`: copied mechanically from the three **fictional**
prototype scenarios (cardiology, knee / missing information, conflicting reports). They give the AI phase
a schema, a loader and a regression baseline to start from. They are **not clinician-reviewed**, so the blueprint's
accuracy targets are not meaningful against them yet. `must_ask_questions` and `timeline` are empty on purpose: they
cannot honestly be derived from a mock, and `validate.py` refuses to let derived files carry them.

Blueprint target for v1 is 20 synthetic cases (ortho, cardiology, neurology, polypharmacy, ambiguous/missing-data,
conflicting-reports) with expert-reviewed truth. Growing to that set, adding the synthetic PDFs/images each case is
read from (`evals/cases/`), and writing the scorer are AI-phase work.

## Rules

- Synthetic only. `synthetic` is the literal `true`; real or de-identified patient data is never benchmark data.
  Using real cases, even de-identified, needs explicit separate consent, a documented purpose and legal sign-off.
- No identity keys anywhere in a ground-truth file.
- A change to a prompt, schema, model or agent must be scored on this set before it ships (blueprint p. 47).
