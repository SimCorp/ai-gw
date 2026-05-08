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
        "extra_env_vars": [],
    },
    {
        "name": "GitHub Copilot",
        "icon": "⚫",
        "env_var": "GITHUB_COPILOT_TOKEN",
        "models": ["copilot-gpt-4o", "copilot-gpt-4o-mini", "copilot-o3-mini", "copilot-claude-3.5-sonnet"],
        "litellm_model_names": ["copilot-gpt-4o", "copilot-gpt-4o-mini", "copilot-o3-mini", "copilot-claude-3.5-sonnet"],
        "test_model": "copilot-gpt-4o",
        "description": "GitHub Copilot API — requires a GitHub PAT with Copilot access (ghp_... token with copilot:read scope)",
        "docs_url": "https://docs.github.com/en/copilot/using-github-copilot/using-github-copilot-chat-in-your-ide",
        "extra_env_vars": [],
    },
    {
        "name": "Azure AI Foundry",
        "icon": "☁️",
        "env_var": "AZURE_API_KEY",
        "models": ["azure-gpt-4o", "azure-gpt-4o-mini", "azure-o3-mini", "azure-gpt-4.1"],
        "litellm_model_names": ["azure-gpt-4o", "azure-gpt-4o-mini", "azure-o3-mini", "azure-gpt-4.1"],
        "test_model": "azure-gpt-4o",
        "description": "Azure AI Foundry (Azure OpenAI) — requires API key, endpoint URL, and API version",
        "docs_url": "https://learn.microsoft.com/en-us/azure/ai-services/openai/",
        "extra_env_vars": [
            {"env_var": "AZURE_API_BASE", "label": "Endpoint URL", "placeholder": "https://YOUR-RESOURCE.openai.azure.com/"},
            {"env_var": "AZURE_API_VERSION", "label": "API Version", "placeholder": "2024-12-01-preview"},
        ],
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
    """Patch the api_key (and any extra params) on every LiteLLM model that reads from this env var."""
    provider = next((p for p in PROVIDERS if p["env_var"] == env_var), None)
    if not provider:
        return False
    target_models = provider.get("litellm_model_names", [])
    if not target_models:
        return False

    # Build extra litellm_params from stored/env extra_env_vars (e.g. Azure api_base, api_version)
    extra_params: dict[str, str] = {}
    for extra in provider.get("extra_env_vars", []):
        val = os.environ.get(extra["env_var"], "")
        if val:
            # Map env var names to LiteLLM param names
            param_name = extra["env_var"].lower().replace("azure_", "").replace("_", "_")
            extra_params[param_name] = val

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
                litellm_params: dict[str, str] = {"api_key": key_value}
                litellm_params.update(extra_params)
                patch = await client.patch(
                    f"{settings.litellm_url}/model/update",
                    headers={"Authorization": f"Bearer {settings.litellm_master_key}"},
                    json={"model_id": model_id, "litellm_params": litellm_params},
                )
                results.append(patch.status_code in (200, 201))
            return all(results) if results else False
    except Exception:
        return False


def _build_provider_list(stored: dict[str, str]) -> list[dict]:
    result = []
    for p in PROVIDERS:
        env_var = p["env_var"]
        extra = p.get("extra_env_vars", [])
        # For providers with extra required env vars (e.g. Azure), all must be set
        all_vars = [env_var] + [e["env_var"] for e in extra]
        is_set = all(bool(stored.get(v) or os.environ.get(v)) for v in all_vars)
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

        # Persist and apply any extra env vars for this provider (e.g. AZURE_API_BASE)
        for extra in p.get("extra_env_vars", []):
            extra_var = extra["env_var"]
            extra_val = (body.get(extra_var) or "").strip()
            if extra_val:
                await session.execute(
                    text("""
                        INSERT INTO provider_keys (env_var, key_value, updated_at)
                        VALUES (:env_var, :val, NOW())
                        ON CONFLICT (env_var) DO UPDATE SET key_value = :val, updated_at = NOW()
                    """),
                    {"env_var": extra_var, "val": extra_val},
                )
                os.environ[extra_var] = extra_val

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


async def _fetch_provider_models(provider: dict, key: str, stored: dict[str, str]) -> list[dict]:
    """Call the provider's model list API and return [{id, name}]."""
    env_var = provider["env_var"]
    name = provider["name"]
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            if "Anthropic" in name:
                r = await client.get(
                    "https://api.anthropic.com/v1/models",
                    headers={"x-api-key": key, "anthropic-version": "2023-06-01"},
                    params={"limit": 100},
                )
                r.raise_for_status()
                return [{"id": m["id"], "name": m.get("display_name", m["id"])} for m in r.json().get("data", [])]

            elif "OpenAI" in name:
                r = await client.get(
                    "https://api.openai.com/v1/models",
                    headers={"Authorization": f"Bearer {key}"},
                )
                r.raise_for_status()
                raw = [m for m in r.json().get("data", []) if "gpt" in m["id"] or m["id"].startswith("o")]
                return [{"id": m["id"], "name": m["id"]} for m in sorted(raw, key=lambda x: x["id"])]

            elif "GitHub Copilot" in name:
                r = await client.get(
                    "https://api.githubcopilot.com/models",
                    headers={"Authorization": f"Bearer {key}"},
                )
                r.raise_for_status()
                return [{"id": m["id"], "name": m.get("name", m["id"])} for m in r.json().get("data", r.json() if isinstance(r.json(), list) else [])]

            elif "GitHub Models" in name:
                r = await client.get(
                    "https://models.inference.ai.azure.com/v1/models",
                    headers={"Authorization": f"Bearer {key}"},
                )
                r.raise_for_status()
                return [{"id": m["id"], "name": m.get("name", m["id"])} for m in r.json().get("data", [])]

            elif "Google" in name:
                r = await client.get(
                    "https://generativelanguage.googleapis.com/v1beta/models",
                    params={"key": key, "pageSize": 50},
                )
                r.raise_for_status()
                return [
                    {"id": m["name"].split("/")[-1], "name": m.get("displayName", m["name"].split("/")[-1])}
                    for m in r.json().get("models", [])
                    if "generateContent" in m.get("supportedGenerationMethods", [])
                ]

            elif "Azure" in name:
                api_base = stored.get("AZURE_API_BASE") or os.environ.get("AZURE_API_BASE", "")
                api_version = stored.get("AZURE_API_VERSION") or os.environ.get("AZURE_API_VERSION", "2024-12-01-preview")
                if not api_base:
                    return []
                base = api_base.rstrip("/")
                r = await client.get(
                    f"{base}/openai/models",
                    headers={"api-key": key},
                    params={"api-version": api_version},
                )
                r.raise_for_status()
                return [{"id": m["id"], "name": m.get("model", m["id"])} for m in r.json().get("data", [])]

    except Exception:
        pass
    return []


@router.post("/api/settings/providers/{env_var}/discover")
async def discover_provider_models(env_var: str, session: AsyncSession = Depends(get_session)):
    """Fetch available models from a provider using its stored API key.
    Returns each model with whether it is already registered in model_registry."""
    provider = next((p for p in PROVIDERS if p["env_var"] == env_var), None)
    if not provider:
        return {"ok": False, "error": "Unknown provider", "models": []}

    stored = await _get_stored_keys(session)
    key = stored.get(env_var) or os.environ.get(env_var)
    if not key:
        return {"ok": False, "error": "No API key configured", "models": []}

    discovered = await _fetch_provider_models(provider, key, stored)
    if not discovered:
        return {"ok": False, "error": "No models returned — check key and try again", "models": []}

    # Check which are already registered
    registered_ids = {
        r[0] for r in (await session.execute(text("SELECT model_id FROM model_registry"))).all()
    }

    return {
        "ok": True,
        "models": [
            {
                "id": m["id"],
                "name": m["name"],
                "registered": m["id"] in registered_ids,
            }
            for m in discovered
        ],
    }
