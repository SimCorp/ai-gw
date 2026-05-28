"""Lightweight regex/heuristic intent classifier for champion-related user messages.

Used upstream of the RAG step in the AiHelpWidget portal endpoint to detect
structured intents (browse champions, find content, book session) so we can
return card-style payloads instead of free-text LLM answers.
"""

from __future__ import annotations

import re
from typing import Literal, TypedDict


class IntentResult(TypedDict, total=False):
    intent: Literal["show_champions", "find_content", "book_champion", "none"]
    query: str  # extracted topic / target
    raw: str


_SHOW_CHAMPIONS_PATTERNS = [
    r"\bchampion(?:s)? (?:for|on|about) (.+)$",
    r"\b(?:show|list|who are|tell me about) (?:me )?(?:the )?champions?\b",
    r"\bfind a champion\b",
]

_FIND_CONTENT_PATTERNS = [
    r"\bfind (?:content|articles?|posts?|videos?) (?:on|about) (.+)$",
    r"\bshow me (?:content|articles?) (?:on|about) (.+)$",
    r"\bwhat do (?:we|you) have (?:on|about) (.+)$",
]

_BOOK_PATTERNS = [
    r"\bbook (?:a session with )?(.+)$",
    r"\boffice hours? with (.+)$",
]


def classify(text: str) -> IntentResult:
    """Return the most specific intent that matches, or {'intent': 'none'}."""
    if not text:
        return {"intent": "none", "raw": text or ""}
    t = text.strip().lower()
    for pat in _BOOK_PATTERNS:
        m = re.search(pat, t)
        if m:
            return {"intent": "book_champion", "query": m.group(1).strip(" ?.!"), "raw": text}
    for pat in _FIND_CONTENT_PATTERNS:
        m = re.search(pat, t)
        if m:
            return {"intent": "find_content", "query": m.group(1).strip(" ?.!"), "raw": text}
    for pat in _SHOW_CHAMPIONS_PATTERNS:
        m = re.search(pat, t)
        if m:
            query = ""
            if m.lastindex:
                try:
                    query = (m.group(1) or "").strip(" ?.!")
                except IndexError:
                    query = ""
            return {"intent": "show_champions", "query": query, "raw": text}
    return {"intent": "none", "raw": text}
