# Deployment foundations (free-tier first)

Blueprint, Part 8 (testing & deployment): Netlify (frontend) · Render free web service (backend) · Supabase free
(database, auth, storage) · GitHub Actions (CI). **Synthetic data only**: real patient data needs paid plans with
backups, agreements and a security review, and a migration + ADR that lifts the synthetic-only constraint.

> **Not verified in the build environment:** the Docker image could not be built there (the registry rate-limited
> the base image pull), and nothing was deployed. The start command was run natively (`uvicorn app.main:app` with
> the locked dependencies, `GET /api/v1/health`), and the Dockerfile is a straightforward `uv sync --locked`.
> Build it once before relying on it.

## Pieces

| Piece | File | Notes |
| --- | --- | --- |
| Backend image | `backend/Dockerfile` | Context = repository root (it carries `workflows/`). Non-root, locked deps, liveness `HEALTHCHECK`, `--proxy-headers`. |
| Render service | `render.yaml` | Free web service, health check `/api/v1/health`, every secret `sync: false`. |
| Netlify site | `frontend/netlify.toml` | Public `NEXT_PUBLIC_*` variables only. |
| Database | `supabase/migrations/` | Apply with `supabase link` + `supabase db push` (forward-only; no Alembic). |
| CI | `.github/workflows/` | `backend`, `frontend`, `supabase`, `guards`. |

## Order of operations (first deployment)

1. **Supabase project** (free). Region of your choice for the synthetic demo. In *Authentication → Providers*: enable
   Google with your own OAuth client; disable email sign-ups and anonymous sign-ins. Add the Netlify URL to the
   redirect allow-list.
2. **Migrations:** `supabase link --project-ref <ref>` then `supabase db push`. The last migration of each phase
   *fails the push* if RLS, grants or roles are not as designed.
3. **Database logins.** The migrations create `app_backend` and `app_system` **without passwords**. Set two
   different strong passwords in the SQL editor:

   ```sql
   alter role app_backend with password '<strong, unique>';
   alter role app_system  with password '<a different strong, unique one>';
   ```

   Use the **pooler** (transaction mode, port 6543) host in both URLs; the backend disables prepared statements for it.
4. **Render:** create the service from `render.yaml`; fill every `sync: false` value (see `backend/.env.example`).
   `ADVISORAI_ENVIRONMENT=production` makes the app refuse to start unless every security setting is present and the
   Supabase URLs are `https`. Docs are off in production.
5. **Netlify:** connect the repository, base directory `frontend`, set the five public variables, deploy.
6. **Smoke test:** `GET <backend>/api/v1/health`, then `/health/ready` (database reachable), then sign in with Google
   and create a case with a fictional document.

## Secrets: where each one lives

| Secret | Lives in | Never in |
| --- | --- | --- |
| `app_backend` / `app_system` passwords | Render env (inside the two DB URLs) | repository, frontend |
| Supabase service-role key | Render env | frontend, `NEXT_PUBLIC_*`, logs |
| `ADVISORAI_AUDIT_IP_HMAC_SECRET` | Render env | the database (only the HMAC is stored) |
| Google OAuth client secret | Supabase Auth settings | backend, frontend, repository |
| Supabase anon key, project URL | Netlify env (public by design) | n/a: it grants nothing alone |

`scripts/repo_guards.py` (CI) fails the build if a private key, a service-role/secret key, a provider key or a
committed `.env` appears in the repository.

## Free-tier limits that matter (verify on the vendors' pages before relying on them)

Render free sleeps when idle (slow first request); Supabase free pauses a project after a week idle and has small
database/storage/egress limits; Netlify free has build-minute and bandwidth caps. None of this is suitable for real
users, which is why the data is synthetic.

## Not done here

No production deployment, custom domain, backups, error tracker or uptime monitor. The blueprint's error tracker
("free-tier tool configured to scrub request bodies") is deferred: when added it must scrub request bodies, because
request bodies here can hold personal health information typed by a person.
