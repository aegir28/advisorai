# ADR 0001: Wire casing is snake_case

- Status: accepted
- Date: 2026-10-02
- Scope: every versioned wire contract under `/api/v1`

## Context

After Phase 2 contract hardening the frontend domain model mixed two styles. The versioned envelope
fields used the blueprint's snake_case (`schema_version`, `run_id`, `case_id`, `missing_info`,
`evidence_refs`, `fact_ref`), while fields that existed in the Phase 1 UI kept camelCase
(`factRefs`, `routingReason`, `evidenceIds`, `caseId` on the report and run, ...). That was a
documented, deliberate inconsistency while no backend existed. It cannot be the wire format: a
backend, its OpenAPI document and any other client need one rule.

## Decision

1. **The wire format is snake_case, consistently.** Every key in every versioned contract
   (`case.v1`, `specialist_report.v1`, `report.v1`, `trace.v1`, `run.v1`) and in the error envelope
   is snake_case. The backend does **not** use a camelCase alias generator.
2. **Free-form content is exempt.** Keys inside `extensions` and `meta` are data, not contract, and
   are never renamed.
3. **Conversion happens once, explicitly, at the frontend API adapter boundary:**

   ```
   backend wire (snake_case) -> Pydantic validation -> frontend httpApi adapter
       -> frontend domain model -> UI
   ```

   The adapter is `frontend/src/lib/api/http/casing.ts`: an explicit key table, **not** a blanket
   camelCase/snake_case rule. A blanket rule would rename the domain's existing snake_case fields and
   break the UI. Because `case_id` / `run_id` are already snake_case in the domain for `case.v1` and
   `specialist_report.v1` but camelCase for `report.v1` and `run.v1`, decoding takes the contract name.
4. **The frontend domain model may stay camelCase where it already is.** No Phase 1 screen changes.
   New contracts should be snake_case in the domain too, so the adapter table does not grow.

## Optional means absent, never null

The Zod contracts use `.optional()`: a missing key is valid, `null` is not. The Pydantic models have
the same semantics: an explicit `null` for any declared field is rejected (`WireModel`), and the
generated JSON Schema / OpenAPI never advertises `null`. Free-form `extensions` / `meta` content is
data, not contract, and may contain nulls (`z.unknown()`). A field that is conditionally required
(`id` on a non-template report item) stays required where the rule says so.

## Enforcement

- Pydantic models use `extra="forbid"`: a camelCase key that leaks onto the wire is rejected, not
  ignored.
- The frontend exports the three synthetic scenarios as wire-form fixtures
  (`npm run export:fixtures` -> `backend/tests/fixtures/contracts/`). A frontend test fails if they
  drift; backend tests validate every fixture, round-trip it unchanged, and assert every key is
  snake_case.
- `npm run export:fixtures` also exports every contract's field paths and optional set, read from
  the Zod schemas (`contract-shapes.json`). A backend test compares them with the Pydantic models, and
  both sides have a test that an explicit `null` is rejected (and an absent key accepted) for every
  optional path.
- A frontend test round-trips every contract through `toWire` / `fromWire` and asserts the result
  equals the original domain object.

## Consequences

- One wire rule, visible in OpenAPI.
- The adapter table is the only place that knows both spellings. A missing entry fails a test.
- Adding a camelCase field to a domain contract requires a table entry (and a fixture refresh).

## Rejected alternatives

- **camelCase on the wire via a Pydantic alias generator.** Rejected: it makes the blueprint's own
  snake_case names the exception, and hides the mapping inside the serialiser.
- **Rename the domain to snake_case now.** Rejected for Phase 2A: it rewrites Phase 1 screens, which
  was explicitly out of scope. It remains a valid later clean-up.
