"""Worker configuration. Reads from env vars set in docker-compose."""
from __future__ import annotations

import os
import socket
from dataclasses import dataclass


@dataclass
class Settings:
    database_url: str
    redis_url: str
    worker_id: str
    concurrency: int
    poll_interval_s: float
    claim_ttl_s: int
    sweeper_interval_s: float
    host_runs_path: str
    container_network: str
    relay_url: str
    admin_url: str
    agent_runtime: str

    @classmethod
    def from_env(cls) -> "Settings":
        return cls(
            # asyncpg URL (no driver suffix; asyncpg.connect accepts plain postgresql://)
            database_url=os.environ["DATABASE_URL"].replace("postgresql+asyncpg://", "postgresql://").replace("postgresql+psycopg2://", "postgresql://"),
            redis_url=os.getenv("REDIS_URL", "redis://redis:6379/0"),
            worker_id=os.getenv("WORKER_ID", f"worker-{socket.gethostname()}"),
            concurrency=int(os.getenv("WORKER_CONCURRENCY", "5")),
            poll_interval_s=float(os.getenv("WORKER_POLL_INTERVAL_S", "1.0")),
            claim_ttl_s=int(os.getenv("WORKER_CLAIM_TTL_S", "120")),
            sweeper_interval_s=float(os.getenv("WORKER_SWEEPER_INTERVAL_S", "30")),
            # Host-side path where this worker writes per-run input/output files. The
            # same host path is bind-mounted into agent containers at /run.
            host_runs_path=os.getenv("HOST_RUNS_PATH", "/tmp/aigw-runs"),
            container_network=os.getenv("AGENT_CONTAINER_NETWORK", "aigateway"),
            relay_url=os.getenv("AGENT_RELAY_URL", "http://agent-relay:8007"),
            admin_url=os.getenv("ADMIN_URL", "http://admin:8005"),
            agent_runtime=os.getenv("AGENT_CONTAINER_RUNTIME", "docker"),
        )
