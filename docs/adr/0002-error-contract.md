# ADR 0002: Error contract and request IDs

- Status: accepted
- Date: 2026-10-02
- Scope: every error response under `/api/v1`

## Decision

Every error response has this envelope, and nothing else:

```json
{
  "error": {
    "code": "CASE_NOT_FOUND",
    "message": "Case could not be found.",
    "request_id": "req_123",
    "details": {}
  }
}
```

| Field | Meaning |
| --- | --- |
| `code` | Stable, machine-readable, `SCREAMING_SNAKE_CASE`. Clients branch on this, never on `message`. |
| `message` | Plain language, safe to show a person. Never clinical content, never user input, never internals. |
| `request_id` | The ID of the failed request; also in the `X-Request-ID` response header. |
| `details` | Machine-readable context; `{}` when there is none. |

**Versioning.** The envelope is part of API v1 (`ErrorEnvelope` in `backend/app/schemas/errors.py`).
Adding an error `code` is backward compatible; the frontend treats `code` as an open string. Changing
the envelope shape needs `/api/v2` and a new ADR. (The envelope itself carries no `schema_version`
field, by design: the API path is the version.)

**Codes (v1).** HTTP-level: `BAD_REQUEST`, `VALIDATION_ERROR` (422), `UNAUTHENTICATED`, `FORBIDDEN`,
`NOT_FOUND`, `METHOD_NOT_ALLOWED`, `CONFLICT`, `HTTP_ERROR`, `INTERNAL_ERROR` (500). Domain, raised by
routes as they are added: `CASE_NOT_FOUND`, `RUN_NOT_FOUND`, `TRACE_ITEM_NOT_FOUND`.

## Rules

1. **All paths use the envelope**: deliberate `AppError`s, framework errors (404, 405, 422) and
   unhandled exceptions (500).
2. **Validation errors never echo input.** `details.errors` has `loc`, `message`, `type` only.
   Pydantic's `input` field is dropped: it can contain personal health information.
3. **500s hide internals.** The exception and traceback are logged server-side with the request ID;
   the client gets `INTERNAL_ERROR` and a fixed message.
4. **A 500 is still readable by the browser.** The error boundary sits inside CORS, so the envelope
   carries CORS headers.
5. **Framework `detail` text is not forwarded**; messages are fixed per status.

## Request / correlation ID

- Every request has one. A caller may send `X-Request-ID` (`[A-Za-z0-9_.-]{1,128}`); anything else is
  replaced by `req_<uuid4 hex>`.
- It is echoed in `X-Request-ID` on **every** response (including CORS preflights), stored in a
  context variable, attached to every log line, and placed in every error envelope.
- Access logs record method, path, status and duration. **Query strings are never logged.**
- The frontend client sends its own ID, prefers the server's, and exposes it on `ApiError.requestId`
  so a person can quote it to support.

## Rejected alternative

RFC 9457 Problem Details (`application/problem+json`). It is a fine standard, but the product needs
a person-safe `message`, a stable `code` and a `request_id` on every error; the custom envelope maps
directly onto the frontend's existing error states.
