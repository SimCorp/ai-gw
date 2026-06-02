"""KubernetesRuntime — creates a K8s Job per node invocation.

Production path for AKS deployment. Not active in local dev (DockerRuntime
is used there). Enable by setting AGENT_CONTAINER_RUNTIME=kubernetes in
the workflow-worker environment.

Wiring it up
------------
1. Install the async client::

       pip install kubernetes-asyncio

2. Provide cluster credentials via one of:
   - ``KUBECONFIG`` env var pointing to a kubeconfig file, or
   - In-cluster service account (automatic when running inside AKS).

3. Set ``AGENT_CONTAINER_RUNTIME=kubernetes`` in the workflow-worker
   environment (e.g. docker-compose override or Helm values).

4. Ensure the ``aigateway`` namespace exists and the service account has
   ``create``/``get``/``watch`` permissions on ``batch/jobs`` and
   ``get``/``watch`` on ``pods``.

5. For shared outputs, either:
   - Have the agent write to ``/run/outputs.json`` on a shared PVC (set
     ``AIGW_RUNS_PVC`` to the PVC name), or
   - Read outputs from the pod's stdout log (simpler, good for small payloads).

Current status: **stub — v0.5 scope**. The interface is implemented but
``run()`` raises ``NotImplementedError`` until ``kubernetes-asyncio`` is
installed and the cluster is configured.
"""

from __future__ import annotations

import logging
import os
from typing import Any

from app.runtime import RunResult

_log = logging.getLogger(__name__)

_NAMESPACE = "aigateway"


class KubernetesRuntime:
    """Implements ``ContainerRuntime`` by launching a Kubernetes Job per agent node.

    Parameters
    ----------
    namespace:
        Kubernetes namespace in which Jobs are created. Defaults to
        ``"aigateway"``.
    kubeconfig:
        Path to kubeconfig file. When ``None`` (the default), the
        in-cluster service account is used.
    runs_pvc:
        Name of a ReadWriteMany PVC that is mounted at ``/run`` inside
        each Job pod. When present, ``outputs.json`` is read from there.
        When ``None``, outputs are read from the pod's stdout log.
    """

    def __init__(
        self,
        namespace: str = _NAMESPACE,
        kubeconfig: str | None = None,
        runs_pvc: str | None = None,
    ) -> None:
        self._namespace = namespace
        self._kubeconfig = kubeconfig or os.getenv("KUBECONFIG")
        self._runs_pvc = runs_pvc or os.getenv("AIGW_RUNS_PVC")

    # ------------------------------------------------------------------
    # ContainerRuntime interface
    # ------------------------------------------------------------------

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
    ) -> RunResult:
        """Create a Kubernetes Job and wait for it to complete.

        Not yet implemented — install ``kubernetes-asyncio`` and configure
        your cluster credentials before enabling this runtime.

        Intended production flow
        ------------------------
        1. Create a ``v1.ConfigMap`` in ``self._namespace`` containing
           ``inputs.json`` serialised from ``inputs``.
        2. Create a ``batch/v1.Job`` with:
           - ``spec.template.spec.containers[0].image = image``
           - Env vars from ``env`` injected as ``envFrom`` / ``env`` entries.
           - The ConfigMap mounted at ``/run/inputs.json``.
           - An ``emptyDir`` (or shared PVC) mounted at ``/run`` for outputs.
        3. Poll ``batch/v1/namespaces/{ns}/jobs/{name}`` until
           ``status.succeeded > 0`` or ``status.failed > 0``, up to
           ``timeout_s``.
        4. Read ``outputs.json`` from the pod log (or PVC) and return a
           ``RunResult``.
        5. Delete the Job and ConfigMap to avoid namespace pollution.

        Raises
        ------
        NotImplementedError
            Always, until this runtime is fully wired up.
        """
        raise NotImplementedError(
            "KubernetesRuntime: install kubernetes-asyncio and configure your cluster. "
            "See the module docstring for full wiring instructions. "
            "Set AGENT_CONTAINER_RUNTIME=docker (or relay) to use the available runtimes."
        )

    async def close(self) -> None:
        """No-op: connection lifecycle managed per-call by kubernetes-asyncio."""
