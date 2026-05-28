"""Retrieval helper for AiHelpWidget — pulls champion-tagged chunks from the librarian."""

from __future__ import annotations

import logging

import httpx

from app.config import settings

_log = logging.getLogger(__name__)


async def retrieve_champion_chunks(query: str, limit: int = 5) -> list[dict]:
    """Return list of `{id, title, content, source_url, score, ...}` from librarian topic=champions.

    Returns an empty list on any failure (network error, non-200, parse error, empty query).
    """
    if not query or not query.strip():
        return []
    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            resp = await client.get(
                f"{settings.librarian_url}/search",
                params={"q": query, "topic": "champions", "limit": limit},
            )
        if resp.status_code != 200:
            return []
        data = resp.json()
        # Librarian returns {results: [...], count: N} — fall back to items for safety.
        return data.get("results") or data.get("items") or []
    except Exception:
        _log.exception("retrieve_champion_chunks failed")
        return []
