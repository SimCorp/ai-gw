import json

_PROBE_TO_CATEGORY = {
    "promptinjection": "prompt_injection",
    "jailbreak": "jailbreak",
    "leakage": "pii_extraction",
    "toxicity": "toxicity",
    "xss": "xss",
    "continuation": "content_policy",
}

_PROBE_TO_SEVERITY = {
    "promptinjection": "high",
    "jailbreak": "high",
    "leakage": "critical",
    "toxicity": "medium",
}


def _probe_prefix(probe_class: str) -> str:
    return probe_class.split(".")[0].lower() if "." in probe_class else probe_class.lower()


def parse_garak_jsonl(output: str) -> list[dict]:
    findings = []
    for line in output.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            continue
        if record.get("passed", True):
            continue
        probe_class = record.get("probe", "unknown")
        prefix = _probe_prefix(probe_class)
        category = _PROBE_TO_CATEGORY.get(prefix, "ai_security")
        severity = _PROBE_TO_SEVERITY.get(prefix, "medium")
        findings.append(
            {
                "scanner": "garak",
                "severity": severity,
                "category": category,
                "title": f"Garak probe failed: {probe_class}",
                "description": (
                    f"The probe '{probe_class}' triggered a failure. "
                    f"The model may be susceptible to {category.replace('_', ' ')}."
                ),
                "evidence": {
                    "probe": probe_class,
                    "passed": False,
                    "notes": record.get("notes", {}),
                    "attempt_idx": record.get("attempt_idx"),
                },
                "remediation": (
                    f"Review the model's system prompt and add guardrail rules to block "
                    f"{category.replace('_', ' ')} patterns."
                ),
            }
        )
    return findings
