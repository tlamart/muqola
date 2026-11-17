#!/bin/sh
set -eu
set +x
case "$RESTORE_DATABASE" in muqola_restore_*) ;; *) exit 2 ;; esac
case "$RESTORE_DATABASE" in *[!a-zA-Z0-9_]*) exit 2 ;; esac
[ "$RESTORE_DATABASE" != "$POSTGRES_DB" ] || exit 2
export PGPASSWORD=$(cat /run/secrets/db_admin_password)
# Refuse any existing application tables; do not drop, clean, truncate or reset.
count=$(psql -XAt --username "$POSTGRES_USER" --dbname "$RESTORE_DATABASE" -v ON_ERROR_STOP=1 \
  -c "SELECT count(*) FROM pg_tables WHERE schemaname NOT IN ('pg_catalog','information_schema')")
[ "$count" = 0 ] || exit 3
pg_restore --username "$POSTGRES_USER" --dbname "$RESTORE_DATABASE" \
  --role=muqola_migrate --exit-on-error --single-transaction --no-owner --no-acl

exec psql -X --username "$POSTGRES_USER" --dbname "$RESTORE_DATABASE" -v ON_ERROR_STOP=1 -f /opt/muqola/runtime-grants.sql
