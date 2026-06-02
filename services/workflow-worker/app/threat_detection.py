"""Agent output threat detection — SafeOutputs pattern from gh-aw.

Scans agent outputs before they propagate to downstream DAG nodes or are
persisted to the database. Runs against cached guardrail patterns fetched
from the admin service on startup.

Fail-open by design: if the admin service is unreachable or patterns are
unavailable, all outputs are allowed through (consistent with the Gateway's
existing fail-open philosophy).
"""

import logging
import re
from typing import Any

_log = logging.getLogger(__name__)

# Patterns that indicate credential leakage — compiled at startup
_SECRET_PATTERNS: list[re.Pattern] = []
_INJECTION_PHRASES: list[str] = []

# Patterns preloaded from guardrails service
_PATTERNS_LOADED = False


def _compile_defaults() -> None:
    """Bootstrap with known-dangerous patterns even if guardrails unreachable."""
    global _SECRET_PATTERNS, _INJECTION_PHRASES, _PATTERNS_LOADED
    _SECRET_PATTERNS = [
        re.compile(r"aigw_run_[A-Za-z0-9_\-]{20,}", re.I),  # scoped gateway keys
        re.compile(r"sk-ant-api[A-Za-z0-9\-_]{20,}", re.I),  # Anthropic keys
        re.compile(r"sk-[a-zA-Z0-9]{20,}", re.I),  # OpenAI-style keys
        re.compile(r"-----BEGIN (RSA |EC |OPENSSH )?PRIVATE KEY-----"),  # private keys
        re.compile(r'(?i)(password|passwd|secret|token)\s*[=:]\s*["\']?[A-Za-z0-9!@#$%^&*]{8,}'),
    ]
    _INJECTION_PHRASES = [
        "ignore previous instructions",
        "ignore all previous",
        "disregard all prior",
        "you are now",
        "new persona",
        "jailbreak",
        "bypass your instructions",
    ]
    _PATTERNS_LOADED = True


async def load_patterns_from_admin(admin_url: str) -> None:
    """Fetch guardrail patterns from the admin service and extend the defaults."""
    global _SECRET_PATTERNS, _INJECTION_PHRASES
    _compile_defaults()  # always load defaults first
    try:
        import httpx

        async with httpx.AsyncClient(timeout=5) as client:
            r = await client.get(f"{admin_url}/guardrails?enabled=true")
            if r.status_code != 200:
                return
            guardrails = r.json()
            for g in guardrails:
                cfg = g.get("config", {})
                for pattern in cfg.get("patterns", []):
                    # Map known pattern names to regexes
                    _enrich_from_pattern_name(pattern)
    except Exception as exc:
        _log.warning("threat-detection: could not load guardrails patterns: %s", exc)


def _enrich_from_pattern_name(name: str) -> None:
    """Map guardrail pattern names to compiled regexes."""
    KNOWN = {
        "aws_access_key": re.compile(r"AKIA[0-9A-Z]{16}"),
        "github_token": re.compile(r"gh[opsu]_[A-Za-z0-9]{36,}"),
        "openai_key": re.compile(r"sk-[a-zA-Z0-9]{20,}", re.I),
        "anthropic_key": re.compile(r"sk-ant-[a-zA-Z0-9\-_]{20,}", re.I),
        "jwt": re.compile(r"eyJ[A-Za-z0-9\-_]+\.[A-Za-z0-9\-_]+\.[A-Za-z0-9\-_]+"),
        "private_key_header": re.compile(r"-----BEGIN (RSA |EC |OPENSSH )?PRIVATE KEY-----"),
        "db_connstring": re.compile(r'(postgresql|mysql|mongodb)\+?://[^\s"\']+:[^\s"\']+@'),
    }
    if name in KNOWN and KNOWN[name] not in _SECRET_PATTERNS:
        _SECRET_PATTERNS.append(KNOWN[name])


def _scan_value(value: Any, path: str = "") -> list[str]:
    """Recursively scan a value for threats. Returns list of findings."""
    findings = []
    if isinstance(value, str):
        # Check secret patterns
        for pattern in _SECRET_PATTERNS:
            if pattern.search(value):
                findings.append(f"secret pattern at {path}: {pattern.pattern[:40]}...")
        # Check injection phrases
        v_lower = value.lower()
        for phrase in _INJECTION_PHRASES:
            if phrase in v_lower:
                findings.append(f"injection phrase at {path}: '{phrase}'")
    elif isinstance(value, dict):
        for k, v in value.items():
            findings.extend(_scan_value(v, f"{path}.{k}" if path else k))
    elif isinstance(value, list):
        for i, item in enumerate(value):
            findings.extend(_scan_value(item, f"{path}[{i}]"))
    return findings


def scan_outputs(outputs: dict) -> tuple[bool, list[str]]:
    """Scan agent outputs for threats.

    Returns (clean, findings) where clean=True means no threats detected.
    Fail-open: if patterns not loaded, returns (True, []).
    """
    if not _PATTERNS_LOADED:
        _compile_defaults()

    findings = _scan_value(outputs)
    if findings:
        _log.warning(
            "threat-detection: %d finding(s) in agent outputs: %s", len(findings), findings[:3]
        )
    return (len(findings) == 0, findings)
