# ADR 0006: Privacy controls: identity separation, audit and signed URLs

- Status: accepted
- Date: 2026-10-03
- Scope: `supabase/migrations`, `backend/app/{audit,storage,core/logging}`

## Identity separation

| Where | What lives there |
| --- | --- |
| `auth.users` | email (managed by Supabase Auth) |
| `public.profiles` | `display_name`, `locale`, consent. **The only place a name exists.** |
| everything else | pseudonymous: `patients` (age, sex), `cases` (code), clinical rows |

Enforced, not just intended: a pgTAP test fails if any column outside `profiles.display_name` is named
like a name, email, phone or address; `medical_records` refuses snapshots with identity keys (a `CHECK`);
`case.v1` has no identity fields; audit metadata refuses `name`, `email`, `phone` and friends (a `CHECK`).

Free text typed by a person (`concern`, `proposed_treatment`, document `title`) can still contain
identifying details. It is treated as sensitive and must be de-identified before any AI step.

## Audit

- `audit_logs` is append-only for **every** role, including the database owner (no grants, plus a trigger
  that refuses UPDATE, DELETE and TRUNCATE). Tested.
- No foreign keys and no owner column, so rows survive deletion of the user, case or document.
- No content: allow-listed metadata keys in the writer, and a `CHECK` that refuses content keys even if the
  writer were bypassed. The client IP is stored only as `HMAC-SHA256(secret, canonical IP)`; the secret lives
  in the backend environment, never in the database. A raw IP cannot be inserted (the column only accepts 64
  hex characters).
- Written on the system path in its own transaction, so a rolled-back business transaction does not lose
  the audit row. Tested.

## Signed URLs and storage

- Private `case-documents` bucket; **no** client policy and a RESTRICTIVE policy against future ones.
- The backend alone signs URLs, with the service-role key (backend environment only).
- Order: ownership under RLS → sign → audit (the URL is never audited) → return. Another user's document and
  an incomplete upload both look like "not found".
- Download URLs live at most 300 seconds: capped in settings (validation rejects more) and in the gateway.
- `SignedUrl` redacts itself in `repr`, `str`, f-strings and logs; the log formatter additionally redacts JWTs,
  `Bearer` values, `token=` / `apikey=` pairs and connection-string passwords; `httpx` request logging is
  silenced. Tests assert none of these ever appear in log output or audit rows.
- Not in this phase: upload endpoints, MIME sniffing, hashing, extraction. The gateway can already sign
  upload URLs and delete objects, so the next phase can build on it.

## Synthetic data only

`ADVISORAI_DATA_MODE` accepts only `synthetic_only`, and the database refuses non-synthetic rows
(`CHECK (is_synthetic)`). Unlocking real data requires a migration and an ADR. No real patient data is to be
entered into any environment until that happens, and a production-region and agreement review is done.
