import asyncio
import hashlib
import json as _json
import logging
import re
import time
from typing import NamedTuple

import httpx
from fastapi import APIRouter, Request, Response
from fastapi.responses import JSONResponse, StreamingResponse

from app import exact, semantic
from app.config import settings
from app.policy import CachePolicy, get_policy

router = APIRouter()

# ---------------------------------------------------------------------------
# Streaming SSE usage parsers — recover token counts from stream tail
# ---------------------------------------------------------------------------

def _parse_sse_usage_openai(tail: bytes) -> tuple[int, int]:
    """Extract prompt/completion tokens from OpenAI-format SSE tail bytes."""
    text = tail.decode("utf-8", errors="ignore")
    for line in reversed(text.splitlines()):
        if not line.startswith("data: "):
            continue
        payload = line[6:].strip()
        if payload in ("[DONE]", ""):
            continue
        try:
            obj = _json.loads(payload)
            usage = obj.get("usage") or {}
            p = usage.get("prompt_tokens", 0)
            c = usage.get("completion_tokens", 0)
            if p or c:
                return p, c
        except Exception:
            continue
    return 0, 0


def _parse_sse_usage_anthropic(tail: bytes) -> tuple[int, int]:
    """Extract input/output tokens from Anthropic native SSE format."""
    text = tail.decode("utf-8", errors="ignore")
    input_tokens = output_tokens = 0
    for line in text.splitlines():
        if not line.startswith("data: "):
            continue
        try:
            obj = _json.loads(line[6:])
            t = obj.get("type", "")
            if t == "message_start":
                usage = (obj.get("message") or {}).get("usage") or {}
                input_tokens = usage.get("input_tokens", 0)
            elif t == "message_delta":
                usage = obj.get("usage") or {}
                output_tokens = usage.get("output_tokens", output_tokens)
        except Exception:
            continue
    return input_tokens, output_tokens


async def _tracked_stream(upstream, emit_coro_fn, parse_fn=_parse_sse_usage_openai):
    """Pass-through async generator that fires emit_coro_fn(tokens_in, tokens_out) after stream ends."""
    tail = bytearray()
    async for chunk in upstream.aiter_raw():
        yield chunk
        tail.extend(chunk)
        if len(tail) > 8192:
            tail = tail[-4096:]  # keep last 4 KB — enough for the usage chunk
    tokens_in, tokens_out = parse_fn(bytes(tail))
    asyncio.create_task(emit_coro_fn(tokens_in, tokens_out))


# ---------------------------------------------------------------------------
# Intent classifier — lightweight keyword detection, no prompt storage
# ---------------------------------------------------------------------------

_INTENT_PATTERNS: list[tuple[str, re.Pattern]] = [
    ("debugging",      re.compile(r'\b(error|exception|traceback|bug|fix|crash|fail|broken|why\s+is|why\s+does|not\s+work)\b', re.I)),
    ("testing",        re.compile(r'\b(test|spec|mock|assert|coverage|pytest|unittest|jest|vitest)\b', re.I)),
    ("refactoring",    re.compile(r'\b(refactor|clean\s*up|simplify|restructure|rename|extract|split|consolidate)\b', re.I)),
    ("code_review",    re.compile(r'\b(review|check|look\s+at|feedback|improve|suggest|what\s+do\s+you\s+think|critique)\b', re.I)),
    ("documentation",  re.compile(r'\b(docstring|comment|document|readme|explain\s+this|describe|what\s+does\s+this)\b', re.I)),
    ("code_generation",re.compile(r'\b(write|implement|create|generate|build|add\s+a\s+function|make\s+a|scaffold)\b', re.I)),
    ("question",       re.compile(r'\b(how\s+do|what\s+is|can\s+you|could\s+you|please\s+explain|help\s+me\s+understand)\b', re.I)),
]


def _classify_intent(prompt_text: str) -> str:
    for intent, pattern in _INTENT_PATTERNS:
        if pattern.search(prompt_text):
            return intent
    return "general"

_log = logging.getLogger(__name__)


async def _replay_as_sse(cached: dict):
    """Re-emit a cached non-streaming OpenAI response as SSE chunks.

    Clients that send stream=true receive text/event-stream even on a cache hit.
    Emits: role-delta → content/tool_calls delta → finish chunk → [DONE].
    Works for any model routed through /v1/chat/completions (Claude, GPT-4o,
    GitHub Copilot models, Azure AI Foundry models, etc.).
    """
    import json as _j
    import uuid as _uid

    rid = cached.get("id") or f"chatcmpl-{_uid.uuid4().hex[:8]}"
    model = cached.get("model", "")
    choices = cached.get("choices", [])

    def _chunk(delta: dict, index: int = 0, finish_reason=None) -> bytes:
        obj = {
            "id": rid,
            "object": "chat.completion.chunk",
            "model": model,
            "choices": [{"index": index, "delta": delta, "finish_reason": finish_reason}],
        }
        return f"data: {_j.dumps(obj)}\n\n".encode()

    # 1. Role delta — signals start of assistant turn
    yield _chunk({"role": "assistant", "content": ""})

    # 2. Content / tool_calls per choice
    for i, choice in enumerate(choices):
        msg = choice.get("message") or {}
        content = msg.get("content") or ""
        tool_calls = msg.get("tool_calls")
        if content:
            yield _chunk({"content": content}, index=i)
        if tool_calls:
            yield _chunk({"tool_calls": tool_calls}, index=i)

    # 3. Finish chunk (includes usage if present)
    finish_reason = (choices[0].get("finish_reason") if choices else None) or "stop"
    finish_obj = {
        "id": rid,
        "object": "chat.completion.chunk",
        "model": model,
        "choices": [{"index": 0, "delta": {}, "finish_reason": finish_reason}],
    }
    usage = cached.get("usage")
    if usage:
        finish_obj["usage"] = usage
    yield f"data: {_j.dumps(finish_obj)}\n\n".encode()

    # 4. SSE end sentinel
    yield b"data: [DONE]\n\n"

# ---------------------------------------------------------------------------
# Short-TTL identity cache — survives auth service restarts / rolling deploys.
# Entries expire after _IDENTITY_CACHE_TTL seconds; revoked keys are stale at
# most that long.  Not persisted: intentionally in-process and ephemeral.
# ---------------------------------------------------------------------------
_IDENTITY_CACHE_TTL = 45  # seconds


class _CachedIdentity(NamedTuple):
    team_id: str
    project_id: str | None
    key_id: str | None
    expires_at: float  # monotonic


_identity_cache: dict[str, _CachedIdentity] = {}

# Patterns that indicate unique/personal context — bypass semantic cache entirely.
_PII_PATTERNS = re.compile(
    r"[a-f0-9]{40}"          # git SHA
    r"|/home/\w+"             # home directory path
    r"|/Users/\w+"            # macOS home path
    r"|\bTraceback\b"         # Python stack trace
    r"|\bError:\s"            # error messages
    r"|\btransaction[_\s]id\b"
    r"|\bmy\s+(account|balance|order|sick\s+leave)\b",
    re.IGNORECASE,
)


def _prompt_text(body: dict) -> str:
    messages = body.get("messages", [])
    return " ".join(m.get("content", "") for m in messages if isinstance(m.get("content"), str))


def _turn_count(body: dict) -> int:
    """Count user turns in the conversation to detect multi-turn context drift."""
    return sum(1 for m in body.get("messages", []) if m.get("role") == "user")


def _has_pii(body: dict) -> bool:
    return bool(_PII_PATTERNS.search(_prompt_text(body)))


async def _emit_event(client: httpx.AsyncClient, event: dict) -> None:
    try:
        await client.post(
            f"{settings.observability_url}/events",
            json=event,
            headers={"x-internal-key": settings.internal_api_key},
            timeout=2,
        )
    except Exception:
        pass


async def _validate_token(
    client: httpx.AsyncClient, token: str, model: str | None
) -> tuple[str, str | None, str | None] | Response | None:
    """Validate token with auth service.

    Returns:
      (team_id, project_id, key_id) on success
      Response on 429 (budget/rate-limit) — forward to caller as-is
      None on auth failure (401, network error, etc.)

    On auth-service errors (network, 5xx), falls back to a 45-second in-process
    identity cache so agents survive rolling deploys and brief outages.
    """
    token_key = hashlib.sha256(token.encode()).hexdigest()

    try:
        resp = await client.post(
            f"{settings.auth_url}/validate",
            json={"token": token, "model": model or ""},
            timeout=5,
        )
        if resp.status_code == 200:
            data = resp.json()
            result = data["team_id"], data.get("project_id"), data.get("key_id")
            # Populate identity cache on every successful validation
            _identity_cache[token_key] = _CachedIdentity(
                team_id=result[0],
                project_id=result[1],
                key_id=result[2],
                expires_at=time.monotonic() + _IDENTITY_CACHE_TTL,
            )
            return result
        if resp.status_code == 429:
            return Response(content=resp.content, status_code=429, media_type="application/json")
        # Explicit 401/403 from auth service — key is invalid/revoked, evict cache
        _identity_cache.pop(token_key, None)
        return None
    except Exception as exc:
        # Auth service unreachable — serve from stale identity cache if available
        cached = _identity_cache.get(token_key)
        if cached and time.monotonic() < cached.expires_at:
            _log.warning("Auth service unreachable, using cached identity (team=%s): %s", cached.team_id, exc)
            return cached.team_id, cached.project_id, cached.key_id
        return None


_GUARDRAIL_CACHE_TTL = 60  # seconds between guardrail refreshes

async def _load_guardrails(redis, team_id: str) -> list[dict]:
    """Load enabled guardrails from Redis, keyed by admin service on create/update."""
    import json as _j
    results = []
    for key in (f"guardrails:{team_id}", "guardrails:global"):
        raw = await redis.get(key)
        if raw:
            try:
                results.extend(_j.loads(raw))
            except Exception:
                pass
    return results


async def _check_guardrails(
    redis,
    team_id: str,
    key_id: str | None,
    request_id: str,
    prompt_text: str,
    model: str | None,
    http,
) -> None:
    """Run enabled guardrails against the prompt text. Fires hits async; blocks on block action."""
    import re as _re, json as _j
    rules = await _load_guardrails(redis, team_id)
    for rule in rules:
        if not rule.get("enabled", True):
            continue
        applies_to = rule.get("applies_to", "input")
        if applies_to not in ("input", "both"):
            continue
        patterns = rule.get("config", {}).get("patterns", [])
        matched = False
        for pat in patterns:
            try:
                if _re.search(pat, prompt_text, _re.IGNORECASE):
                    matched = True
                    break
            except Exception:
                continue
        if not matched:
            continue
        action = rule.get("action", "flag")
        asyncio.create_task(_emit_guardrail_hit(http, {
            "guardrail_id": rule.get("id"),
            "guardrail_type": rule.get("type"),
            "team_id": team_id,
            "api_key_id": key_id,
            "request_id": request_id,
            "model": model,
            "input_or_output": "input",
            "action_taken": action,
            "severity": rule.get("severity", "high"),
        }))
        if action == "block":
            from fastapi.responses import JSONResponse as _JR
            raise _BlockedByGuardrail(rule.get("name", "guardrail"))


class _BlockedByGuardrail(Exception):
    def __init__(self, rule_name: str):
        self.rule_name = rule_name


async def _emit_guardrail_hit(http, hit: dict) -> None:
    try:
        await http.post(
            f"{settings.observability_url}/guardrail-hits",
            json=hit,
            headers={"x-internal-key": settings.internal_api_key},
            timeout=2,
        )
    except Exception:
        pass


async def _check_budget(redis, team_id: str, key_id: str | None, cap: float) -> bool:
    """Return True if request is allowed (under budget or cap disabled)."""
    if cap <= 0.0 or not settings.budget_check_enabled:
        return True
    try:
        counter_key = f"budget:{team_id}:{key_id or 'default'}"
        spent = float(await redis.get(counter_key) or 0.0)
        return spent < cap
    except Exception:
        return True  # fail open — never block agents due to Redis failure


@router.get("/v1/models")
async def list_models(request: Request):
    http = request.app.state.http
    auth_header = request.headers.get("Authorization", "")
    token = auth_header.removeprefix("Bearer ").strip()
    result = await _validate_token(http, token, None)
    if result is None:
        return JSONResponse({"error": "Unauthorized"}, status_code=401)
    if isinstance(result, Response):
        return result
    _team_id, _project_id, _key_id = result
    resp = await http.get(
        f"{settings.litellm_url}/v1/models",
        headers={"Authorization": f"Bearer {settings.litellm_master_key}"},
        timeout=10,
    )
    return Response(content=resp.content, status_code=resp.status_code, media_type="application/json")


@router.post("/v1/chat/completions")
async def chat_completions(request: Request):
    body = await request.json()
    redis = request.app.state.redis
    http = request.app.state.http

    auth_header = request.headers.get("Authorization", "")
    token = auth_header.removeprefix("Bearer ").strip()
    result = await _validate_token(http, token, body.get("model"))
    if result is None:
        return JSONResponse({"error": "Unauthorized"}, status_code=401)
    if isinstance(result, Response):
        return result
    team_id, project_id, key_id = result

    # Propagate or generate request-id for distributed tracing
    request_id = (
        request.headers.get("x-request-id")
        or request.headers.get("x-correlation-id")
        or str(__import__("uuid").uuid4())
    )

    # Claude Code / agentic context headers
    session_trace_id = request.headers.get("x-session-trace-id")
    session_purpose = request.headers.get("x-session-purpose")
    repo = request.headers.get("x-repo")

    # Classify request intent from prompt text (no prompt stored)
    request_intent = _classify_intent(_prompt_text(body))

    try:
        policy = await get_policy(team_id, project_id, redis)
    except Exception:
        policy = CachePolicy(
            ttl_seconds=settings.default_ttl_seconds,
            similarity_threshold=settings.default_similarity_threshold,
            opt_out=False,
            embedding_model=settings.embedding_model,
        )

    # Allowed models gate — empty list means all models permitted
    requested_model = body.get("model", "")
    if policy.allowed_models and requested_model and requested_model not in policy.allowed_models:
        return JSONResponse(
            {"error": "model_not_permitted",
             "message": f"Model '{requested_model}' is not in your team's allowed model list"},
            status_code=403,
            headers={"x-request-id": request_id},
        )

    # Guardrails — run lightweight enforcement on input before forwarding
    try:
        await _check_guardrails(redis, team_id, key_id, request_id, _prompt_text(body), body.get("model"), http)
    except _BlockedByGuardrail as exc:
        return JSONResponse(
            {"error": "blocked_by_guardrail", "message": f"Request blocked by guardrail: {exc.rule_name}"},
            status_code=400,
            headers={"x-request-id": request_id},
        )

    # Hard budget gate — fail open (allow) if Redis is unavailable
    if not await _check_budget(redis, team_id, key_id, policy.budget_hard_cap):
        return JSONResponse({"error": "Budget cap exceeded"}, status_code=429, headers={"x-request-id": request_id})

    start = time.monotonic()

    # Determine whether to bypass the cache:
    # - policy opt_out
    # - conversation has too many turns (context drift)
    # - prompt contains personal identifiers / unique content
    turns = _turn_count(body)
    bypass_cache = (
        policy.opt_out
        or turns > policy.conversation_turn_limit
        or _has_pii(body)
    )

    emb: list[float] | None = None
    similarity_score: float | None = None
    cache_stage = "bypass" if bypass_cache else "miss"

    cache_namespace = f"{team_id}:{project_id or ''}"

    if not bypass_cache:
        # 1. Exact match
        try:
            cached = await exact.get(body, redis, team_id=team_id, project_id=project_id or "")
            if cached:
                cache_stage = "exact_hit"
                asyncio.create_task(
                    _emit_event(http, {
                        "team_id": team_id, "project_id": project_id, "key_id": key_id,
                        "model": body.get("model"), "cache_hit": True, "cache_stage": cache_stage,
                        "latency_ms": int((time.monotonic() - start) * 1000),
                        "cache_namespace": cache_namespace,
                        "session_trace_id": session_trace_id,
                        "session_purpose": session_purpose, "repo": repo,
                    })
                )
                _hit_headers = {"X-Cache": "HIT", "X-Cache-Stage": "exact", "x-request-id": request_id}
                if body.get("stream"):
                    return StreamingResponse(
                        _replay_as_sse(cached),
                        media_type="text/event-stream",
                        headers=_hit_headers,
                    )
                return JSONResponse(cached, headers=_hit_headers)
        except Exception:
            pass  # Redis failure → fail open

        # 2. Semantic match
        emb_start = time.monotonic()
        try:
            emb = await semantic.embed(_prompt_text(body), policy.embedding_model)
            cached = await semantic.get(emb, policy.similarity_threshold, redis, team_id=team_id, project_id=project_id or "")
            if cached:
                cache_stage = "semantic_hit"
                asyncio.create_task(
                    _emit_event(http, {
                        "team_id": team_id, "project_id": project_id, "key_id": key_id,
                        "model": body.get("model"), "cache_hit": True, "cache_stage": cache_stage,
                        "embedding_latency_ms": int((time.monotonic() - emb_start) * 1000),
                        "latency_ms": int((time.monotonic() - start) * 1000),
                        "cache_namespace": cache_namespace,
                        "session_trace_id": session_trace_id,
                        "session_purpose": session_purpose, "repo": repo,
                    })
                )
                _hit_headers = {"X-Cache": "HIT", "X-Cache-Stage": "semantic", "x-request-id": request_id}
                if body.get("stream"):
                    return StreamingResponse(
                        _replay_as_sse(cached),
                        media_type="text/event-stream",
                        headers=_hit_headers,
                    )
                return JSONResponse(cached, headers=_hit_headers)
        except Exception:
            semantic.record_embedding_failure(redis)
            emb = None  # embedding failure → treat as miss

    # 3. Forward to LiteLLM
    fwd_headers = {
        k: v for k, v in request.headers.items()
        if k.lower() not in ("host", "content-length", "authorization")
    }
    fwd_headers["Authorization"] = f"Bearer {settings.litellm_master_key}"
    fwd_headers["x-request-id"] = request_id

    # Inject Anthropic prefix-cache header so provider-side caching compounds with ours.
    # This is a no-op for non-Anthropic providers.
    fwd_headers.setdefault("anthropic-beta", "prompt-caching-2024-07-31")

    is_stream = body.get("stream", False)

    if is_stream:
        # Inject include_usage so LiteLLM/OpenAI appends a usage chunk at stream end
        stream_body = {**body, "stream_options": {**body.get("stream_options", {}), "include_usage": True}}
        req = http.build_request(
            "POST", f"{settings.litellm_url}/v1/chat/completions", json=stream_body, headers=fwd_headers,
        )
        upstream = await http.send(req, stream=True)
        latency_ms = int((time.monotonic() - start) * 1000)
        err = None if upstream.status_code == 200 else str(upstream.status_code)

        base_event = {
            "team_id": team_id, "project_id": project_id, "key_id": key_id,
            "model": body.get("model"), "cache_hit": False, "cache_stage": "stream",
            "latency_ms": latency_ms, "error": err,
            "cache_namespace": cache_namespace, "session_trace_id": session_trace_id,
            "session_purpose": session_purpose, "repo": repo, "request_intent": request_intent,
        }

        async def _emit_after_stream(tokens_in: int, tokens_out: int) -> None:
            await _emit_event(http, {**base_event, "tokens_input": tokens_in, "tokens_output": tokens_out})

        return StreamingResponse(
            _tracked_stream(upstream, _emit_after_stream, _parse_sse_usage_openai),
            status_code=upstream.status_code,
            media_type=upstream.headers.get("content-type", "text/event-stream"),
            headers={"X-Cache": "MISS", "x-request-id": request_id},
        )

    try:
        resp = await http.post(
            f"{settings.litellm_url}/v1/chat/completions", json=body, headers=fwd_headers, timeout=600
        )
    except httpx.RequestError as exc:
        _log.warning("LiteLLM unreachable: %s", exc)
        return JSONResponse(
            {"error": "upstream_unavailable", "message": "LLM provider temporarily unavailable"},
            status_code=503,
            headers={"Retry-After": "30", "x-request-id": request_id},
        )
    response_body = resp.json()

    if resp.status_code == 200 and not bypass_cache:
        try:
            await exact.set(body, response_body, policy.ttl_seconds, redis, team_id=team_id, project_id=project_id or "")
        except Exception:
            pass
        if emb is not None:
            try:
                await semantic.set(emb, response_body, policy.ttl_seconds, redis, team_id=team_id, project_id=project_id or "")
            except Exception:
                pass

    usage = response_body.get("usage", {})
    asyncio.create_task(
        _emit_event(http, {
            "team_id": team_id, "project_id": project_id, "key_id": key_id,
            "model": body.get("model"),
            "tokens_input": usage.get("prompt_tokens", 0),
            "tokens_output": usage.get("completion_tokens", 0),
            "cache_hit": False, "cache_stage": cache_stage,
            "latency_ms": int((time.monotonic() - start) * 1000),
            "error": None if resp.status_code == 200 else str(resp.status_code),
            "cache_namespace": cache_namespace,
            "session_trace_id": session_trace_id,
            "session_purpose": session_purpose, "repo": repo,
            "request_intent": request_intent,
        })
    )
    return Response(
        content=resp.content, status_code=resp.status_code, media_type="application/json",
        headers={"X-Cache": "MISS", "x-request-id": request_id},
    )


@router.post("/anthropic/{path:path}")
async def anthropic_proxy(path: str, request: Request):
    """Anthropic-compatible passthrough — validates gateway key then forwards to LiteLLM."""
    http = request.app.state.http

    token = (
        request.headers.get("x-api-key", "")
        or request.headers.get("Authorization", "").removeprefix("Bearer ").strip()
    )
    body_bytes = await request.body()
    body = {}
    try:
        import json
        body = json.loads(body_bytes) if body_bytes else {}
    except Exception:
        pass

    result = await _validate_token(http, token, body.get("model"))
    if result is None:
        return JSONResponse({"error": {"type": "authentication_error", "message": "Invalid API key"}}, status_code=401)
    if isinstance(result, Response):
        return result
    team_id, project_id, key_id = result

    fwd_headers = {
        k: v for k, v in request.headers.items()
        if k.lower() not in ("host", "content-length", "authorization", "x-api-key")
    }
    fwd_headers["x-api-key"] = settings.litellm_master_key
    # Ensure Anthropic prefix caching is active for all forwarded Anthropic requests.
    fwd_headers.setdefault("anthropic-beta", "prompt-caching-2024-07-31")

    is_stream = body.get("stream", False)
    target = f"{settings.litellm_url}/anthropic/{path}"

    start = time.monotonic()
    anthropic_intent = _classify_intent(_prompt_text(body))
    if is_stream:
        try:
            req = http.build_request("POST", target, content=body_bytes, headers=fwd_headers)
            upstream = await http.send(req, stream=True)
        except httpx.RequestError as exc:
            _log.warning("LiteLLM unreachable on Anthropic path: %s", exc)
            return JSONResponse(
                {"error": {"type": "overloaded_error", "message": "LLM provider temporarily unavailable"}},
                status_code=503,
                headers={"Retry-After": "30"},
            )
        latency_ms = int((time.monotonic() - start) * 1000)
        anthropic_base_event = {
            "team_id": team_id, "project_id": project_id, "key_id": key_id,
            "model": body.get("model"), "cache_hit": False, "cache_stage": "stream",
            "latency_ms": latency_ms, "request_intent": anthropic_intent,
        }

        async def _emit_anthropic(tokens_in: int, tokens_out: int) -> None:
            await _emit_event(http, {**anthropic_base_event, "tokens_input": tokens_in, "tokens_output": tokens_out})

        return StreamingResponse(
            _tracked_stream(upstream, _emit_anthropic, _parse_sse_usage_anthropic),
            status_code=upstream.status_code,
            media_type=upstream.headers.get("content-type", "text/event-stream"),
            headers={"X-Cache": "MISS"},
        )

    try:
        resp = await http.post(target, content=body_bytes, headers=fwd_headers, timeout=600)
    except httpx.RequestError as exc:
        _log.warning("LiteLLM unreachable on Anthropic path: %s", exc)
        return JSONResponse(
            {"error": {"type": "overloaded_error", "message": "LLM provider temporarily unavailable"}},
            status_code=503,
            headers={"Retry-After": "30"},
        )
    asyncio.create_task(_emit_event(http, {
        "team_id": team_id, "project_id": project_id, "key_id": key_id,
        "model": body.get("model"), "cache_hit": False, "cache_stage": "miss",
        "latency_ms": int((time.monotonic() - start) * 1000),
    }))
    return Response(
        content=resp.content, status_code=resp.status_code,
        media_type=resp.headers.get("content-type", "application/json"),
        headers={"X-Cache": "MISS"},
    )
