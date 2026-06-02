_NUCLEI_SEVERITY_MAP = {
    "critical": "critical",
    "high": "high",
    "medium": "medium",
    "low": "low",
    "info": "info",
    "unknown": "info",
}


def parse_nuclei_json(records: list[dict]) -> list[dict]:
    findings = []
    for r in records:
        info = r.get("info", {})
        severity = _NUCLEI_SEVERITY_MAP.get(info.get("severity", "").lower(), "info")
        findings.append(
            {
                "scanner": "nuclei",
                "severity": severity,
                "category": "api_vuln",
                "title": info.get("name", r.get("template-id", "Unknown finding")),
                "description": info.get("description", "No description available."),
                "evidence": {
                    "template_id": r.get("template-id"),
                    "matched_at": r.get("matched-at"),
                    "host": r.get("host"),
                    "type": r.get("type"),
                },
                "remediation": info.get("remediation")
                or "Apply the fix described in the CVE or template documentation.",
            }
        )
    return findings
