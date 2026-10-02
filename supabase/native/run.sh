#!/usr/bin/env bash
# Native PostgreSQL substitute harness (see stub_supabase.sql for what it is and is not).
#   supabase/native/run.sh up      create + start a throw-away cluster, apply stubs, migrations, seed
#   supabase/native/run.sh pgtap   run the pgTAP tests in supabase/tests/database
#   supabase/native/run.sh reset   drop and rebuild the database (clean migrations + seed)
#   supabase/native/run.sh down    stop and delete the cluster
# Prints the ADVISORAI_TEST_ADMIN_DATABASE_URL to use for the backend integration tests.
set -euo pipefail
here="$(cd "$(dirname "$0")" && pwd)"
root="$(cd "$here/../.." && pwd)"
VER="${PGVER:-16}"; CLUSTER="advisorai"; PORT="${PGPORT_NATIVE:-54322}"
psqlq() { su postgres -c "psql -v ON_ERROR_STOP=1 -q -p $PORT -d ${2:-postgres} $1"; }

build() {
  su postgres -c "psql -q -p $PORT -d postgres -c 'drop database if exists advisorai'" >/dev/null
  su postgres -c "psql -q -p $PORT -d postgres -c 'create database advisorai'" >/dev/null
  su postgres -c "psql -q -p $PORT -d postgres -c 'alter database advisorai set search_path = \"\$user\", public, extensions'" >/dev/null
  psqlq "-f $here/stub_supabase.sql" advisorai
  psqlq "-c 'create extension if not exists pgcrypto with schema extensions'" advisorai || true
  for f in "$root"/supabase/migrations/*.sql; do psqlq "-f $f" advisorai >/dev/null; done
  psqlq "-f $root/supabase/seed.sql" advisorai >/dev/null
}

case "${1:-}" in
  up)
    pg_lsclusters | grep -q "$CLUSTER" || pg_createcluster "$VER" "$CLUSTER" -p "$PORT" -- --auth-local=trust --auth-host=trust
    pg_ctlcluster "$VER" "$CLUSTER" start 2>/dev/null || true
    until su postgres -c "pg_isready -q -p $PORT"; do sleep 1; done
    build
    echo "ADVISORAI_TEST_ADMIN_DATABASE_URL=postgresql+asyncpg://postgres@127.0.0.1:$PORT/advisorai" ;;
  reset) build ;;
  pgtap)
    su postgres -c "pg_prove -p $PORT -d advisorai -v $root/supabase/tests/database/*.sql" ;;
  down)
    pg_ctlcluster "$VER" "$CLUSTER" stop 2>/dev/null || true
    pg_dropcluster "$VER" "$CLUSTER" 2>/dev/null || true ;;
  *) echo "usage: $0 up|reset|pgtap|down" >&2; exit 2 ;;
esac
