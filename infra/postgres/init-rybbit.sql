-- Create a dedicated database for Rybbit analytics.
-- Rybbit manages its own schema via Drizzle; keeping it in a separate
-- database avoids any collision with the Alembic-managed `aigateway` DB.
-- Runs only on first cluster initialisation (empty data dir).
CREATE DATABASE rybbit;
