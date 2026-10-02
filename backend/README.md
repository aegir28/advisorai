# backend

FastAPI service for AdvisorAI. **Phase 2A foundation + Phase 2B Supabase foundation.** AdvisorAI is decision support and
second-opinion preparation, not medical advice.

## What exists

- FastAPI app factory (`app/main.py`), versioned under `/api/v1`
- `GET /api/v1/health` (liveness) and `GET /api/v1/health/ready` (database reachable; no connection details)
- `GET /api/v1/me`: the signed-in user's own profile (JWT -> `CurrentUser` -> user-scoped transaction -> RLS)
- OpenAPI at `/api/v1/docs`, `/api/v1/redoc`, `/api/v1/openapi.json` (includes the five contracts)
- Error contract: one envelope for every error ([ADR 0002](../docs/adr/0002-error-contract.md))
- Request ID / correlation ID on every request, response, error and log line
- CORS and typed configuration (`ADVISORAI_*` environment variables, see `.env.example`)
- Pydantic v2 models for the five versioned contracts (`app/schemas/`), snake_case on the wire
  ([ADR 0001](../docs/adr/0001-wire-casing.md))
- **Phase 2B**
  - `app/auth/`: Supabase JWT verification against the project's **JWKS** (asymmetric keys only; `alg: none`
    and HS* rejected), the `CurrentUser` dependency
  - `app/db/`: direct Postgres through the fail-closed `app_backend` role, with an explicit, request-scoped
    user context so RLS applies, and a **separate `app_system` login and pool** for system operations (the
    user path cannot switch to it) ([ADR 0005](../docs/adr/0005-database-user-context.md))
  - `app/audit/`: append-only audit writer (no content, IP only as an HMAC)
  - `app/storage/`: signed-URL gateway (5-minute downloads) and the ownership + audit service
    ([ADR 0006](../docs/adr/0006-privacy-controls-audit-and-storage.md))
  - log redaction for JWTs, bearer values, signed-URL tokens and connection-string passwords
  - the database itself lives in [`../supabase`](../supabase/README.md)

## What does not exist yet

Google OAuth and frontend authentication (Phase 2C), the document upload API, OCR, MIME sniffing, hashing,
document processing, workflow engine, AI gateway, agents, evidence retrieval, report/question persistence.
Data mode is `synthetic_only`: no real patient data.

## Python version

`requires-python = ">=3.12"`. A second search of the repository (config files, CI, docs, history)
and the architecture blueprint found **no earlier Python target**, so 3.12 is a decision made in
Phase 2A, recorded in [ADR 0003](../docs/adr/0003-python-target-and-lockfile.md). It is developed on
3.13 and CI runs 3.12 and 3.13. Do not change it without an ADR.

## Dependencies and the lockfile

`pyproject.toml` declares the dependencies (lower bounds). [`uv.lock`](uv.lock) pins the exact
resolved graph for every platform, with hashes, and is committed. Install from it:

```bash
pip install uv                       # or see https://docs.astral.sh/uv/
uv sync --locked --extra dev         # creates .venv from uv.lock; fails if the lock is stale
uv run --no-sync uvicorn app.main:app --reload
```

Plain `pip install -e ".[dev]"` still works, but it re-resolves and is not reproducible.

Changing a dependency: edit `pyproject.toml`, run `uv lock`, commit both files. To upgrade
everything: `uv lock --upgrade`, then run the checks below. CI runs `uv lock --check`, so a lock that
does not match `pyproject.toml` fails the build.

## Run

```bash
uv sync --locked --extra dev
cp .env.example .env          # optional: defaults work for local development
uv run --no-sync uvicorn app.main:app --reload
```

## Check

```bash
uv run --no-sync ruff check . && uv run --no-sync ruff format --check .
uv run --no-sync mypy
uv run --no-sync pytest
```

## Layout

```
app/
  main.py              app factory, middleware order, handlers
  openapi.py           OpenAPI description + the versioned contracts as schemas
  api/                 thin HTTP layer: router.py (/api/v1), health.py, me.py
  auth/                jwks.py, verifier.py, dependencies.py (CurrentUser)
  db/                  database.py (user_session / system_session), profiles.py
  audit/               writer.py
  storage/             gateway.py (signed URLs), service.py (ownership -> sign -> audit)
  core/                config.py, request_id.py, errors.py, logging.py (with redaction)
  schemas/             Pydantic wire contracts, one module per contract + errors
tests/
  unit/                health, request ID, errors, config, OpenAPI, JWT/JWKS, auth + /me, audit, storage,
                       log redaction, DB/contract parity, repo hygiene (no secrets, no identity)
  integration/         needs `supabase start` (skipped otherwise): user context, RLS with two users, anon,
                       audit, signed URLs, the API against a real database
  contract/            frontend fixtures vs Pydantic models, malformed-payload rejection,
                       Zod/Pydantic field-shape and optional/null parity
  fixtures/contracts/  GENERATED from the frontend scenarios: do not edit by hand
```

## Contract fixtures

`tests/fixtures/contracts/<scenario>/*.json` are generated by the frontend from its three synthetic
scenarios, in wire (snake_case) form:

```bash
cd ../frontend && npm run export:fixtures
```

Backend tests validate every fixture with the Pydantic models and require an exact round trip.
CI fails if the fixtures drift from the scenarios.

## Running against the local Supabase stack

See [`../supabase/README.md`](../supabase/README.md). Set `ADVISORAI_DATABASE_URL` (login `app_backend`), `ADVISORAI_SYSTEM_DATABASE_URL` (login `app_system`),
`ADVISORAI_SUPABASE_JWKS_URL`, `ADVISORAI_SUPABASE_JWT_ISSUER` (and the storage/audit variables) in `.env`;
anything not configured makes the routes that need it answer `503 SERVICE_UNAVAILABLE`, never open access.

## Adding an endpoint later

1. Add a router module in `app/api/` and include it in `app/api/router.py`.
2. Use the response model from `app/schemas/`; raise `AppError(ErrorCode.…)` for expected failures.
3. Read settings through `settings_from_request`, not the global. Protect the route with `CurrentUserDep`
   and open data access with `database.user_session(user)`; never accept a user or owner ID from the client.
   A response model with optional fields needs `response_model_exclude_none=True` (optional means absent).
4. Add the matching `httpApi` method and `decode*` call in `frontend/src/lib/api/http/`.
