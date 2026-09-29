#!/usr/bin/env bash
# Copy the whole production database from one Neon project to another (the
# us-east-1 → London move, 2026-09-29), then prove the copy matches row-for-row.
#
# Reads both connection strings from the environment so no password is ever typed
# on the command line, pasted into chat, or saved in shell history:
#
#   read -rs OLD_DATABASE_URL && export OLD_DATABASE_URL   # paste old URL, Enter
#   read -rs NEW_DATABASE_URL && export NEW_DATABASE_URL   # paste new URL, Enter
#   ./scripts/copy_database.sh
#
# Safe by design:
#   - read-only against OLD (pg_dump only); OLD is never modified
#   - refuses to run if NEW already has tables (won't clobber anything)
#   - uses Neon's DIRECT endpoint (drops "-pooler"): dump/restore through the
#     pgbouncer pooler can fail on session-level settings
#   - exits non-zero if any table's row count differs
set -euo pipefail

PG_BIN="${PG_BIN:-/opt/homebrew/opt/libpq/bin}"
export PATH="$PG_BIN:$PATH"

die() { echo "✖ $*" >&2; exit 1; }
say() { echo "▸ $*"; }

command -v pg_dump >/dev/null || die "pg_dump not found — run: brew install libpq"
[[ -n "${OLD_DATABASE_URL:-}" ]] || die "OLD_DATABASE_URL is not set"
[[ -n "${NEW_DATABASE_URL:-}" ]] || die "NEW_DATABASE_URL is not set"
[[ "$OLD_DATABASE_URL" != "$NEW_DATABASE_URL" ]] || die "OLD and NEW are the same database"

direct() { echo "${1/-pooler./.}"; }   # Neon pooler host → direct host
host_of() { sed -E 's#^[a-z]+://[^@]+@([^/:?]+).*#\1#' <<<"$1"; }
OLD="$(direct "$OLD_DATABASE_URL")"
NEW="$(direct "$NEW_DATABASE_URL")"

say "From: $(host_of "$OLD")"
say "To:   $(host_of "$NEW")"

old_ver=$(psql "$OLD" -Atc "show server_version_num")
new_ver=$(psql "$NEW" -Atc "show server_version_num")
say "Postgres versions — old ${old_ver:0:2}, new ${new_ver:0:2}"
(( new_ver / 10000 >= old_ver / 10000 )) || die "NEW runs an older Postgres major than OLD — create it on ${old_ver:0:2}+"

existing=$(psql "$NEW" -Atc "select count(*) from information_schema.tables where table_schema='public'")
[[ "$existing" == "0" ]] || die "NEW already has $existing tables in public — expected an empty database. Aborting."

dump="$(mktemp -t level-db).dump"
trap 'rm -f "$dump"' EXIT

say "Dumping old database…"
pg_dump "$OLD" --format=custom --no-owner --no-privileges --file="$dump"
say "Dump size: $(du -h "$dump" | cut -f1)"

say "Restoring into new database…"
pg_restore --dbname="$NEW" --no-owner --no-privileges --exit-on-error "$dump"

say "Verifying row counts table by table…"
tables=$(psql "$OLD" -Atc "select tablename from pg_tables where schemaname='public' order by 1")
mismatch=0
printf "  %-28s %10s %10s\n" TABLE OLD NEW
for t in $tables; do
  a=$(psql "$OLD" -Atc "select count(*) from public.\"$t\"")
  b=$(psql "$NEW" -Atc "select count(*) from public.\"$t\"")
  flag=""; [[ "$a" == "$b" ]] || { flag="  ✖ MISMATCH"; mismatch=1; }
  printf "  %-28s %10s %10s%s\n" "$t" "$a" "$b" "$flag"
done

old_rev=$(psql "$OLD" -Atc "select version_num from alembic_version")
new_rev=$(psql "$NEW" -Atc "select version_num from alembic_version")
say "Migration revision — old $old_rev, new $new_rev"
[[ "$old_rev" == "$new_rev" ]] || mismatch=1

# Id sequences: the next id must continue after the copied rows, or the first new
# player/match would collide with an existing id.
say "Checking id sequences continue past the copied rows…"
for t in $tables; do
  seq=$(psql "$NEW" -Atc "select pg_get_serial_sequence('public.\"$t\"', 'id')" 2>/dev/null || true)
  [[ -n "$seq" ]] || continue
  maxid=$(psql "$NEW" -Atc "select coalesce(max(id), 0) from public.\"$t\"")
  last=$(psql "$NEW" -Atc "select case when is_called then last_value else last_value - 1 end from $seq")
  if (( last < maxid )); then
    echo "  ✖ $t: next id would be $((last + 1)) but max id is $maxid"
    mismatch=1
  fi
done

if (( mismatch )); then
  die "Copy does NOT match — do not switch Railway over. The old database is untouched."
fi
echo
echo "✔ Copy verified: every table matches and ids continue correctly."
echo "  Next: set Railway's DATABASE_URL to the NEW connection string (pooler URL is fine for the app)."
