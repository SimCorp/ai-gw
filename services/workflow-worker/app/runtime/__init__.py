"""ContainerRuntime port.

Two impls (only Docker in v0.1; Kubernetes lands with AKS deployment in v0.5):
- DockerRuntime  — uses host docker.sock via aiodocker
- KubernetesRuntime — v0.5+, not in this milestone
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, AsyncIterator, Protocol


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
        log_stream: AsyncIterator[str] | None = None,
    ) -> RunResult: ...
