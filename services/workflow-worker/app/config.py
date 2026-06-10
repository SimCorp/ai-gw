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
    relay_secret: str
    admin_internal_token: str
    # --- Azure Container Apps Jobs runtime (only required when
    # AGENT_CONTAINER_RUNTIME=aca_job; harmless empty defaults for docker/relay).
    # Env var names below are what bicep must wire to match. ---
    agent_runner_job_name: (
        str  # AGENT_RUNNER_JOB_NAME — pre-declared ACA job, e.g. job-agent-runner-<env>-sdc
    )
    azure_resource_group: str  # AZURE_RESOURCE_GROUP — RG holding the job + storage
    azure_subscription_id: str  # AZURE_SUBSCRIPTION_ID — subscription of the job
    runs_share_name: str  # AIGW_RUNS_SHARE — Azure Files share for per-run I/O exchange
    runs_storage_account: str  # AIGW_RUNS_STORAGE_ACCOUNT — storage account hosting the share
    aca_poll_interval_s: float  # AGENT_ACA_POLL_INTERVAL_S — execution status poll cadence

    @classmethod
    def from_env(cls) -> "Settings":
        return cls(
            # asyncpg URL (no driver suffix; asyncpg.connect accepts plain postgresql://)
            database_url=os.environ["DATABASE_URL"]
            .replace("postgresql+asyncpg://", "postgresql://")
            .replace("postgresql+psycopg2://", "postgresql://"),
            redis_url=os.environ["REDIS_URL"],
            worker_id=os.getenv("WORKER_ID", f"worker-{socket.gethostname()}"),
            concurrency=int(os.getenv("WORKER_CONCURRENCY", "5")),
            poll_interval_s=float(os.getenv("WORKER_POLL_INTERVAL_S", "1.0")),
            claim_ttl_s=int(os.getenv("WORKER_CLAIM_TTL_S", "120")),
            sweeper_interval_s=float(os.getenv("WORKER_SWEEPER_INTERVAL_S", "30")),
            # Host-side path where this worker writes per-run input/output files. The
            # same host path is bind-mounted into agent containers at /run.
            host_runs_path=os.getenv("HOST_RUNS_PATH", "/tmp/aigw-runs"),
            container_network=os.getenv("AGENT_CONTAINER_NETWORK", "aigateway"),
            relay_url=os.environ["AGENT_RELAY_URL"],
            admin_url=os.environ["ADMIN_URL"],
            agent_runtime=os.getenv("AGENT_CONTAINER_RUNTIME", "docker"),
            relay_secret=os.getenv("AGENT_RELAY_SECRET", ""),
            admin_internal_token=os.getenv("ADMIN_INTERNAL_TOKEN", ""),
            agent_runner_job_name=os.getenv("AGENT_RUNNER_JOB_NAME", ""),
            azure_resource_group=os.getenv("AZURE_RESOURCE_GROUP", ""),
            azure_subscription_id=os.getenv("AZURE_SUBSCRIPTION_ID", ""),
            runs_share_name=os.getenv("AIGW_RUNS_SHARE", ""),
            runs_storage_account=os.getenv("AIGW_RUNS_STORAGE_ACCOUNT", ""),
            aca_poll_interval_s=float(os.getenv("AGENT_ACA_POLL_INTERVAL_S", "2.0")),
        )
