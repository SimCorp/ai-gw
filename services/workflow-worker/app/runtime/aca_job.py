"""ACAJobRuntime — spawns an agent as an Azure Container Apps Jobs execution.

Replaces the Docker-socket spawn for Azure. Per agent run we start a *manual
execution* of a pre-declared ACA job (``AGENT_RUNNER_JOB_NAME``) with a
per-execution template override carrying the agent image + env, then poll the
execution to completion.

I/O exchange mirrors DockerRuntime's /run bind-mount, but over an **Azure Files**
share mounted at /run inside the job container: the worker writes
``inputs.json`` to ``{run_id}/{node_id}/`` on the share before starting and
reads ``outputs.json`` back after the execution finishes. The share is reached
via the storage data plane (``DefaultAzureCredential`` = worker managed
identity, ``token_intent="backup"`` for AAD on SMB shares).

Hardening intent (mirrors DockerRuntime): restart=Never is the job's trigger
type (declared in bicep), the override drops to the agent image only, and the
job runs inside the ACA workload subnet with no extra privilege.

The Azure SDK clients are referenced via module-level names so unit tests can
monkeypatch them without real credentials or network I/O.
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

from azure.identity import DefaultAzureCredential
from azure.mgmt.appcontainers import ContainerAppsAPIClient
from azure.mgmt.appcontainers import models as aca_models
from azure.storage.fileshare import ShareServiceClient

from app.runtime import RunResult

_log = logging.getLogger(__name__)

# Execution states that mean the job is no longer running.
_TERMINAL_STATES = {"Succeeded", "Failed", "Degraded", "Stopped"}


class ACAJobRuntime:
    def __init__(
        self,
        *,
        job_name: str,
        resource_group: str,
        subscription_id: str,
        share_name: str,
        storage_account: str,
        poll_interval_s: float = 2.0,
        cpu: float = 1.0,
        memory: str = "2Gi",
    ) -> None:
        if not (job_name and resource_group and subscription_id and share_name and storage_account):
            raise ValueError(
                "ACAJobRuntime requires AGENT_RUNNER_JOB_NAME, AZURE_RESOURCE_GROUP, "
                "AZURE_SUBSCRIPTION_ID, AIGW_RUNS_SHARE and AIGW_RUNS_STORAGE_ACCOUNT"
            )
        self._job_name = job_name
        self._resource_group = resource_group
        self._poll_interval_s = poll_interval_s
        self._cpu = cpu
        self._memory = memory
        self._share_name = share_name

        self._credential = DefaultAzureCredential()
        self._client = ContainerAppsAPIClient(self._credential, subscription_id)
        self._share = ShareServiceClient(
            account_url=f"https://{storage_account}.file.core.windows.net",
            credential=self._credential,
            token_intent="backup",
        ).get_share_client(share_name)

    async def close(self) -> None:
        try:
            self._credential.close()
        except Exception:
            pass

    async def run(
        self,
        image: str,
        env: dict[str, str],
        inputs: dict[str, Any],
        *,
        run_id: str,
        node_id: str,
        timeout_s: float,
        on_log: Any = None,
        allowed_hosts: list[str] | None = None,
    ) -> RunResult:
        if allowed_hosts:
            _log.info(
                "run=%s node=%s allowed_hosts=%s (enforcement pending; v1.0)",
                run_id,
                node_id,
                allowed_hosts,
            )

        run_dir = f"{run_id}/{node_id}"
        # The job container sees the share mounted at /run, so it reads
        # /run/inputs.json and writes /run/outputs.json.
        await asyncio.to_thread(self._write_inputs, run_dir, inputs)

        template = self._build_template(image, env, run_dir)

        try:
            execution_name = await asyncio.to_thread(self._start, template)
        except Exception as exc:
            _log.error("aca job start failed for %s: %s", image, exc)
            raise

        _log.info(
            "run=%s node=%s started aca execution %s (job=%s)",
            run_id,
            node_id,
            execution_name,
            self._job_name,
        )

        try:
            status = await asyncio.wait_for(
                self._poll_until_terminal(execution_name), timeout=timeout_s
            )
        except asyncio.TimeoutError:
            _log.warning("aca execution %s timed out, stopping", execution_name)
            try:
                await asyncio.to_thread(self._stop, execution_name)
            except Exception:
                pass
            raise
        finally:
            pass

        outputs = await asyncio.to_thread(self._read_outputs, run_dir)
        # Best-effort cleanup of the run dir; keep going if it fails.
        try:
            await asyncio.to_thread(self._cleanup, run_dir)
        except Exception as exc:
            _log.debug("run dir cleanup failed for %s: %s", run_dir, exc)

        exit_code = 0 if status == "Succeeded" else 1
        return RunResult(
            exit_code=exit_code,
            outputs=outputs,
            stdout_tail=f"aca execution {execution_name} status={status}",
        )

    # ------------------------------------------------------------------
    # Azure mgmt-plane helpers (sync; called via asyncio.to_thread)
    # ------------------------------------------------------------------

    def _build_template(
        self, image: str, env: dict[str, str], run_dir: str
    ) -> aca_models.JobExecutionTemplate:
        env_vars = [aca_models.EnvironmentVar(name=k, value=v) for k, v in env.items()]
        # Carry the run id + share-relative inputs path so the agent can locate
        # its I/O dir on the mounted share.
        env_vars.append(aca_models.EnvironmentVar(name="AIGW_RUN_DIR", value=run_dir))
        env_vars.append(
            aca_models.EnvironmentVar(name="AIGW_INPUTS_PATH", value="/run/inputs.json")
        )
        container = aca_models.JobExecutionContainer(
            image=image,
            name="agent",
            env=env_vars,
            resources=aca_models.ContainerResources(cpu=self._cpu, memory=self._memory),
        )
        return aca_models.JobExecutionTemplate(containers=[container])

    def _start(self, template: aca_models.JobExecutionTemplate) -> str:
        poller = self._client.jobs.begin_start(
            self._resource_group, self._job_name, template=template
        )
        execution = poller.result()
        return execution.name

    def _poll_until_terminal_once(self, execution_name: str) -> str | None:
        for execution in self._client.jobs_executions.list(self._resource_group, self._job_name):
            if execution.name == execution_name:
                status = execution.status
                # status is a JobExecutionRunningState enum (str subclass) or None.
                return str(status) if status is not None else None
        return None

    async def _poll_until_terminal(self, execution_name: str) -> str:
        while True:
            status = await asyncio.to_thread(self._poll_until_terminal_once, execution_name)
            if status in _TERMINAL_STATES:
                return status
            await asyncio.sleep(self._poll_interval_s)

    def _stop(self, execution_name: str) -> None:
        self._client.jobs.begin_stop_execution(
            self._resource_group, self._job_name, execution_name
        ).result()

    # ------------------------------------------------------------------
    # Azure Files data-plane helpers (sync; called via asyncio.to_thread)
    # ------------------------------------------------------------------

    def _dir_client(self, run_dir: str):
        return self._share.get_directory_client(run_dir)

    def _write_inputs(self, run_dir: str, inputs: dict[str, Any]) -> None:
        # Ensure the per-run directory chain exists, then upload inputs.json and
        # an empty outputs.json (so the agent can be permissive in failure cases).
        run_id, _, node_id = run_dir.partition("/")
        for path in (run_id, run_dir):
            try:
                self._share.get_directory_client(path).create_directory()
            except Exception:
                pass  # already exists
        dir_client = self._dir_client(run_dir)
        payload = json.dumps(inputs).encode("utf-8")
        dir_client.get_file_client("inputs.json").upload_file(payload)
        dir_client.get_file_client("outputs.json").upload_file(b"{}")

    def _read_outputs(self, run_dir: str) -> dict[str, Any]:
        try:
            stream = self._dir_client(run_dir).get_file_client("outputs.json").download_file()
            raw = stream.readall()
        except Exception as exc:
            _log.warning("failed to read outputs.json for %s: %s", run_dir, exc)
            return {}
        try:
            return json.loads(raw) or {}
        except (json.JSONDecodeError, ValueError) as exc:
            _log.warning("failed to parse outputs.json for %s: %s", run_dir, exc)
            return {}

    def _cleanup(self, run_dir: str) -> None:
        dir_client = self._dir_client(run_dir)
        for name in ("inputs.json", "outputs.json"):
            try:
                dir_client.delete_file(name)
            except Exception:
                pass
        try:
            dir_client.delete_directory()
        except Exception:
            pass
