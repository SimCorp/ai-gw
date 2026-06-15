-- Creates the litellm database on first init.
-- This runs as part of docker-entrypoint-initdb.d before postgres is healthy,
-- so LiteLLM's Prisma schema has its own namespace and doesn't collide with
-- the Alembic-managed aigateway DB.
CREATE DATABASE litellm;
