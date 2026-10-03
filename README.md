# AdvisorAI

**Before you take a second opinion, know exactly what to ask.**

AdvisorAI is a decision-support and second-opinion **preparation** platform. A person adds their
medical records; specialist AI perspectives read them, every important claim is checked against
evidence, and the person receives a calm plain-language report plus personalised, prioritised
questions to take to a qualified doctor.

AdvisorAI is **not** a doctor. It does not diagnose, prescribe, tell anyone to stop a medicine, say
a doctor is right or wrong, or decide whether a procedure should happen.

> **Status: Phase 1 prototype + the non-AI backend foundation (Phases 2A to 2F).** The clickable frontend
> runs on mocked, entirely fictional data by default and can be switched to the real backend. The backend is
> FastAPI on a Supabase Postgres foundation: RLS, private storage, audit log, JWT verification, the case and
> document lifecycle with secure upload and validation, and a job-queue/workflow engine with no AI nodes. Google
> sign-in is wired through Supabase Auth. There is **no AI, OCR, model call or provider key** yet.
> **Synthetic data only: never enter real medical information.**

## Repository layout

| Path | Purpose | Status |
| --- | --- | --- |
| [`frontend/`](frontend) | Next.js 15 app: the interactive prototype | **Implemented** |
| [`docs/`](docs) | Design direction, data contract, scope notes | Written |
| [`backend/`](backend) | FastAPI backend: foundation only (Phase 2A) | **Foundation** |
| [`supabase/`](supabase) | Migrations, RLS, storage policies, pgTAP tests, synthetic seed | **Foundation** |
| [`registry/`](registry) | Future agent and model configuration | Placeholder |
| [`workflows/`](workflows) | Future workflow (DAG) definitions | Placeholder |
| [`evidence/`](evidence) | Future curated evidence library | Placeholder |
| [`evals/`](evals) | Future benchmark cases and scoring | Placeholder |
| [`.github/`](.github) | CI: backend checks, fixture drift, Supabase stack + pgTAP + integration | **Backend + DB CI** |

## Run the prototype

```bash
cd frontend
npm install
npm run dev
```

Then open <http://localhost:3000>. Choose **Continue with Google** (simulated: it opens a fake
account chooser), confirm the consent step, and you are in.

Three fictional cases are included: a full cardiology case, a **missing-information** case and a
**conflicting-reports** case. See [`frontend/README.md`](frontend/README.md) for details.

## Run the backend

Requires Python 3.12 or newer.

```bash
cd backend
pip install uv                  # once; https://docs.astral.sh/uv/
uv sync --locked --extra dev    # installs exactly what backend/uv.lock pins
uv run --no-sync uvicorn app.main:app --reload
```

Then open <http://localhost:8000/api/v1/docs>. Tests: `uv run --no-sync pytest`. See
[`backend/README.md`](backend/README.md).

## Branching

`develop` is the default branch. Work happens on feature branches (for example
`feat/phase-1-ux-ui`) and is merged through review.
