"""Content sanitizer for agent inputs — pattern from gh-aw Content Sanitization layer.

Sanitizes the inputs dict before writing to inputs.json to prevent:
- @mention injection (actors referencing GitHub users to confuse agents)
- XML/HTML tag injection (potential XSS-like prompt manipulation)
- Oversized payloads (DoS via large inputs)
- Excessive key counts (complexity explosion)
"""
import json
import re
import logging
from typing import Any

_log = logging.getLogger(__name__)

_MAX_STRING_CHARS = 50_000
_MAX_KEYS_TOTAL = 100
_MAX_JSON_BYTES = 1_048_576  # 1 MB

_MENTION_RE = re.compile(r'@[A-Za-z0-9_-]+')


def sanitize_string(value: str, path: str = "") -> str:
    """Sanitize a single string value."""
    # Replace @mentions
    value = _MENTION_RE.sub("(mention redacted)", value)
    # Convert < and > to safe entities
    value = value.replace("<", "&lt;").replace(">", "&gt;")
    # Enforce length limit
    if len(value) > _MAX_STRING_CHARS:
        _log.info("sanitizer: truncated string at %s from %d to %d chars",
                  path, len(value), _MAX_STRING_CHARS)
        value = value[:_MAX_STRING_CHARS] + " [truncated]"
    return value


def _sanitize_value(value: Any, path: str = "", key_count: list[int] = None) -> Any:
    """Recursively sanitize a value."""
    if key_count is None:
        key_count = [0]

    if isinstance(value, str):
        return sanitize_string(value, path)
    elif isinstance(value, dict):
        result = {}
        for k, v in value.items():
            key_count[0] += 1
            if key_count[0] > _MAX_KEYS_TOTAL:
                _log.warning("sanitizer: key limit reached at %s, truncating", path)
                break
            result[k] = _sanitize_value(v, f"{path}.{k}" if path else k, key_count)
        return result
    elif isinstance(value, list):
        return [_sanitize_value(item, f"{path}[{i}]", key_count)
                for i, item in enumerate(value)]
    else:
        return value


def sanitize_inputs(inputs: dict) -> dict:
    """Sanitize a full inputs dict. Returns the sanitized copy."""
    sanitized = _sanitize_value(inputs)
    # Enforce total size limit
    serialized = json.dumps(sanitized)
    if len(serialized.encode()) > _MAX_JSON_BYTES:
        _log.warning("sanitizer: inputs exceed 1MB after sanitization, truncating to top-level keys")
        # Fallback: keep only top-level string values
        sanitized = {
            k: v for k, v in sanitized.items()
            if isinstance(v, (str, int, float, bool)) or v is None
        }
    return sanitized
