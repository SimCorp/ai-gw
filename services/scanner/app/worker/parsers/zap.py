import json

_RISK_SEVERITY = {"3": "high", "2": "medium", "1": "low", "0": "info"}


def parse_zap_json(json_str: str) -> list[dict]:
    findings = []
    try:
        data = json.loads(json_str)
    except (json.JSONDecodeError, TypeError):
        return findings
    for site in data.get("site", []):
        for alert in site.get("alerts", []):
            risk = str(alert.get("riskcode", "0"))
            severity = _RISK_SEVERITY.get(risk, "info")
            findings.append({
                "scanner": "zap",
                "severity": severity,
                "category": "api_vuln",
                "title": alert.get("name") or alert.get("alert", "ZAP finding"),
                "description": (alert.get("desc") or "").strip(),
                "evidence": {
                    "pluginid": alert.get("pluginid"),
                    "confidence": alert.get("confidence"),
                    "instances": alert.get("instances", [])[:3],
                },
                "remediation": (alert.get("solution") or "").strip() or None,
            })
    return findings
