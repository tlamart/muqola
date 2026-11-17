#!/bin/sh
set -eu
set +x
export PGPASSWORD=$(cat /run/secrets/db_admin_password)
exec pg_dump --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" --format=custom --no-owner --no-acl
