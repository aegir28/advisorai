"""The database CHECK constraints must match the frontend contract enums (schemas.ts).

Read from the migration SQL text, so it runs everywhere (no database needed). The only allowed
differences are the two deliberate INTERNAL states (ADR 0004): `pending_upload` for documents and
`queued` for workflow runs, which no API exposes yet.
"""

import re
from pathlib import Path

ROOT = Path(__file__).parents[3]
SCHEMAS_TS = (ROOT / "frontend" / "src" / "domain" / "schemas.ts").read_text(encoding="utf-8")
MIGRATIONS = "\n".join(
    p.read_text(encoding="utf-8") for p in sorted((ROOT / "supabase" / "migrations").glob("*.sql"))
)


def db_values(table: str, column: str) -> set[str]:
    """The literals of `check (<column> in ('a', 'b', ...))` inside `create table public.<table>`."""
    start = MIGRATIONS.index(f"create table public.{table} (")
    end = MIGRATIONS.index(");\n", start)
    body = MIGRATIONS[start:end]
    match = re.search(rf"check \({column} in \(([^)]*)\)\)", body)
    assert match, f"no `{column} in (...)` check on {table}"
    return set(re.findall(r"'([^']+)'", match.group(1)))


def zod_enum(name: str) -> set[str]:
    """`export const <name> = z.enum([...])`"""
    match = re.search(rf"export const {name} = z\.enum\(\[(.*?)\]\)", SCHEMAS_TS, re.S)
    assert match, f"{name} not found in schemas.ts"
    return set(re.findall(r'"([^"]+)"', match.group(1)))


def zod_inline_enum(schema: str, field: str) -> set[str]:
    """`<field>: z.enum([...])` inside `export const <schema> = z.object({ ... })`"""
    block = SCHEMAS_TS[SCHEMAS_TS.index(f"export const {schema} = ") :]
    match = re.search(rf"\b{field}: z\.enum\(\[(.*?)\]\)", block, re.S)
    assert match, f"{schema}.{field} not found in schemas.ts"
    return set(re.findall(r'"([^"]+)"', match.group(1)))


def test_case_status_matches_the_contract() -> None:
    assert db_values("cases", "status") == zod_enum("CaseStatusSchema")


def test_sex_matches_the_contract() -> None:
    assert db_values("patients", "sex") == zod_enum("SexSchema")


def test_document_type_matches_the_contract() -> None:
    assert db_values("documents", "type") == zod_enum("DocumentTypeSchema")


def test_document_status_is_the_contract_plus_the_internal_pending_upload_state() -> None:
    assert db_values("documents", "status") == zod_enum("DocumentStatusSchema") | {"pending_upload"}


def test_workflow_run_status_is_the_contract_plus_the_internal_queued_state() -> None:
    assert db_values("workflow_runs", "status") == zod_enum("RunStatusSchema") | {"queued"}


def test_internal_states_are_not_part_of_the_api_contracts() -> None:
    assert "queued" not in zod_enum("RunStatusSchema")
    assert "pending_upload" not in zod_enum("DocumentStatusSchema")


def test_workflow_step_status_matches_the_contract() -> None:
    assert db_values("workflow_steps", "status") == zod_enum("StepStatusSchema")


def test_fact_type_flag_and_timeline_precision_match_the_contract() -> None:
    assert db_values("facts", "type") == zod_inline_enum("FactSchema", "type")
    assert db_values("timeline_events", "precision") == zod_inline_enum("TimelineEventSchema", "precision")
    assert db_values("facts", "flag") == zod_inline_enum("FactSchema", "flag")
    assert db_values("lab_results", "flag") == zod_inline_enum("FactSchema", "flag")


def test_diagnosis_status_matches_case_v1() -> None:
    assert db_values("diagnoses", "status") == {"documented", "suspected"}
    assert '"documented", "suspected"' in SCHEMAS_TS


def test_workflow_steps_and_run_step_count_match_run_v1() -> None:
    # Widened by 20261008000001 (steps come from the workflow definition); the registry loader's maximum matches.
    assert "workflow_steps_n_range check (n between 1 and 64)" in MIGRATIONS
    assert "z.number().int().min(1).max(64)" in SCHEMAS_TS  # RunStepSchema.n


def test_the_document_mime_allow_list_matches_the_storage_bucket() -> None:
    documents = db_values("documents", "mime_type")
    bucket = set(
        re.findall(
            r"'([a-z]+/[a-z]+)'", MIGRATIONS[MIGRATIONS.index("insert into storage.buckets") :].split(";")[0]
        )
    )
    assert documents == bucket == {"application/pdf", "image/jpeg", "image/png"}


def test_the_storage_size_limit_is_20_mb_in_the_table_and_the_bucket() -> None:
    assert "size_bytes between 1 and 20971520" in MIGRATIONS
    assert "false, 20971520" in MIGRATIONS
