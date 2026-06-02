"""Pure guardrail evaluation — no I/O, no side-effects.

Used by the request-path to enforce block/redact/flag rules on both
the input prompt and the output completion.
"""

import functools
import re
from dataclasses import dataclass, field


@dataclass
class GuardrailOutcome:
    blocked_rule: str | None  # name of the first block rule that matched, else None
    text: str  # input text with redactions applied (unchanged if none)
    hits: list[dict] = field(default_factory=list)  # one per matched rule


@functools.lru_cache(maxsize=512)
def _compile(pattern: str) -> re.Pattern | None:
    """Compile a regex pattern; return None if it is invalid (never raises)."""
    try:
        return re.compile(pattern, re.IGNORECASE)
    except Exception:
        return None


def evaluate_guardrails(rules: list[dict], text: str, direction: str) -> GuardrailOutcome:
    """Evaluate *rules* against *text* in the given *direction* ("input" or "output").

    Direction filtering:
      "input"  → considers rules whose applies_to is "input" or "both"
      "output" → considers rules whose applies_to is "output" or "both"

    For each rule that matches (any of its config.patterns matches text):
      - "block":  record hit, set blocked_rule (first wins), stop processing.
      - "redact": replace every match of every pattern with the rule's mask
                  (config.mask or "[REDACTED]"), record hit, continue.
      - anything else ("flag", unknown): record hit only, text unchanged.

    A bad/uncompilable pattern is silently skipped; the function never raises.
    """
    _INPUT_APPLIES = {"input", "both"}
    _OUTPUT_APPLIES = {"output", "both"}

    allowed = _INPUT_APPLIES if direction == "input" else _OUTPUT_APPLIES

    hits: list[dict] = []
    blocked_rule: str | None = None

    for rule in rules:
        if not rule.get("enabled", True):
            continue
        if rule.get("applies_to", "input") not in allowed:
            continue

        patterns = rule.get("config", {}).get("patterns", [])
        action = rule.get("action", "flag")
        mask = rule.get("config", {}).get("mask", "[REDACTED]")

        # Check whether any pattern matches the current text
        compiled = [_compile(p) for p in patterns]
        matched = any(rx is not None and rx.search(text) for rx in compiled)

        if not matched:
            continue

        # Record hit (caller merges request-context fields before emitting)
        hits.append(
            {
                "guardrail_id": rule.get("id"),
                "guardrail_type": rule.get("type"),
                "action_taken": action,
                "severity": rule.get("severity", "high"),
                "input_or_output": direction,
            }
        )

        if action == "block":
            blocked_rule = rule.get("name", "guardrail")
            break  # first block wins; stop processing
        elif action == "redact":
            for rx in compiled:
                if rx is not None:
                    text = rx.sub(mask, text)
            # continue to next rule

    return GuardrailOutcome(blocked_rule=blocked_rule, text=text, hits=hits)
