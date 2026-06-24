#!/bin/bash
# Creates the rybbit database and a least-privilege owner on first cluster init.
# Runs only when the data dir is empty (postgres entrypoint convention).
# RYBBIT_POSTGRES_PASSWORD must be set on the postgres service.
set -e
psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" \
  -c "CREATE DATABASE rybbit;" \
  -c "CREATE USER rybbit WITH PASSWORD '$RYBBIT_POSTGRES_PASSWORD';" \
  -c "GRANT ALL PRIVILEGES ON DATABASE rybbit TO rybbit;" \
  -c "ALTER DATABASE rybbit OWNER TO rybbit;"
