"""ContainerRuntime port.

Three impls:
- DockerRuntime  — uses host docker.sock via aiodocker (local dev)
- ACAJobRuntime  — Azure Container Apps Jobs executions (Azure deployment)
- RelayRuntime   — forwards relay:// agents to the agent-relay service
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Protocol


@dataclass
class RunResult:
    exit_code: int
    outputs: dict[str, Any]
    stdout_tail: str  # last N lines of stdout for log/debug


class ContainerRuntime(Protocol):
    async def run(
        self,
        image: str,
        env: dict[str, str],
        inputs: dict[str, Any],
        *,
        run_id: str,
        node_id: str,
        timeout_s: float,
        on_log: Callable | None = None,
    ) -> RunResult: ...
