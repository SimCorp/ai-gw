"""Redis queue worker — polls for jobs and executes scan containers."""

import asyncio
import json
import logging
import os
import socket
from typing import Any

import httpx

from app.config import settings
from app.worker.parsers.garak import parse_garak_jsonl
from app.worker.parsers.nmap import parse_nmap_xml
from app.worker.parsers.nuclei import parse_nuclei_json

log = logging.getLogger(__name__)
WORKER_ID = f"{socket.gethostname()}-{os.getpid()}"

_TIER_NMAP_ARGS: dict[str, list[str]] = {
    "quick": ["--top-ports", "100", "-T4"],
    "standard": ["--top-ports", "1000", "-T4", "-sV"],
    "deep": ["-p-", "-T4", "-sV", "-sC"],
}
_TIER_NUCLEI_TEMPLATES: dict[str, list[str]] = {
    "quick": ["http/technologies"],
    "standard": ["http/vulnerabilities", "http/misconfiguration", "http/exposures"],
    "deep": [
        "http/vulnerabilities",
        "http/misconfiguration",
        "http/exposures",
        "http/cves",
        "http/takeovers",
        "network",
    ],
}
_TIER_GARAK_PROBES: dict[str, list[str]] = {
    "quick": [
        "promptinjection.HijackHateHumans",
        "promptinjection.HijackKillHumans",
        "leakage.SnapshotData",
        "jailbreak.Dan",
        "toxicity.ToxicCommentModel",
    ],
    "standard": ["promptinjection", "jailbreak", "leakage", "xss", "toxicity"],
    "deep": [],
}

_docker_client = None


def _docker():
    global _docker_client
    if _docker_client is None:
        import docker

        _docker_client = docker.from_env()
    return _docker_client


async def _post_internal(path: str, payload: Any) -> None:
    async with httpx.AsyncClient(timeout=30.0) as client:
        await client.post(
            f"http://localhost:8011{path}",
            json=payload,
            headers={"Authorization": f"Bearer {settings.scanner_worker_secret}"},
        )


def _run_container(
    image: str, command: list[str], timeout: int = settings.max_container_timeout_seconds
) -> str:
    container = _docker().containers.run(
        image,
        command=command,
        detach=True,
        remove=False,
        network=settings.docker_network,
    )
    try:
        container.wait(timeout=timeout)
        output = container.logs(stdout=True, stderr=False).decode("utf-8", errors="replace")
    except Exception as exc:
        log.warning("Container %s timed out or failed: %s", container.id, exc)
        container.kill()
        output = container.logs(stdout=True, stderr=False).decode("utf-8", errors="replace")
    finally:
        container.remove(force=True)
    return output


async def _run_nmap(job_id: str, target_url: str, tier: str) -> None:
    from urllib.parse import urlparse

    host = urlparse(target_url).hostname or target_url
    args = _TIER_NMAP_ARGS.get(tier, _TIER_NMAP_ARGS["quick"])
    command = ["-oX", "-"] + args + [host]
    log.info("Running nmap for job %s", job_id)
    xml_output = await asyncio.to_thread(_run_container, "instrumentisto/nmap", command)
    findings = parse_nmap_xml(xml_output)
    if findings:
        await _post_internal(f"/internal/jobs/{job_id}/findings", {"findings": findings})


async def _run_nuclei(job_id: str, target_url: str, tier: str) -> None:
    templates = _TIER_NUCLEI_TEMPLATES.get(tier, _TIER_NUCLEI_TEMPLATES["quick"])
    template_args: list[str] = []
    for t in templates:
        template_args += ["-t", t]
    command = ["-u", target_url, "-json"] + template_args + ["-silent", "-no-color"]
    log.info("Running nuclei for job %s", job_id)
    raw_output = await asyncio.to_thread(_run_container, "projectdiscovery/nuclei", command)
    records = []
    for line in raw_output.splitlines():
        try:
            records.append(json.loads(line))
        except json.JSONDecodeError:
            pass
    findings = parse_nuclei_json(records)
    if findings:
        await _post_internal(f"/internal/jobs/{job_id}/findings", {"findings": findings})


async def _run_zap(job_id: str, target_url: str, openapi_spec_url: str) -> None:
    command = [
        "zap-api-scan.py",
        "-t",
        openapi_spec_url,
        "-f",
        "openapi",
        "-J",
        "/zap/results.json",
        "-I",
    ]
    log.info("Running ZAP for job %s against spec %s", job_id, openapi_spec_url)
    await asyncio.to_thread(_run_container, "zaproxy/zap-stable", command)
    findings = [
        {
            "scanner": "zap",
            "severity": "info",
            "category": "api_vuln",
            "title": "ZAP API scan completed",
            "description": f"ZAP deep API scan ran against OpenAPI spec at {openapi_spec_url}.",
            "evidence": {"spec_url": openapi_spec_url},
            "remediation": None,
        }
    ]
    await _post_internal(f"/internal/jobs/{job_id}/findings", {"findings": findings})


async def _run_garak(job_id: str, target_url: str, tier: str) -> None:
    probes = _TIER_GARAK_PROBES.get(tier, _TIER_GARAK_PROBES["quick"])
    probe_args: list[str] = []
    for p in probes:
        probe_args += ["--probe", p]
    command = [
        "--model_type",
        "rest",
        "--model_name",
        target_url,
        "--report_prefix",
        "/tmp/garak_out",
        "--parallel_requests",
        "1",
    ] + probe_args
    log.info("Running garak for job %s", job_id)
    raw_output = await asyncio.to_thread(_run_container, "ai-gateway/garak:latest", command)
    findings = parse_garak_jsonl(raw_output)
    if findings:
        await _post_internal(f"/internal/jobs/{job_id}/findings", {"findings": findings})


async def process_job(job_payload: dict) -> None:
    job_id = job_payload["job_id"]
    target_url = job_payload["target_url"]
    scan_types = job_payload.get("scan_types", ["ai", "api", "network"])
    tier = job_payload.get("tier", "quick")
    openapi_spec_url = job_payload.get("openapi_spec_url")

    await _post_internal(f"/internal/jobs/{job_id}/progress", {"worker_id": WORKER_ID})

    tasks = []
    if "network" in scan_types or "api" in scan_types:
        tasks.append(_run_nmap(job_id, target_url, tier))
    if "api" in scan_types:
        tasks.append(_run_nuclei(job_id, target_url, tier))
    if "api" in scan_types and tier == "deep" and openapi_spec_url:
        tasks.append(_run_zap(job_id, target_url, openapi_spec_url))

    partial = False
    try:
        await asyncio.gather(*tasks)
        if "ai" in scan_types:
            await _run_garak(job_id, target_url, tier)
        status = "completed"
    except asyncio.TimeoutError:
        partial = True
        status = "completed"
    except Exception as exc:
        log.error("Job %s failed: %s", job_id, exc)
        await _post_internal(
            f"/internal/jobs/{job_id}/complete",
            {
                "status": "failed",
                "error_message": str(exc),
                "partial_results": False,
            },
        )
        return

    await _post_internal(
        f"/internal/jobs/{job_id}/complete",
        {
            "status": status,
            "error_message": None,
            "partial_results": partial,
        },
    )


async def run_worker(redis) -> None:
    log.info("Scanner worker %s started", WORKER_ID)
    while True:
        try:
            item = await redis.brpop(settings.scan_job_queue_key, timeout=5)
            if item is None:
                continue
            _, raw = item
            payload = json.loads(raw)
            asyncio.create_task(process_job(payload))
        except asyncio.CancelledError:
            break
        except Exception as exc:
            log.error("Worker error: %s", exc)
            await asyncio.sleep(2)
