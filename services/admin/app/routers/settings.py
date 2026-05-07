"""Provider API key management — store keys in DB, push to LiteLLM at runtime."""
import os
from typing import Any

import httpx
from fastapi import APIRouter, Depends, Request
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db import get_session

router = APIRouter(tags=["settings"])
# Provider definitions — env_var is what LiteLLM reads
PROVIDERS = [
    {
        "name": "Anthropic (Claude)",
        "icon": "🟣",
        "env_var": "ANTHROPIC_API_KEY",
        "models": ["claude-sonnet-4-6", "claude-opus-4-7", "claude-haiku-4-5"],
        "litellm_model_names": ["claude-sonnet-4-6", "claude-opus-4-7", "claude-haiku-4-5"],
        "test_model": "claude-haiku-4-5",
    },
    {
        "name": "OpenAI",
        "icon": "🟢",
        "env_var": "OPENAI_API_KEY",
        "models": ["gpt-4o", "gpt-4o-mini"],
        "litellm_model_names": ["gpt-4o"],
        "test_model": "gpt-4o",
    },
    {
        "name": "Google (Gemini)",
        "icon": "🔵",
        "env_var": "GEMINI_API_KEY",
        "models": ["gemini-1.5-pro", "gemini-1.5-flash"],
        "litellm_model_names": ["gemini-1.5-pro"],
        "test_model": "gemini-1.5-pro",
    },
    {
        "name": "GitHub Models (GPT-4o)",
        "icon": "⚫",
        "env_var": "GITHUB_MODELS_API_KEY",
        "models": ["github-gpt-4o"],
        "litellm_model_names": ["github-gpt-4o"],
        "test_model": "github-gpt-4o",
    },
]

_ENSURE_TABLE = text("""
    CREATE TABLE IF NOT EXISTS provider_keys (
        env_var TEXT PRIMARY KEY,
        key_value TEXT NOT NULL,
        updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
    )
""")


async def _ensure_table(session: AsyncSession) -> None:
    await session.execute(_ENSURE_TABLE)
    await session.commit()


async def _get_stored_keys(session: AsyncSession) -> dict[str, str]:
    await _ensure_table(session)
    rows = (await session.execute(text("SELECT env_var, key_value FROM provider_keys"))).all()
    return {r[0]: r[1] for r in rows}


async def _push_to_litellm(env_var: str, key_value: str) -> bool:
    """Patch the api_key on every LiteLLM model that reads from this env var."""
    provider = next((p for p in PROVIDERS if p["env_var"] == env_var), None)
    if not provider:
        return False
    target_models = provider.get("litellm_model_names", [])
    if not target_models:
        return False
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            # Fetch current model list to get internal model IDs
            info_resp = await client.get(
                f"{settings.litellm_url}/model/info",
                headers={"Authorization": f"Bearer {settings.litellm_master_key}"},
            )
            if info_resp.status_code != 200:
                return False
            models = info_resp.json().get("data", [])
            results = []
            for m in models:
                if m.get("model_name") not in target_models:
                    continue
                model_id = m.get("model_info", {}).get("id")
                if not model_id:
                    continue
                patch = await client.patch(
                    f"{settings.litellm_url}/model/update",
                    headers={"Authorization": f"Bearer {settings.litellm_master_key}"},
                    json={"model_id": model_id, "litellm_params": {"api_key": key_value}},
                )
                results.append(patch.status_code in (200, 201))
            return all(results) if results else False
    except Exception:
        return False


def _build_provider_list(stored: dict[str, str]) -> list[dict]:
    result = []
    for p in PROVIDERS:
        env_var = p["env_var"]
        is_set = bool(stored.get(env_var) or os.environ.get(env_var))
        result.append({**p, "is_set": is_set})
    return result


def _build_model_status(stored: dict[str, str]) -> list[dict]:
    rows = []
    for p in PROVIDERS:
        env_var = p["env_var"]
        key_set = bool(stored.get(env_var) or os.environ.get(env_var))
        for model in p.get("models", []):
            rows.append({"name": model, "provider": p["name"], "key_set": key_set})
    return rows


@router.get("/api/settings/providers")
async def list_providers(session: AsyncSession = Depends(get_session)):
    """Return configured providers and which keys are set (values masked)."""
    stored = await _get_stored_keys(session)
    return {"providers": _build_provider_list(stored)}


@router.post("/api/settings/providers")
async def save_provider_keys(
    request: Request,
    session: AsyncSession = Depends(get_session),
):
    """Upsert provider API keys. Accepts JSON: {env_var: key_value, ...}"""
    body = await request.json()
    await _ensure_table(session)

    push_results = []
    for p in PROVIDERS:
        env_var = p["env_var"]
        raw = (body.get(env_var) or "").strip()
        if not raw:
            continue

        await session.execute(
            text("""
                INSERT INTO provider_keys (env_var, key_value, updated_at)
                VALUES (:env_var, :val, NOW())
                ON CONFLICT (env_var) DO UPDATE SET key_value = :val, updated_at = NOW()
            """),
            {"env_var": env_var, "val": raw},
        )
        os.environ[env_var] = raw
        ok = await _push_to_litellm(env_var, raw)
        push_results.append(ok)

    await session.commit()
    return {"saved": True, "pushed": all(push_results) if push_results else False}


@router.post("/ui/settings/test/{env_var}")
async def test_provider(env_var: str, session: AsyncSession = Depends(get_session)):
    """Fire a minimal 1-token completion through LiteLLM and return pass/fail + latency."""
    import time

    provider = next((p for p in PROVIDERS if p["env_var"] == env_var), None)
    if not provider:
        return {"ok": False, "error": "Unknown provider"}

    stored = await _get_stored_keys(session)
    key = stored.get(env_var) or os.environ.get(env_var)
    if not key:
        return {"ok": False, "error": "No API key configured — save a key first"}

    model = provider.get("test_model", provider["litellm_model_names"][0])
    t0 = time.monotonic()
    try:
        async with httpx.AsyncClient(timeout=20) as client:
            resp = await client.post(
                f"{settings.litellm_url}/v1/chat/completions",
                headers={"Authorization": f"Bearer {settings.litellm_master_key}"},
                json={
                    "model": model,
                    "messages": [{"role": "user", "content": "Reply with the single word: ok"}],
                    "max_tokens": 5,
                    "api_key": key,  # pass stored key directly; overrides whatever LiteLLM has
                },
            )
        latency_ms = int((time.monotonic() - t0) * 1000)
        if resp.status_code == 200:
            reply = resp.json().get("choices", [{}])[0].get("message", {}).get("content", "").strip()
            return {"ok": True, "latency_ms": latency_ms, "reply": reply, "model": model}
        else:
            detail = resp.json().get("error", {}).get("message", resp.text[:200])
            return {"ok": False, "error": detail, "latency_ms": latency_ms}
    except httpx.TimeoutException:
        return {"ok": False, "error": "Request timed out after 20s"}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}
