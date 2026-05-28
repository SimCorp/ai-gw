"""AI help chat endpoint — serves the in-portal assistant for both admin and developer users."""

from typing import Literal

import httpx
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.auth import require_admin_auth
from app.config import settings
from app.llm.champion_rag import retrieve_champion_chunks
from app.routers.dev_auth import _get_current_developer

# Minimum cosine similarity from librarian to consider a chunk "confidently relevant"
_CHAMPION_RAG_THRESHOLD = 0.55
_CHAMPION_SNIPPET_MAX_CHARS = 600

router = APIRouter(prefix="/ai-help", tags=["ai-help"])

_SYSTEM_ADMIN = """You are an expert assistant embedded in the AI Gateway admin portal.
You help platform administrators with:
- Managing teams, areas, users, and API keys
- Configuring model registry, guardrails, and policies
- Understanding cost reports, budget alerts, and spend by team
- Auditing MCP servers, plugins, and skill catalogs
- Troubleshooting common issues (rate limiting, model errors, webhook delivery)
- Reviewing audit logs and approval workflows

Answer concisely and accurately. When mentioning specific pages, refer to them by their sidebar label (e.g. "Quotas & budgets", "Audit log"). When answering about API endpoints, use the format GET /admin/... or POST /admin/...

You have no access to live data — answer based on the gateway's design and configuration patterns."""

_SYSTEM_PORTAL = """You are an expert assistant embedded in the AI Gateway developer portal.
You help engineers at SimCorp with:
- Getting started: creating API keys, choosing a model, sending first requests
- Using the OpenAI-compatible API (base URL: http://gateway/v1, same SDK as OpenAI)
- Streaming, tool use, and cache behaviour (x-cache: bypass header)
- Understanding usage and cost on the Usage & spend page
- Managing MCP servers, skills, agents, and plugins in the catalog
- Common errors: 401 (bad key), 429 (rate limit), 502/503 (upstream provider down)
- Recommended models: claude-sonnet-4-6 for most work, claude-haiku-4-5-20251001 for low-cost tasks, claude-opus-4-7 for complex reasoning

Code examples use the openai Python SDK or fetch with Authorization: Bearer <your-key>.
Answer concisely. Point to specific portal pages when relevant (Playground, API keys, Usage & spend, Docs)."""


class Message(BaseModel):
    role: Literal["user", "assistant", "system"]
    content: str = Field(..., max_length=8000)


class ChatRequest(BaseModel):
    messages: list[Message] = Field(..., max_length=40)
    context: Literal["admin", "portal"] = "portal"


async def _call_llm(messages: list[dict]) -> str:
    url = f"{settings.litellm_url}/v1/chat/completions"
    payload = {
        "model": "claude-haiku-4-5-20251001",
        "messages": messages,
        "max_tokens": 512,
        "temperature": 0.3,
    }
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.post(
            url,
            json=payload,
            headers={"Authorization": f"Bearer {settings.litellm_master_key}"},
        )
    if resp.status_code != 200:
        raise HTTPException(status_code=502, detail="AI backend unavailable")
    data = resp.json()
    return data["choices"][0]["message"]["content"]


@router.post("/chat")
async def ai_help_chat_admin(
    body: ChatRequest,
    _auth: dict = Depends(require_admin_auth),
):
    """AI help endpoint for admin portal users."""
    system = _SYSTEM_ADMIN if body.context == "admin" else _SYSTEM_PORTAL
    messages = [{"role": "system", "content": system}] + [
        {"role": m.role, "content": m.content} for m in body.messages
    ]
    reply = await _call_llm(messages)
    return {"reply": reply}


def _build_champion_context(chunks: list[dict]) -> tuple[str, list[dict]]:
    """Format retrieved champion chunks into a system-prompt snippet and a cited_sources list."""
    lines: list[str] = []
    cited: list[dict] = []
    for ch in chunks:
        title = ch.get("title") or "Untitled"
        content = ch.get("content") or ""
        snippet = content[:_CHAMPION_SNIPPET_MAX_CHARS].strip()
        source_url = ch.get("source_url")
        suffix = f" [source: {source_url}]" if source_url else ""
        lines.append(f"- {title} — {snippet}{suffix}")
        cited.append(
            {
                "contribution_id": ch.get("id"),
                "title": title,
                "source_url": source_url,
            }
        )
    block = "\n\nRelevant champion content (cite these when relevant):\n" + "\n".join(lines)
    return block, cited


@router.post("/chat/portal")
async def ai_help_chat_portal(
    body: ChatRequest,
    developer: dict = Depends(_get_current_developer),
):
    """AI help endpoint for developer portal users (dev session auth).

    RAG-augmented: retrieves champion-tagged chunks from the librarian, grounds the
    LLM response in them, and falls back to an `ask_cta` payload when no relevant
    content is available.
    """
    # Find the last user message for retrieval
    last_user_msg = ""
    for m in reversed(body.messages):
        if m.role == "user":
            last_user_msg = m.content
            break

    chunks = await retrieve_champion_chunks(last_user_msg, limit=5)

    # Filter to chunks above the similarity threshold. If chunks lack a score
    # (e.g. embedding pipeline failure), fall back to top-3 unconditionally.
    has_scores = any("score" in c for c in chunks)
    if has_scores:
        relevant = [c for c in chunks if (c.get("score") or 0.0) >= _CHAMPION_RAG_THRESHOLD]
    else:
        relevant = chunks[:3]

    # No-confidence fallback → structured ask_cta payload, no LLM call.
    if not relevant:
        title_guess = last_user_msg.strip().splitlines()[0][:80] if last_user_msg else ""
        return {
            "type": "ask_cta",
            "reply": "I don't have a great answer for that yet. Want to ask a champion?",
            "content": "I don't have a great answer for that yet. Want to ask a champion?",
            "message": "I don't have a great answer for that yet. Want to ask a champion?",
            "prefill": {
                "title": title_guess,
                "description": last_user_msg,
            },
            "cited_sources": [],
        }

    context_block, cited_sources = _build_champion_context(relevant)
    system_prompt = _SYSTEM_PORTAL + context_block

    messages = [{"role": "system", "content": system_prompt}] + [
        {"role": m.role, "content": m.content} for m in body.messages
    ]
    reply = await _call_llm(messages)
    return {
        "type": "text",
        "reply": reply,
        "content": reply,
        "cited_sources": cited_sources,
    }
