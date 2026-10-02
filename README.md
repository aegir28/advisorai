# AdvisorAI

**Before you take a second opinion, know exactly what to ask.**

AdvisorAI is a decision-support and second-opinion **preparation** platform. A person adds their
medical records; specialist AI perspectives read them, every important claim is checked against
evidence, and the person receives a calm plain-language report plus personalised, prioritised
questions to take to a qualified doctor.

AdvisorAI is **not** a doctor. It does not diagnose, prescribe, tell anyone to stop a medicine, say
a doctor is right or wrong, or decide whether a procedure should happen.

> **Status: Phase 1, the UX/UI prototype.** A complete, clickable, frontend-only prototype running on
> mocked, entirely fictional data. There is no backend, no AI, no database and no real
> authentication yet. Never enter real medical information.

## Repository layout

| Path | Purpose | Phase 1 |
| --- | --- | --- |
| [`frontend/`](frontend) | Next.js 15 app: the interactive prototype | **Implemented** |
| [`docs/`](docs) | Design direction, data contract, scope notes | Written |
| [`backend/`](backend) | Future FastAPI backend | Placeholder |
| [`supabase/`](supabase) | Future SQL: tables, RLS, storage policies | Placeholder |
| [`registry/`](registry) | Future agent and model configuration | Placeholder |
| [`workflows/`](workflows) | Future workflow (DAG) definitions | Placeholder |
| [`evidence/`](evidence) | Future curated evidence library | Placeholder |
| [`evals/`](evals) | Future benchmark cases and scoring | Placeholder |
| [`.github/`](.github) | Future CI | Placeholder |

## Run the prototype

```bash
cd frontend
npm install
npm run dev
```

Then open <http://localhost:3000>. On the sign-up or sign-in screen choose
**"Skip ahead as a demo user"** (or use the demo code `123456`).

Three fictional cases are included: a full cardiology case, a **missing-information** case and a
**conflicting-reports** case. See [`frontend/README.md`](frontend/README.md) for details.

## Branching

`develop` is the default branch. Work happens on feature branches (for example
`feat/phase-1-ux-ui`) and is merged through review.
