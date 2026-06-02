import xml.etree.ElementTree as ET

_EXPECTED_INTERNAL_PORTS = {
    22,
    80,
    443,
    8080,
    8443,
    8000,
    8001,
    8002,
    8003,
    8004,
    8005,
    8006,
    8007,
    8008,
    8009,
    8010,
    8011,
    3000,
    3001,
    3002,
}

_PORT_SEVERITY = {
    21: "high",
    23: "high",
    25: "medium",
    110: "medium",
    143: "medium",
    3306: "high",
    5432: "high",
    6379: "high",
    27017: "high",
}


def parse_nmap_xml(xml_output: str) -> list[dict]:
    findings = []
    try:
        root = ET.fromstring(xml_output)
    except ET.ParseError:
        return findings

    for host in root.findall("host"):
        ports_elem = host.find("ports")
        if ports_elem is None:
            continue
        for port_elem in ports_elem.findall("port"):
            state = port_elem.find("state")
            if state is None or state.get("state") != "open":
                continue
            portid = port_elem.get("portid")
            if not portid:
                continue
            port_num = int(portid)
            service = port_elem.find("service")
            service_name = service.get("name", "unknown") if service is not None else "unknown"
            service_product = service.get("product", "") if service is not None else ""
            service_version = service.get("version", "") if service is not None else ""

            severity = _PORT_SEVERITY.get(
                port_num,
                "info" if port_num in _EXPECTED_INTERNAL_PORTS else "low",
            )
            description = (
                f"Port {port_num} is open and running {service_product} {service_version}".strip()
                or f"Port {port_num} is open."
            )
            findings.append(
                {
                    "scanner": "nmap",
                    "severity": severity,
                    "category": "open_port",
                    "title": f"Open port {port_num}/{port_elem.get('protocol', 'tcp')}: {service_name}",
                    "description": description,
                    "evidence": {
                        "port": port_num,
                        "protocol": port_elem.get("protocol", "tcp"),
                        "service": service_name,
                        "product": service_product,
                        "version": service_version,
                    },
                    "remediation": (
                        "Ensure this port is intentionally exposed. "
                        "If not needed externally, restrict access via firewall rules."
                    )
                    if severity != "info"
                    else "Port appears expected for this service type.",
                }
            )
    return findings
