"""DockerRuntime — spawns a sibling container via the host docker.sock.

Inputs/outputs flow through a bind-mounted directory at /run inside the agent
container. The host path is HOST_RUNS_PATH/{run_id}/{node_id}/ and is also
visible inside the worker (mounted at /worker-runs/{run_id}/{node_id}/) so we
can write inputs.json before launching, and read outputs.json after exit.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import shutil
from typing import Any

import aiodocker

from app.runtime import RunResult

_log = logging.getLogger(__name__)


class DockerRuntime:
    def __init__(self, host_runs_path: str, worker_runs_path: str, container_network: str):
        self._client = aiodocker.Docker()
        self._host_runs_path = host_runs_path.rstrip("/")
        self._worker_runs_path = worker_runs_path.rstrip("/")
        self._network = container_network

    async def close(self) -> None:
        await self._client.close()

    async def run(
        self,
        image: str,
        env: dict[str, str],
        inputs: dict[str, Any],
        *,
        run_id: str,
        node_id: str,
        timeout_s: float,
        on_log: callable | None = None,
    ) -> RunResult:
        # Prepare the per-invocation directory (visible at both worker and agent paths)
        worker_dir = f"{self._worker_runs_path}/{run_id}/{node_id}"
        host_dir = f"{self._host_runs_path}/{run_id}/{node_id}"
        os.makedirs(worker_dir, exist_ok=True)
        with open(f"{worker_dir}/inputs.json", "w") as f:
            json.dump(inputs, f)
        # Initialise an empty outputs.json so the agent can be permissive in failure cases
        if not os.path.exists(f"{worker_dir}/outputs.json"):
            with open(f"{worker_dir}/outputs.json", "w") as f:
                f.write("{}")

        # Build & run the container
        binds = [f"{host_dir}:/run"]
        env_list = [f"{k}={v}" for k, v in env.items()]

        try:
            container = await self._client.containers.run(
                config={
                    "Image": image,
                    "Env": env_list,
                    "HostConfig": {
                        "Binds": binds,
                        "NetworkMode": self._network,
                        "AutoRemove": False,
                        "ReadonlyRootfs": True,
                        "CapDrop": ["ALL"],
                        "SecurityOpt": ["no-new-privileges:true"],
                    },
                    "AttachStdout": True,
                    "AttachStderr": True,
                },
                name=f"aigw-run-{run_id[:8]}-{node_id}-{int(asyncio.get_event_loop().time()*1000)}",
            )
        except aiodocker.exceptions.DockerError as exc:
            _log.error("docker run failed for %s: %s", image, exc)
            raise

        # Stream logs as they appear
        stdout_lines: list[str] = []
        try:
            log_task = asyncio.create_task(self._stream_logs(container, stdout_lines, on_log))
            try:
                await asyncio.wait_for(container.wait(), timeout=timeout_s)
            except asyncio.TimeoutError:
                _log.warning("container timeout, killing %s", container.id)
                try:
                    await container.kill()
                except Exception:
                    pass
                raise
            finally:
                log_task.cancel()
                try:
                    await log_task
                except asyncio.CancelledError:
                    pass

            info = await container.show()
            exit_code = info.get("State", {}).get("ExitCode", -1)

            # Read outputs.json from the shared dir
            outputs: dict[str, Any] = {}
            outputs_file = f"{worker_dir}/outputs.json"
            if os.path.exists(outputs_file):
                try:
                    with open(outputs_file) as f:
                        outputs = json.load(f) or {}
                except (json.JSONDecodeError, OSError) as exc:
                    _log.warning("failed to parse outputs.json for %s/%s: %s", run_id, node_id, exc)

            return RunResult(
                exit_code=exit_code,
                outputs=outputs,
                stdout_tail="\n".join(stdout_lines[-50:]),
            )
        finally:
            # Clean up container; keep the dir for one cycle in case of inspection
            try:
                await container.delete(force=True)
            except Exception:
                pass

    async def _stream_logs(self, container, stdout_lines: list[str], on_log: callable | None) -> None:
        try:
            async for line in container.log(stdout=True, stderr=True, follow=True):
                # aiodocker yields strings already
                line = line.rstrip("\n")
                stdout_lines.append(line)
                if on_log is not None:
                    try:
                        await on_log(line)
                    except Exception:
                        pass
        except Exception as exc:
            _log.debug("log stream ended: %s", exc)
