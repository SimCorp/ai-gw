import asyncio
import json
import time

import httpx
from fastapi import APIRouter, Request, Response
from fastapi.responses import JSONResponse

from app import exact, semantic
from app.config import settings
from app.policy import get_policy

router = APIRouter()


def _prompt_text(body: dict) -> str:
    """Extract a single string from the messages list for embedding."""
    messages = body.get("messages", [])
    return " ".join(m.get("content", "") for m in messages if isinstance(m.get("content"), str))


async def _emit_event(client: httpx.AsyncClient, event: dict) -> None:
    try:
        await client.post(f"{settings.observability_url}/events", json=event, timeout=2)
    except Exception:
        pass  # observability failure must never block the request path


@router.post("/v1/chat/completions")
async def chat_completions(request: Request):
    body = await request.json()
    redis = request.app.state.redis
    http = request.app.state.http

    team_id = request.headers.get("X-Team-Id", "unknown")
    project_id = request.headers.get("X-Project-Id")

    policy = await get_policy(team_id, project_id, redis)
    start = time.monotonic()

    if not policy.opt_out:
        # 1. Exact match
        cached = await exact.get(body, redis)
        if cached:
            asyncio.create_task(
                _emit_event(http, {"team_id": team_id, "project_id": project_id, "model": body.get("model"), "cache_hit": True, "latency_ms": int((time.monotonic() - start) * 1000)})
            )
            return JSONResponse(cached, headers={"X-Cache": "HIT"})

        # 2. Semantic match
        try:
            emb = await semantic.embed(_prompt_text(body), settings)
            cached = await semantic.get(emb, policy.similarity_threshold, redis)
            if cached:
                asyncio.create_task(
                    _emit_event(http, {"team_id": team_id, "project_id": project_id, "model": body.get("model"), "cache_hit": True, "latency_ms": int((time.monotonic() - start) * 1000)})
                )
                return JSONResponse(cached, headers={"X-Cache": "HIT"})
        except Exception:
            pass  # embedding failure → treat as miss

    # 3. Forward to LiteLLM
    headers = {k: v for k, v in request.headers.items() if k.lower() not in ("host", "content-length")}
    resp = await http.post(f"{settings.litellm_url}/v1/chat/completions", json=body, headers=headers, timeout=600)
    response_body = resp.json()

    # Store in cache on success
    if resp.status_code == 200 and not policy.opt_out:
        await exact.set(body, response_body, policy.ttl_seconds, redis)
        try:
            if "emb" in dir():
                await semantic.set(emb, response_body, policy.ttl_seconds, redis)
        except Exception:
            pass

    usage = response_body.get("usage", {})
    asyncio.create_task(
        _emit_event(http, {
            "team_id": team_id,
            "project_id": project_id,
            "model": body.get("model"),
            "tokens_input": usage.get("prompt_tokens", 0),
            "tokens_output": usage.get("completion_tokens", 0),
            "cache_hit": False,
            "latency_ms": int((time.monotonic() - start) * 1000),
            "error": None if resp.status_code == 200 else str(resp.status_code),
        })
    )
    return Response(content=resp.content, status_code=resp.status_code, media_type="application/json", headers={"X-Cache": "MISS"})
