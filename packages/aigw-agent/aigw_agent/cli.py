"""aigw-agent CLI — register a local agent with the AI Gateway relay service.

Usage
-----
    aigw-agent serve agents/echo/main.py --slug my-echo
    aigw-agent status
"""
from __future__ import annotations

import asyncio
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

import click
import httpx
import websockets
from rich.console import Console
from rich.live import Live
from rich.table import Table

DEFAULT_RELAY_URL = "http://localhost:8007"

console = Console()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _ws_url(relay_url: str, path: str) -> str:
    """Convert an http(s) relay URL to a ws(s) URL for the given path."""
    base = relay_url.rstrip("/")
    if base.startswith("https://"):
        base = "wss://" + base[len("https://"):]
    elif base.startswith("http://"):
        base = "ws://" + base[len("http://"):]
    return f"{base}{path}"


async def _register(relay_url: str, slug: str, name: str) -> str:
    """POST /register and return the relay_token."""
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"{relay_url.rstrip('/')}/register",
            json={"slug": slug, "name": name, "capabilities": []},
            timeout=10.0,
        )
        resp.raise_for_status()
        data = resp.json()
        token: str = data["relay_token"]
        return token


async def _invoke_script(script: str, inputs: dict[str, Any], env: dict[str, str]) -> tuple[dict[str, Any], int]:
    """Write inputs.json, run the script, read outputs.json."""
    with tempfile.TemporaryDirectory(prefix="aigw-run-") as tmp:
        tmp_path = Path(tmp)
        inputs_file = tmp_path / "inputs.json"
        outputs_file = tmp_path / "outputs.json"

        inputs_file.write_text(json.dumps(inputs))

        child_env = {**os.environ}
        for k, v in env.items():
            child_env[k] = v
        child_env["AIGW_INPUTS_PATH"] = str(inputs_file)
        child_env["AIGW_OUTPUTS_PATH"] = str(outputs_file)

        proc = await asyncio.create_subprocess_exec(
            sys.executable,
            script,
            cwd=str(Path(script).parent),
            env=child_env,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        _stdout, _stderr = await proc.communicate()
        exit_code = proc.returncode or 0

        outputs: dict[str, Any] = {}
        if outputs_file.exists():
            try:
                outputs = json.loads(outputs_file.read_text())
            except json.JSONDecodeError:
                outputs = {"_raw": outputs_file.read_text()}

        return outputs, exit_code


# ---------------------------------------------------------------------------
# Serve command
# ---------------------------------------------------------------------------

async def _serve_loop(
    script: str,
    relay_url: str,
    slug: str,
    name: str,
) -> None:
    console.print(f"[bold]Registering[/bold] slug=[cyan]{slug}[/cyan] name=[cyan]{name}[/cyan] ...")

    try:
        token = await _register(relay_url, slug, name)
    except Exception as exc:
        console.print(f"[red]Registration failed:[/red] {exc}")
        raise SystemExit(1) from exc

    ws_endpoint = _ws_url(relay_url, f"/connect/{token}")
    console.print(f"[green]Registered.[/green] Connecting to relay WebSocket ...")

    stats = {"received": 0, "completed": 0, "errors": 0}

    def _make_table() -> Table:
        table = Table(title="aigw-agent", show_header=True, header_style="bold magenta")
        table.add_column("Stat", style="cyan")
        table.add_column("Value", justify="right")
        table.add_row("Status", "[green]connected[/green]")
        table.add_row("Relay URL", relay_url)
        table.add_row("Slug", slug)
        table.add_row("Script", script)
        table.add_row("Invocations received", str(stats["received"]))
        table.add_row("Invocations completed", str(stats["completed"]))
        table.add_row("Errors", str(stats["errors"]))
        return table

    stop = asyncio.Event()

    async def _heartbeat_loop(identity_url: str, hb_slug: str, interval: float = 30.0) -> None:
        """Ping the identity service so the agent shows as 'online'."""
        while not stop.is_set():
            try:
                async with httpx.AsyncClient(timeout=5) as c:
                    await c.post(f"{identity_url.rstrip('/')}/agents/{hb_slug}/heartbeat")
            except Exception:
                pass  # identity service optional — never block serve
            try:
                await asyncio.wait_for(stop.wait(), timeout=interval)
            except asyncio.TimeoutError:
                pass

    def _handle_sigint():
        console.print("\n[yellow]Shutting down ...[/yellow]")
        stop.set()

    loop = asyncio.get_running_loop()
    try:
        loop.add_signal_handler(__import__("signal").SIGINT, _handle_sigint)
    except NotImplementedError:
        pass  # Windows

    async with websockets.connect(ws_endpoint) as ws:
        console.print(f"[bold green]Connected.[/bold green] Waiting for invocations. Press Ctrl+C to stop.\n")
        # Ping identity service every 30s so this agent shows as online
        identity_url = relay_url.replace(":8007", ":8006")  # best-effort; override via IDENTITY_URL env
        identity_url = __import__("os").environ.get("IDENTITY_URL", identity_url)
        asyncio.create_task(_heartbeat_loop(identity_url, slug))
        with Live(_make_table(), refresh_per_second=4, console=console) as live:
            while not stop.is_set():
                try:
                    raw = await asyncio.wait_for(ws.recv(), timeout=1.0)
                except asyncio.TimeoutError:
                    live.update(_make_table())
                    continue
                except websockets.ConnectionClosed:
                    console.print("[yellow]WebSocket closed by relay.[/yellow]")
                    break

                try:
                    msg = json.loads(raw)
                except json.JSONDecodeError:
                    console.print(f"[red]Received non-JSON message:[/red] {raw!r}")
                    continue

                if msg.get("type") != "invoke":
                    continue

                invocation_id: str = msg.get("invocation_id", "unknown")
                inputs: dict[str, Any] = msg.get("inputs", {})
                env: dict[str, str] = msg.get("env", {})

                stats["received"] += 1
                live.update(_make_table())

                try:
                    outputs, exit_code = await _invoke_script(script, inputs, env)
                    stats["completed"] += 1
                except Exception as exc:
                    outputs = {"error": str(exc)}
                    exit_code = 1
                    stats["errors"] += 1

                result_msg = json.dumps({
                    "type": "result",
                    "invocation_id": invocation_id,
                    "outputs": outputs,
                    "exit_code": exit_code,
                })
                try:
                    await ws.send(result_msg)
                except websockets.ConnectionClosed:
                    console.print("[yellow]WebSocket closed while sending result.[/yellow]")
                    break

                live.update(_make_table())


# ---------------------------------------------------------------------------
# Click commands
# ---------------------------------------------------------------------------

@click.group()
def main() -> None:
    """SimCorp AI Gateway — laptop agent CLI."""


@main.command("serve")
@click.argument("script_or_dir")
@click.option("--relay-url", default=DEFAULT_RELAY_URL, show_default=True, help="Agent relay base URL")
@click.option("--slug", default=None, help="Agent slug (defaults to script stem)")
@click.option("--name", default=None, help="Human-readable agent name")
def serve(script_or_dir: str, relay_url: str, slug: str | None, name: str | None) -> None:
    """Register and serve a local agent script via the relay.

    SCRIPT_OR_DIR is the path to a Python script (or a directory containing
    main.py) that implements the agent. The script is invoked once per
    invocation with AIGW_INPUTS_PATH and AIGW_OUTPUTS_PATH env vars set.
    """
    path = Path(script_or_dir)
    if path.is_dir():
        path = path / "main.py"
    if not path.exists():
        console.print(f"[red]Script not found:[/red] {path}")
        raise SystemExit(1)

    script = str(path.resolve())
    effective_slug = slug or path.stem
    effective_name = name or effective_slug

    try:
        asyncio.run(_serve_loop(script, relay_url, effective_slug, effective_name))
    except SystemExit:
        raise
    except KeyboardInterrupt:
        console.print("[yellow]Interrupted.[/yellow]")


@main.command("status")
@click.option("--relay-url", default=DEFAULT_RELAY_URL, show_default=True, help="Agent relay base URL")
def status(relay_url: str) -> None:
    """List agents currently connected to the relay."""

    async def _get_agents() -> list[dict]:
        async with httpx.AsyncClient() as client:
            resp = await client.get(f"{relay_url.rstrip('/')}/agents", timeout=10.0)
            resp.raise_for_status()
            return resp.json()

    try:
        agents = asyncio.run(_get_agents())
    except Exception as exc:
        console.print(f"[red]Could not reach relay at {relay_url}:[/red] {exc}")
        raise SystemExit(1) from exc

    if not agents:
        console.print("[yellow]No agents currently connected.[/yellow]")
        return

    table = Table(title=f"Connected agents — {relay_url}", show_header=True, header_style="bold magenta")
    table.add_column("Slug", style="cyan")
    table.add_column("Name")
    table.add_column("Token", style="dim")
    table.add_column("Capabilities")

    for agent in agents:
        table.add_row(
            agent.get("slug", ""),
            agent.get("name", ""),
            agent.get("relay_token", "")[:12] + "...",
            ", ".join(agent.get("capabilities", [])) or "(none)",
        )

    console.print(table)
