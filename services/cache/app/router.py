import asyncio
import time

import httpx
from fastapi import APIRouter, Request, Response
from fastapi.responses import JSONResponse

from app import exact, semantic
from app.config import settings
from app.policy import CachePolicy, get_policy

router = APIRouter()


def _prompt_text(body: dict) -> str:
    messages = body.get("messages", [])
    return " ".join(m.get("content", "") for m in messages if isinstance(m.get("content"), str))


async def _emit_event(client: httpx.AsyncClient, event: dict) -> None:
    try:
        await client.post(f"{settings.observability_url}/events", json=event, timeout=2)
    except Exception:
        pass


async def _validate_token(client: httpx.AsyncClient, token: str, model: str | None) -> tuple[str, str | None] | None:
    """Call auth service to validate token. Returns (team_id, project_id) or None on failure."""
    try:
        resp = await client.post(
            f"{settings.auth_url}/validate",
            json={"token": token, "model": model},
            timeout=5,
        )
        if resp.status_code == 200:
            data = resp.json()
            return data["team_id"], data.get("project_id")
        return None
    except Exception:
        return None


@router.post("/v1/chat/completions")
async def chat_completions(request: Request):
    body = await request.json()
    redis = request.app.state.redis
    http = request.app.state.http

    # Validate caller token via auth service
    auth_header = request.headers.get("Authorization", "")
    token = auth_header.removeprefix("Bearer ").strip()
    result = await _validate_token(http, token, body.get("model"))
    if result is None:
        return JSONResponse({"error": "Unauthorized"}, status_code=401)
    team_id, project_id = result

    try:
        policy = await get_policy(team_id, project_id, redis)
    except Exception:
        policy = CachePolicy(
            ttl_seconds=settings.default_ttl_seconds,
            similarity_threshold=settings.default_similarity_threshold,
            opt_out=False,
            embedding_model=settings.embedding_model,
        )
    start = time.monotonic()

    emb: list[float] | None = None
    if not policy.opt_out:
        # 1. Exact match
        try:
            cached = await exact.get(body, redis)
            if cached:
                asyncio.create_task(
                    _emit_event(http, {"team_id": team_id, "project_id": project_id, "model": body.get("model"), "cache_hit": True, "latency_ms": int((time.monotonic() - start) * 1000)})
                )
                return JSONResponse(cached, headers={"X-Cache": "HIT"})
        except Exception:
            pass  # Redis failure → fail open

        # 2. Semantic match
        try:
            emb = await semantic.embed(_prompt_text(body), policy.embedding_model)
            cached = await semantic.get(emb, policy.similarity_threshold, redis)
            if cached:
                asyncio.create_task(
                    _emit_event(http, {"team_id": team_id, "project_id": project_id, "model": body.get("model"), "cache_hit": True, "latency_ms": int((time.monotonic() - start) * 1000)})
                )
                return JSONResponse(cached, headers={"X-Cache": "HIT"})
        except Exception:
            emb = None  # embedding failure → treat as miss

    # 3. Forward to LiteLLM with master key (not caller's token)
    headers = {
        k: v for k, v in request.headers.items()
        if k.lower() not in ("host", "content-length", "authorization")
    }
    headers["Authorization"] = f"Bearer {settings.litellm_master_key}"
    resp = await http.post(f"{settings.litellm_url}/v1/chat/completions", json=body, headers=headers, timeout=600)
    response_body = resp.json()

    # Store in cache on success
    if resp.status_code == 200 and not policy.opt_out:
        try:
            await exact.set(body, response_body, policy.ttl_seconds, redis)
        except Exception:
            pass
        if emb is not None:
            try:
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
