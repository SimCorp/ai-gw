import json

import httpx
from fastapi import HTTPException

from app.config import settings

_SYSTEM = (
    "You classify AI-related content submitted by SimCorp engineers. "
    "Return a JSON object with keys: title, summary (<=200 chars), "
    "focus_areas (list of slugs like 'agentic', 'rag', 'evals', 'prompt-engineering', 'mcp', 'workflows'), "
    "tags (list of free-form slugs), difficulty ('beginner'|'intermediate'|'advanced'|'unknown'). "
    "Return ONLY the JSON object, no prose."
)

_FALLBACK = {"title": "(untitled)", "summary": "", "focus_areas": [], "tags": [], "difficulty": "unknown"}


async def classify_content(*, text: str) -> dict:
    """Single litellm call → structured metadata dict. Never raises on parse error,
    but raises HTTPException(502) when litellm itself is unavailable."""
    payload = {
        "model": "claude-haiku-4-5-20251001",
        "messages": [
            {"role": "system", "content": _SYSTEM},
            {"role": "user", "content": text[:8000]},
        ],
        "max_tokens": 400,
        "temperature": 0.2,
    }
    async with httpx.AsyncClient(timeout=20.0) as client:
        resp = await client.post(
            f"{settings.litellm_url}/v1/chat/completions",
            json=payload,
            headers={"Authorization": f"Bearer {settings.litellm_master_key}"},
        )
    if resp.status_code != 200:
        raise HTTPException(status_code=502, detail="metadata backend unavailable")
    content = resp.json()["choices"][0]["message"]["content"]
    try:
        parsed = json.loads(content)
    except json.JSONDecodeError:
        return dict(_FALLBACK)

    return {
        "title": str(parsed.get("title") or "(untitled)"),
        "summary": str(parsed.get("summary") or "")[:200],
        "focus_areas": [str(x) for x in (parsed.get("focus_areas") or [])][:8],
        "tags": [str(x) for x in (parsed.get("tags") or [])][:12],
        "difficulty": parsed.get("difficulty") if parsed.get("difficulty") in {"beginner", "intermediate", "advanced"} else "unknown",
    }
