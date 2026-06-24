-- Create Rybbit database and a least-privilege owner for it.
-- Rybbit manages its own schema via Drizzle; keeping it in a separate
-- database avoids any collision with the Alembic-managed `aigateway` DB.
-- Runs only on first cluster initialisation (empty data dir).
--
-- NOTE: PASSWORD 'changeme' is a placeholder for fresh-cluster init.
-- On an existing cluster (data dir already present) this script does NOT run;
-- an operator must manually create the role with the correct password:
--   CREATE USER rybbit WITH PASSWORD '<value of RYBBIT_POSTGRES_PASSWORD>';
--   GRANT ALL PRIVILEGES ON DATABASE rybbit TO rybbit;
--   ALTER DATABASE rybbit OWNER TO rybbit;
-- For fresh clusters, align the password by setting RYBBIT_POSTGRES_PASSWORD=changeme
-- in infra/.env temporarily, then rotate it after first boot.
CREATE DATABASE rybbit;
CREATE USER rybbit WITH PASSWORD 'changeme';
GRANT ALL PRIVILEGES ON DATABASE rybbit TO rybbit;
ALTER DATABASE rybbit OWNER TO rybbit;
