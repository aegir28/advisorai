# .github

CI workflows (`workflows/`):

| Workflow | Runs |
| --- | --- |
| `backend.yml` | `uv lock --check`, `ruff`, `mypy`, `pytest` on Python 3.12 and 3.13 from the lockfile; the frontend fixture drift check. Integration tests skip here (no database). |
| `frontend.yml` | `npm ci`, typecheck, lint, tests (wire parity with the backend API-surface snapshot, safety-rule parity, secret-hygiene tests), production build. |
| `guards.yml` | `scripts/repo_guards.py`: the project name, no committed secrets, and the temporary no-AI-yet boundary. |
| `supabase.yml` | The real local Supabase stack: `supabase db reset` from a clean database, `db lint`, **pgTAP / RLS tests**, then the backend **integration tests** (two users, anon, the user-context mechanism, audit, signed URLs). |
