# ADR 0009: Google sign-in (Supabase Auth) and the frontend HTTP integration (Phase 2E)

- Status: accepted
- Date: 2026-10-06
- Scope: `frontend/src/features/auth`, `frontend/src/lib/api/http`, `supabase/config.toml`,
  `backend/app/api/me.py`, `backend/app/core/security.py`

Authentication is kept completely separate from the AI layer: nothing here touches a provider, a model or a key.

## Sign-in

1. **Google only** for the product (ADR 0004, decision 1). The browser uses `@supabase/supabase-js` with the
   **public project URL and anon key only** and the PKCE flow. The frontend contains no secret: a service-role
   or `sb_secret_*` key makes `assertPublicKey` throw, and a test scans the source for secret-looking
   `NEXT_PUBLIC_*` names and pins the exact list of public variables the app reads.
2. **Two implementations behind one context**, selected by `NEXT_PUBLIC_AUTH_MODE`: `mock` (default, the Phase 1
   prototype, no configuration) and `supabase` (real). `NEXT_PUBLIC_API_MODE=http` and `AUTH_MODE=supabase` go
   together; the mock session carries no token, so the backend answers `401` to it.
3. **The backend decides who you are, from the token.** The browser sends `Authorization: Bearer <access token>`
   to FastAPI only; FastAPI verifies it against the project's JWKS (ADR 0005). The anon key is never sent to the
   backend, the access token is never logged, and the user's email stays in Supabase (`auth.users`): the frontend
   shows the email from the Supabase session and never sends it to AdvisorAI's own API.
4. **Consent is recorded on the profile.** `POST /api/v1/me/consent {version}` sets `profiles.consented_at` and
   `consent_version` for the caller (RLS plus the existing column grant). Consent ticked on the sign-up screen
   survives the Google redirect in `sessionStorage` (not `localStorage`) and is recorded once after sign-in.
5. **Provider configuration.** `supabase/config.toml` has an `[auth.external.google]` block with
   `client_id`/`secret` read from environment variables (`SUPABASE_AUTH_EXTERNAL_GOOGLE_CLIENT_ID`,
   `..._SECRET`). It is `enabled = false` in the repository because the Supabase CLI refuses to start an enabled
   provider without credentials, which would break `supabase start` in CI. Turn it on locally, or in the hosted
   project's settings, with your own Google OAuth client. **Those credentials belong to Supabase Auth only**:
   never to the frontend, the backend or the repository.

   **Not verified here:** a real Google round-trip needs a Google OAuth client and a running Supabase Auth, which
   this environment did not have. What is tested: the context logic, the token plumbing, key hygiene, the backend
   consent endpoint and JWT verification end to end with locally minted tokens.
6. **Production Supabase project:** disable email sign-ups and anonymous sign-ins (local `config.toml` keeps email
   enabled for development users, ADR 0004).

## Frontend HTTP API

`createHttpApi()` now implements the `AdvisorApi` methods the backend serves (cases, safety check, documents,
run status). Everything that needs the AI pipeline is **not faked**: result reads answer `null` ("no results
exist for this case"), `getSecondOpinion` answers `{status: "none"}`, and `startAnalysis`, `updateQuestion`,
`submitSecondOpinion` throw `ApiNotAvailableError` (the upload screen shows a plain-language message).

- Wire shapes are **strict** Zod schemas (an unexpected key fails), mapped explicitly to the camelCase domain
  model. Optional means absent, never null.
- **Upload:** signed URL → `PUT` straight to private storage → `complete`. Type and size are pre-checked in the
  browser for a fast message, but the backend re-checks the real file.
- The wire schemas are tested against a committed snapshot of the backend's API surface
  (`backend/tests/fixtures/api-surface.json`, itself checked against the live OpenAPI); the safety rules run
  against one shared fixture on both sides.
- `ownerLabel`, `specialtyLabel` and `DocumentItem.pages` became optional in the domain schema: the first two are
  prototype display strings the backend does not send (the UI never read them); `pages` is unknown for a file that
  failed validation.

**Not verified here:** the browser's multipart `PUT` to a real Supabase signed upload URL (it mirrors the request
`supabase-js` makes, but no Storage API was available). The signed-URL gateway has unit tests against a mock
transport; the two real-Storage integration tests still need `supabase start`.

## Hardening added alongside

Every API response carries `Cache-Control: no-store`, `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`,
`Referrer-Policy: no-referrer` and (outside the docs pages) a deny-all CSP; HSTS in production. Request bodies are
capped at 1 MiB (`413 PAYLOAD_TOO_LARGE`): files never pass through the API on the way in. Per-user rate limiting
is not implemented (see ADR 0007); add it before any public exposure.
