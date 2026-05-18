#!/usr/bin/env python3
"""Seed the AI Gateway with the real SimCorp governance hierarchy.

Usage:
    ADMIN_TOKEN=<token> python scripts/seed_simcorp_org.py
    python scripts/seed_simcorp_org.py  # prompts for token

The script is idempotent: it checks slugs before creating and skips existing
resources. Placeholder areas (Engineering, Risk & Compliance, Finance,
AI Transformation) are deleted if they have no teams.

Target structure:
    Area: Product Development
        Unit: Platform
            Sub-unit: DevEx
                Teams: Application, Connectivity & Cloud Foundations,
                       Connectivity & Platform Services, Core, Hosting, Lift
            Sub-unit: Architecture
            Sub-unit: Platform Engineering
            Sub-unit: Release & Adoption
            Sub-unit: Security & Compliance
            Sub-unit: SaaS Onboarding & Reliability
        Unit: Application
        Unit: PD Strategy & Excellence
        Unit: Product Management
    Area: Commercial Management
    Area: Global Finance, IT & Legal
    Area: Global People & Culture
"""

import os
import sys
import json
import urllib.request
import urllib.error

BASE = os.environ.get("ADMIN_API", "http://localhost:8005")


def get_token() -> str:
    token = os.environ.get("ADMIN_TOKEN", "")
    if not token:
        token = input("Admin token: ").strip()
    if not token:
        sys.exit("No token provided.")
    return token


def req(method: str, path: str, token: str, body: dict | None = None):
    url = f"{BASE}{path}"
    data = json.dumps(body).encode() if body is not None else None
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }
    r = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(r) as resp:
            raw = resp.read()
            return json.loads(raw) if raw else None
    except urllib.error.HTTPError as e:
        body_text = e.read().decode()
        raise RuntimeError(f"{method} {path} → {e.code}: {body_text}") from e


def ensure_area(token: str, areas: list, name: str, slug: str, color: str, description: str) -> str:
    existing = next((a for a in areas if a["slug"] == slug), None)
    if existing:
        print(f"  [skip] area '{name}' already exists")
        return existing["id"]
    result = req("POST", "/areas", token, {"name": name, "slug": slug, "color": color, "description": description})
    print(f"  [+] area '{name}'")
    return result["id"]


def ensure_unit(token: str, units: list, area_id: str, name: str, slug: str,
                description: str, color: str, parent_unit_id: str | None = None) -> str:
    existing = next((u for u in units if u["slug"] == slug and u["area_id"] == area_id), None)
    if existing:
        print(f"  [skip] unit '{name}'")
        return existing["id"]
    result = req("POST", "/units", token, {
        "area_id": area_id,
        "name": name,
        "slug": slug,
        "description": description,
        "color": color,
        "parent_unit_id": parent_unit_id,
    })
    print(f"  [+] unit '{name}'" + (f" (sub-unit of parent)" if parent_unit_id else ""))
    return result["id"]


def ensure_team(token: str, teams: list, unit_id: str, name: str, slug: str) -> str:
    existing = next((t for t in teams if t["slug"] == slug), None)
    if existing:
        print(f"  [skip] team '{name}'")
        return existing["id"]
    result = req("POST", "/teams", token, {"unit_id": unit_id, "name": name, "slug": slug})
    print(f"  [+] team '{name}'")
    return result["id"]


def delete_placeholder_areas(token: str, areas: list):
    placeholders = ["engineering", "risk-compliance", "finance", "ai-transformation"]
    for slug in placeholders:
        area = next((a for a in areas if a["slug"] == slug), None)
        if not area:
            continue
        area_id = area["id"]
        units = req("GET", f"/units?area_id={area_id}", token) or []
        has_teams = any(u.get("team_count", 0) > 0 for u in units)
        if has_teams:
            print(f"  [skip] placeholder area '{area['name']}' has teams — not deleting")
            continue
        for u in units:
            req("DELETE", f"/units/{u['id']}", token)
        req("DELETE", f"/areas/{area_id}", token)
        print(f"  [-] deleted placeholder area '{area['name']}'")


def main():
    token = get_token()

    print("\nFetching current state...")
    areas = req("GET", "/areas", token) or []
    units = req("GET", "/units", token) or []
    all_teams: list = []
    for u in units:
        try:
            detail = req("GET", f"/units/{u['id']}", token)
            all_teams.extend(detail.get("teams", []))
        except Exception:
            pass

    print("\nRemoving placeholder areas...")
    delete_placeholder_areas(token, areas)

    areas = req("GET", "/areas", token) or []

    print("\nCreating Areas...")
    pd_id = ensure_area(token, areas, "Product Development", "product-development", "#0A7BD7",
                        "Marc Schröter — CPO/CTO")
    cm_id = ensure_area(token, areas, "Commercial Management", "commercial-management", "#1D958E",
                        "Oliver Johnson — CRO")
    fi_id = ensure_area(token, areas, "Global Finance, IT & Legal", "global-finance-it-legal", "#EF3E4A",
                        "Jeroen van den Heuvel — CFO")
    pc_id = ensure_area(token, areas, "Global People & Culture", "global-people-culture", "#4B17B6",
                        "Debbie Townley — CPCO")
    _ = cm_id, fi_id, pc_id  # created but no sub-structure seeded yet

    units = req("GET", "/units", token) or []

    print("\nCreating Units under Product Development...")
    platform_id = ensure_unit(token, units, pd_id, "Platform", "platform",
                              "Ulrik Elstrup Hansen, SVP", "#0A7BD7")
    _app_id = ensure_unit(token, units, pd_id, "Application", "application",
                          "Per Karlsson, SVP Engineering", "#0A7BD7")
    _strat_id = ensure_unit(token, units, pd_id, "PD Strategy & Excellence", "pd-strategy-excellence",
                            "Stefan Rubæk Holm, VP", "#0A7BD7")
    _pm_id = ensure_unit(token, units, pd_id, "Product Management", "product-management",
                         "Iyan Adewuya, CPO", "#0A7BD7")

    units = req("GET", "/units", token) or []

    print("\nCreating Sub-units under Platform...")
    devex_id = ensure_unit(token, units, pd_id, "DevEx", "devex",
                           "Benjamin Thillerup, AVP Engineering", "#0A7BD7", parent_unit_id=platform_id)
    ensure_unit(token, units, pd_id, "Architecture", "architecture",
                "Frederik Gottlieb", "#0A7BD7", parent_unit_id=platform_id)
    ensure_unit(token, units, pd_id, "Platform Engineering", "platform-engineering",
                "Chris Blake", "#0A7BD7", parent_unit_id=platform_id)
    ensure_unit(token, units, pd_id, "Release & Adoption", "release-adoption",
                "Niclas Nordsted", "#0A7BD7", parent_unit_id=platform_id)
    ensure_unit(token, units, pd_id, "Security & Compliance", "security-compliance",
                "Anne Færch", "#0A7BD7", parent_unit_id=platform_id)
    ensure_unit(token, units, pd_id, "SaaS Onboarding & Reliability", "saas-onboarding-reliability",
                "Neil Cook", "#0A7BD7", parent_unit_id=platform_id)

    print("\nCreating Teams under DevEx...")
    ensure_team(token, all_teams, devex_id, "Application", "devex-application")
    ensure_team(token, all_teams, devex_id, "Connectivity & Cloud Foundations", "devex-connectivity-cloud")
    ensure_team(token, all_teams, devex_id, "Connectivity & Platform Services", "devex-connectivity-platform")
    ensure_team(token, all_teams, devex_id, "Core", "devex-core")
    ensure_team(token, all_teams, devex_id, "Hosting", "devex-hosting")
    ensure_team(token, all_teams, devex_id, "Lift", "devex-lift")

    print("\nDone. SimCorp org hierarchy seeded successfully.")
    print(f"  Areas:    http://localhost:3001/admin/areas")
    print(f"  Units:    http://localhost:3001/admin/units")
    print(f"  Teams:    http://localhost:3001/admin/teams")


if __name__ == "__main__":
    main()
