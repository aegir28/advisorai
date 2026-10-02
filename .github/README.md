# .github

CI workflows (`workflows/`):

| Workflow | Runs |
| --- | --- |
| `backend.yml` | `uv lock --check`, `ruff`, `mypy`, `pytest` on Python 3.12 and 3.13 from the lockfile; the frontend fixture drift check. Integration tests skip here (no database). |
| `supabase.yml` | The real local Supabase stack: `supabase db reset` from a clean database, `db lint`, **pgTAP / RLS tests**, then the backend **integration tests** (two users, anon, the user-context mechanism, audit, signed URLs). |
