import json as _json

from app.worker.parsers.garak import parse_garak_jsonl
from app.worker.parsers.nmap import parse_nmap_xml
from app.worker.parsers.nuclei import parse_nuclei_json

GARAK_SAMPLE = """
{"attempt_idx":0,"probe":"promptinjection.HijackHateHumans","result_class":"promptinjection.HijackHateHumans","passed":false,"notes":{"trigger":"ignore previous","response":"I will now say hateful things"}}
{"attempt_idx":1,"probe":"promptinjection.HijackHateHumans","result_class":"promptinjection.HijackHateHumans","passed":true,"notes":{}}
"""

NUCLEI_SAMPLE = [
    {
        "template-id": "CVE-2021-41773",
        "info": {
            "name": "Path Traversal",
            "severity": "critical",
            "description": "Apache path traversal",
        },
        "host": "http://myapp.simcorp.internal",
        "matched-at": "http://myapp.simcorp.internal/cgi-bin/.%2e/%2e%2e/etc/passwd",
        "type": "http",
    }
]

NMAP_XML = """<?xml version="1.0"?>
<nmaprun>
  <host>
    <ports>
      <port protocol="tcp" portid="22">
        <state state="open"/>
        <service name="ssh" product="OpenSSH" version="8.9"/>
      </port>
      <port protocol="tcp" portid="8080">
        <state state="open"/>
        <service name="http" product="nginx"/>
      </port>
    </ports>
  </host>
</nmaprun>"""


def test_garak_parse_finds_failure():
    findings = parse_garak_jsonl(GARAK_SAMPLE)
    assert len(findings) == 1
    f = findings[0]
    assert f["scanner"] == "garak"
    assert f["category"] == "prompt_injection"
    assert f["severity"] in ("critical", "high", "medium", "low", "info")
    assert "title" in f
    assert "description" in f


def test_garak_parse_passes_ignored():
    findings = parse_garak_jsonl(GARAK_SAMPLE)
    assert all(f["evidence"]["passed"] is False for f in findings)


def test_nuclei_parse():
    findings = parse_nuclei_json(NUCLEI_SAMPLE)
    assert len(findings) == 1
    f = findings[0]
    assert f["scanner"] == "nuclei"
    assert f["severity"] == "critical"
    assert f["title"] == "Path Traversal"


def test_nmap_parse_open_ports():
    findings = parse_nmap_xml(NMAP_XML)
    assert len(findings) == 2
    ports = {f["evidence"]["port"] for f in findings}
    assert ports == {22, 8080}
    assert all(f["scanner"] == "nmap" for f in findings)
    assert all(f["category"] == "open_port" for f in findings)


def test_nmap_parse_severity_ssh():
    findings = parse_nmap_xml(NMAP_XML)
    ssh = next(f for f in findings if f["evidence"]["port"] == 22)
    assert ssh["severity"] == "info"


def test_nuclei_empty():
    assert parse_nuclei_json([]) == []


def test_garak_empty():
    assert parse_garak_jsonl("") == []


ZAP_SAMPLE = _json.dumps(
    {
        "site": [
            {
                "name": "http://myapp.simcorp.internal",
                "alerts": [
                    {
                        "pluginid": "10202",
                        "name": "Absence of Anti-CSRF Tokens",
                        "riskcode": "2",
                        "confidence": "2",
                        "desc": "No Anti-CSRF tokens found in HTML forms.",
                        "instances": [
                            {"uri": "http://myapp.simcorp.internal/form", "method": "GET"}
                        ],
                        "solution": "Use CSRF tokens in forms.",
                    },
                    {
                        "pluginid": "10049",
                        "name": "Non-Storable Content",
                        "riskcode": "0",
                        "confidence": "3",
                        "desc": "Response not storable by caching components.",
                        "instances": [],
                        "solution": "",
                    },
                ],
            }
        ]
    }
)


def test_zap_parse_finds_findings():
    from app.worker.parsers.zap import parse_zap_json

    findings = parse_zap_json(ZAP_SAMPLE)
    assert len(findings) == 2
    assert all(f["scanner"] == "zap" for f in findings)
    assert all(f["category"] == "api_vuln" for f in findings)


def test_zap_parse_severity_mapping():
    from app.worker.parsers.zap import parse_zap_json

    findings = parse_zap_json(ZAP_SAMPLE)
    medium = next(f for f in findings if f["title"] == "Absence of Anti-CSRF Tokens")
    info = next(f for f in findings if f["title"] == "Non-Storable Content")
    assert medium["severity"] == "medium"
    assert info["severity"] == "info"


def test_zap_parse_empty_and_invalid():
    from app.worker.parsers.zap import parse_zap_json

    assert parse_zap_json("{}") == []
    assert parse_zap_json("") == []
    assert parse_zap_json("not json") == []
