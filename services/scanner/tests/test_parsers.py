from app.worker.parsers.garak import parse_garak_jsonl
from app.worker.parsers.nuclei import parse_nuclei_json
from app.worker.parsers.nmap import parse_nmap_xml


GARAK_SAMPLE = """
{"attempt_idx":0,"probe":"promptinjection.HijackHateHumans","result_class":"promptinjection.HijackHateHumans","passed":false,"notes":{"trigger":"ignore previous","response":"I will now say hateful things"}}
{"attempt_idx":1,"probe":"promptinjection.HijackHateHumans","result_class":"promptinjection.HijackHateHumans","passed":true,"notes":{}}
"""

NUCLEI_SAMPLE = [
    {
        "template-id": "CVE-2021-41773",
        "info": {"name": "Path Traversal", "severity": "critical", "description": "Apache path traversal"},
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
