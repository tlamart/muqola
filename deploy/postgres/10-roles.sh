#!/bin/sh
# Only the initial, empty PostgreSQL volume runs this script. Existing volumes
# require the separately documented explicit role-setup command, never a reset.
set -eu
set +x
export MUQOLA_MIGRATE_PASSWORD=$(cat /run/secrets/db_migrate_password)
export MUQOLA_APP_PASSWORD=$(cat /run/secrets/db_app_password)
# psql variables are quoted as SQL literals/identifiers; no shell-built SQL.
psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" \
  -v db="$POSTGRES_DB" <<'SQL'
\getenv migrate_password MUQOLA_MIGRATE_PASSWORD
\getenv app_password MUQOLA_APP_PASSWORD
SET log_statement = 'none';
SET log_min_error_statement = 'panic';
BEGIN;
CREATE ROLE muqola_migrate LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION PASSWORD :'migrate_password';
CREATE ROLE muqola_app LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION PASSWORD :'app_password';
REVOKE ALL ON DATABASE :"db" FROM PUBLIC;
GRANT CONNECT, CREATE, TEMPORARY ON DATABASE :"db" TO muqola_migrate;
GRANT CONNECT ON DATABASE :"db" TO muqola_app;
REVOKE ALL ON SCHEMA public FROM PUBLIC;
ALTER SCHEMA public OWNER TO muqola_migrate;
GRANT USAGE ON SCHEMA public TO muqola_app;
ALTER DEFAULT PRIVILEGES FOR ROLE muqola_migrate IN SCHEMA public GRANT SELECT, INSERT, UPDATE ON TABLES TO muqola_app;
ALTER DEFAULT PRIVILEGES FOR ROLE muqola_migrate IN SCHEMA public GRANT USAGE, SELECT ON SEQUENCES TO muqola_app;
GRANT SELECT, INSERT, UPDATE ON ALL TABLES IN SCHEMA public TO muqola_app;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO muqola_app;
COMMIT;
SQL
