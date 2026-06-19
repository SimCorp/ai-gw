"""AI Gateway scope taxonomy — canonical source of truth.

Scopes follow the pattern: ai-gw:<resource>:<action>
Wildcards use '*' (resolved at enforcement time against team policy).
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# Control plane scopes
# ---------------------------------------------------------------------------

CP_METRICS_READ = "ai-gw:metrics:read"
CP_AUDIT_READ = "ai-gw:audit:read"
CP_COST_READ = "ai-gw:cost:read"
CP_COST_WRITE = "ai-gw:cost:write"
CP_TEAM_READ = "ai-gw:team:read"
CP_TEAM_WRITE = "ai-gw:team:write"
CP_KEY_CREATE = "ai-gw:key:create"
CP_KEY_REVOKE = "ai-gw:key:revoke"
CP_POLICY_READ = "ai-gw:policy:read"
CP_POLICY_WRITE = "ai-gw:policy:write"
CP_GUARDRAIL_READ = "ai-gw:guardrail:read"
CP_GUARDRAIL_WRITE = "ai-gw:guardrail:write"
CP_INSIGHTS_READ = "ai-gw:insights:read"
CP_AREA_ADMIN = "ai-gw:area:admin"

# ---------------------------------------------------------------------------
# Data plane scopes
# ---------------------------------------------------------------------------

DP_INFERENCE_ALL = "ai-gw:inference:*"
DP_INFERENCE_CLAUDE_ALL = "ai-gw:inference:claude:*"
DP_INFERENCE_OPENAI_ALL = "ai-gw:inference:openai:*"
DP_INFERENCE_HAIKU = "ai-gw:inference:claude-haiku:execute"
DP_INFERENCE_SONNET = "ai-gw:inference:claude-sonnet:execute"
DP_INFERENCE_OPUS = "ai-gw:inference:claude-opus:execute"
DP_STREAMING = "ai-gw:streaming:enable"
DP_TOOL_EXECUTE = "ai-gw:tool:execute"
DP_CACHE_BYPASS = "ai-gw:cache:bypass"
DP_AUTODRIVE_OVERRIDE = "ai-gw:autodrive:override"
DP_BATCH_SUBMIT = "ai-gw:batch:submit"
DP_VISION_EXECUTE = "ai-gw:vision:execute"

ALL_SCOPES: list[str] = [
    CP_METRICS_READ,
    CP_AUDIT_READ,
    CP_COST_READ,
    CP_COST_WRITE,
    CP_TEAM_READ,
    CP_TEAM_WRITE,
    CP_KEY_CREATE,
    CP_KEY_REVOKE,
    CP_POLICY_READ,
    CP_POLICY_WRITE,
    CP_GUARDRAIL_READ,
    CP_GUARDRAIL_WRITE,
    CP_INSIGHTS_READ,
    CP_AREA_ADMIN,
    DP_INFERENCE_ALL,
    DP_INFERENCE_CLAUDE_ALL,
    DP_INFERENCE_OPENAI_ALL,
    DP_INFERENCE_HAIKU,
    DP_INFERENCE_SONNET,
    DP_INFERENCE_OPUS,
    DP_STREAMING,
    DP_TOOL_EXECUTE,
    DP_CACHE_BYPASS,
    DP_AUTODRIVE_OVERRIDE,
    DP_BATCH_SUBMIT,
    DP_VISION_EXECUTE,
]

# ---------------------------------------------------------------------------
# Role → default scope bundles
# ---------------------------------------------------------------------------

ROLE_SCOPES: dict[str, list[str]] = {
    "platform_admin": ALL_SCOPES,
    "area_owner": [
        CP_METRICS_READ,
        CP_AUDIT_READ,
        CP_COST_READ,
        CP_COST_WRITE,
        CP_TEAM_READ,
        CP_POLICY_READ,
        CP_GUARDRAIL_READ,
        CP_INSIGHTS_READ,
        CP_AREA_ADMIN,
        DP_INFERENCE_ALL,
        DP_STREAMING,
        DP_TOOL_EXECUTE,
    ],
    "unit_lead": [
        CP_METRICS_READ,
        CP_AUDIT_READ,
        CP_COST_READ,
        CP_TEAM_READ,
        CP_POLICY_READ,
    ],
    "team_admin": [
        CP_METRICS_READ,
        CP_AUDIT_READ,
        CP_COST_READ,
        CP_COST_WRITE,
        CP_TEAM_READ,
        CP_TEAM_WRITE,
        CP_KEY_CREATE,
        CP_KEY_REVOKE,
        CP_POLICY_READ,
        CP_POLICY_WRITE,
        CP_GUARDRAIL_READ,
        DP_INFERENCE_ALL,
        DP_STREAMING,
        DP_TOOL_EXECUTE,
    ],
    "developer": [
        CP_METRICS_READ,
        CP_COST_READ,
        DP_INFERENCE_ALL,
        DP_STREAMING,
        DP_TOOL_EXECUTE,
    ],
    "viewer": [
        CP_METRICS_READ,
        CP_AUDIT_READ,
        CP_COST_READ,
    ],
    "service_account": [
        DP_INFERENCE_ALL,
    ],
}

# Default scopes for a newly issued API key
DEFAULT_KEY_SCOPES: list[str] = [DP_INFERENCE_ALL]

# Scopes a developer may self-assign when minting an API key via the portal.
# Control-plane (CP_*) scopes are never honored on an sk- key, so they must not
# be grantable through self-service key creation (defence against minting keys
# that claim privileges the developer does not hold).
SELF_SERVICE_KEY_SCOPES: list[str] = [
    DP_INFERENCE_ALL,
    DP_INFERENCE_CLAUDE_ALL,
    DP_INFERENCE_OPENAI_ALL,
    DP_INFERENCE_HAIKU,
    DP_INFERENCE_SONNET,
    DP_INFERENCE_OPUS,
    DP_STREAMING,
    DP_TOOL_EXECUTE,
    DP_CACHE_BYPASS,
    DP_AUTODRIVE_OVERRIDE,
    DP_BATCH_SUBMIT,
    DP_VISION_EXECUTE,
]


# ---------------------------------------------------------------------------
# Scope matching — resolves wildcards
# ---------------------------------------------------------------------------


def scope_matches(requested: str, granted: str) -> bool:
    """Return True if `granted` scope covers the `requested` scope.

    Wildcards in `granted` are prefix-matched:
      ai-gw:inference:*         covers ai-gw:inference:claude-haiku:execute
      ai-gw:inference:claude:*  covers ai-gw:inference:claude-haiku:execute
      ai-gw:inference:claude-haiku:execute  covers only itself
    """
    if granted == requested:
        return True
    if granted.endswith(":*"):
        prefix = granted[:-2]  # strip ':*'
        return requested.startswith(prefix + ":")
    if granted == "ai-gw:inference:*":
        return requested.startswith("ai-gw:inference:")
    return False


def has_scope(requested: str, granted_scopes: list[str]) -> bool:
    """Return True if any granted scope covers the requested scope."""
    return any(scope_matches(requested, g) for g in granted_scopes)


def model_to_scope(model: str) -> str:
    """Map a model name to its data-plane scope.

    Examples:
      claude-haiku-4-5        → ai-gw:inference:claude-haiku:execute
      claude-sonnet-4-6       → ai-gw:inference:claude-sonnet:execute
      gpt-4o                  → ai-gw:inference:openai:*
      unknown-model           → ai-gw:inference:*
    """
    m = model.lower()
    if "haiku" in m:
        return DP_INFERENCE_HAIKU
    if "sonnet" in m:
        return DP_INFERENCE_SONNET
    if "opus" in m:
        return DP_INFERENCE_OPUS
    if m.startswith("claude"):
        return DP_INFERENCE_CLAUDE_ALL
    if m.startswith("gpt") or m.startswith("o1") or m.startswith("o3"):
        return DP_INFERENCE_OPENAI_ALL
    return DP_INFERENCE_ALL
