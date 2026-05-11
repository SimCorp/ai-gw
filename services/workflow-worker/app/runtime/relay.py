"""RelayRuntime — implements ContainerRuntime by invoking a relay agent.

Instead of spawning a Docker container, this runtime forwards the invocation
to the Agent Relay service over HTTP. The relay service, in turn, forwards
it to a laptop-hosted agent connected via WebSocket.

Image format: "relay://{slug}" signals relay dispatch.
"""
from __future__ import annotations

import logging
from typing import Any

import httpx

from app.runtime import RunResult

_log = logging.getLogger(__name__)


class RelayRuntime:
    def __init__(self, relay_url: str, relay_secret: str = "") -> None:
        self._relay_url = relay_url.rstrip("/")
        self._relay_secret = relay_secret

    async def run(
        self,
        image: str,
        env: dict[str, str],
        inputs: dict[str, Any],
        *,
        run_id: str,
        node_id: str,
        timeout_s: float,
        on_log=None,
    ) -> RunResult:
        """Dispatch the invocation to the relay service and await the result.

        image must be in the form "relay://{slug}".
        """
        slug = image.removeprefix("relay://")
        _log.info("relay dispatch: slug=%s run_id=%s node_id=%s", slug, run_id, node_id)

        headers: dict[str, str] = {}
        if self._relay_secret:
            headers["X-Relay-Secret"] = self._relay_secret

        async with httpx.AsyncClient() as client:
            try:
                resp = await client.post(
                    f"{self._relay_url}/invoke/{slug}",
                    json={
                        "inputs": inputs,
                        "env": env,
                        "run_id": run_id,
                        "node_id": node_id,
                    },
                    headers=headers,
                    timeout=timeout_s,
                )
            except httpx.TimeoutException:
                _log.warning("relay timeout for slug=%s run_id=%s", slug, run_id)
                import asyncio
                raise asyncio.TimeoutError()
            except httpx.RequestError as exc:
                _log.error("relay request error for slug=%s: %s", slug, exc)
                raise

        if resp.status_code == 503:
            raise RuntimeError(f"relay agent '{slug}' not connected: {resp.text}")
        if resp.status_code == 504:
            import asyncio
            raise asyncio.TimeoutError()
        if not resp.is_success:
            raise RuntimeError(f"relay invoke failed ({resp.status_code}): {resp.text}")

        data = resp.json()
        outputs = data.get("outputs") or {}
        exit_code = int(data.get("exit_code", 0))

        if on_log is not None:
            try:
                await on_log(f"relay agent '{slug}' completed with exit_code={exit_code}")
            except Exception:
                pass

        return RunResult(
            exit_code=exit_code,
            outputs=outputs,
            stdout_tail=f"relay://{slug} exit_code={exit_code}",
        )
