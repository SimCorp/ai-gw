#!/usr/bin/env python3
"""
Seed the SimCorp Workday org structure into ai-gw.

Idempotent: runs GET first, only creates if missing (matched by name).
Run: python services/admin/scripts/seed_workday_org.py
Or inside docker: docker compose -f infra/docker-compose.yml exec admin python /app/scripts/seed_workday_org.py
"""

import os
import sys

import httpx

BASE_URL = os.getenv("ADMIN_URL", "http://localhost:8005")
EMAIL = os.getenv("ADMIN_EMAIL", "admin@simcorp.com")
PASSWORD = os.getenv("ADMIN_PASSWORD", "Admin2024!")


def main():
    with httpx.Client(base_url=BASE_URL, timeout=30) as c:
        # Login via unified auth endpoint
        r = c.post("/auth/login", json={"email": EMAIL, "password": PASSWORD})
        r.raise_for_status()
        token = r.json()["token"]
        headers = {"Authorization": f"Bearer {token}"}

        # ------------------------------------------------------------------ #
        # Areas                                                                #
        # API accepts: name, slug, description, color                         #
        # ------------------------------------------------------------------ #
        existing_areas = {a["name"]: a for a in c.get("/areas", headers=headers).json()}

        areas_data = [
            {
                "name": "Product & Technology",
                "slug": "product-technology",
                "color": "#3B82F6",
                "description": "Marc Schröter — Engineering, Platform, Product",
            },
            {
                "name": "Operations",
                "slug": "operations",
                "color": "#10B981",
                "description": "Ronan Donnelly — Value Streams, Client Operations",
            },
            {
                "name": "Commercial",
                "slug": "commercial",
                "color": "#F59E0B",
                "description": "Oliver Johnson — EMEA, APAC, Americas",
            },
            {
                "name": "Finance & IT",
                "slug": "finance-it",
                "color": "#8B5CF6",
                "description": "Jeroen van den Heuvel — Group IT, Finance, CISO",
            },
            {
                "name": "Professional Services",
                "slug": "professional-services",
                "color": "#EF4444",
                "description": "Fred Bouteiller — Consulting, Delivery",
            },
            {
                "name": "People & Culture",
                "slug": "people-culture",
                "color": "#EC4899",
                "description": "Debbie Townley — HR, Comms, Learning",
            },
            {
                "name": "Strategy",
                "slug": "strategy",
                "color": "#6366F1",
                "description": "Anders Halsteen Thomsen — Group Strategy",
            },
            {
                "name": "Managed Business Services",
                "slug": "mbs",
                "color": "#14B8A6",
                "description": "Ulrik Modigh — MBS Delivery",
            },
        ]

        area_ids = {}
        for a in areas_data:
            if a["name"] in existing_areas:
                area_ids[a["name"]] = existing_areas[a["name"]]["id"]
                print(f"  Area exists: {a['name']}")
            else:
                r = c.post("/areas", headers=headers, json=a)
                if r.status_code in (200, 201):
                    area_ids[a["name"]] = r.json()["id"]
                    print(f"  Created area: {a['name']}")
                else:
                    print(f"  ERROR creating area {a['name']}: {r.text}", file=sys.stderr)

        # ------------------------------------------------------------------ #
        # Units                                                                #
        # API accepts: area_id, name, slug, description, color, parent_unit_id#
        # ------------------------------------------------------------------ #
        existing_units_raw = c.get("/units", headers=headers).json()
        existing_units = {
            u["name"]: u
            for u in (
                existing_units_raw
                if isinstance(existing_units_raw, list)
                else existing_units_raw.get("items", [])
            )
        }

        pt_id = area_ids.get("Product & Technology")
        fi_id = area_ids.get("Finance & IT")
        comm_id = area_ids.get("Commercial")

        units_data = [
            # Product & Technology
            {"name": "Platform", "slug": "platform", "area_id": pt_id, "color": "#3B82F6"},
            {
                "name": "Application Engineering",
                "slug": "app-engineering",
                "area_id": pt_id,
                "color": "#60A5FA",
            },
            {
                "name": "Product Management",
                "slug": "product-management",
                "area_id": pt_id,
                "color": "#93C5FD",
            },
            # Finance & IT
            {"name": "Group IT", "slug": "group-it", "area_id": fi_id, "color": "#8B5CF6"},
            {
                "name": "Information Security",
                "slug": "infosec",
                "area_id": fi_id,
                "color": "#A78BFA",
            },
            # Commercial
            {"name": "EMEA", "slug": "emea", "area_id": comm_id, "color": "#F59E0B"},
            {"name": "APAC", "slug": "apac", "area_id": comm_id, "color": "#FBB040"},
            {"name": "Americas", "slug": "americas", "area_id": comm_id, "color": "#FCD34D"},
            {"name": "UK & Nordics", "slug": "uk-nordics", "area_id": comm_id, "color": "#FDE68A"},
        ]

        unit_ids = {}
        for u in units_data:
            if not u.get("area_id"):
                print(f"  Skipping unit {u['name']} — parent area missing", file=sys.stderr)
                continue
            if u["name"] in existing_units:
                unit_ids[u["name"]] = existing_units[u["name"]]["id"]
                print(f"  Unit exists: {u['name']}")
            else:
                payload = {k: v for k, v in u.items() if v is not None}
                r = c.post("/units", headers=headers, json=payload)
                if r.status_code in (200, 201):
                    unit_ids[u["name"]] = r.json()["id"]
                    print(f"  Created unit: {u['name']}")
                else:
                    print(f"  ERROR creating unit {u['name']}: {r.text}", file=sys.stderr)

        # ------------------------------------------------------------------ #
        # Teams                                                                #
        # API accepts: name, slug, area_id, unit_id                           #
        # ------------------------------------------------------------------ #
        existing_teams_raw = c.get("/teams", headers=headers).json()
        existing_teams = {
            t["name"]: t
            for t in (
                existing_teams_raw
                if isinstance(existing_teams_raw, list)
                else existing_teams_raw.get("items", [])
            )
        }

        platform_id = unit_ids.get("Platform")

        teams_data = [
            # Platform engineering squads
            {"name": "LIFT", "slug": "lift", "unit_id": platform_id, "area_id": pt_id},
            {
                "name": "Connectivity & Cloud Foundation",
                "slug": "ccf",
                "unit_id": platform_id,
                "area_id": pt_id,
            },
            {"name": "Hosting", "slug": "hosting", "unit_id": platform_id, "area_id": pt_id},
            {
                "name": "Core & Platform",
                "slug": "core-platform",
                "unit_id": platform_id,
                "area_id": pt_id,
            },
            {
                "name": "Connectivity & Platform Services",
                "slug": "cps",
                "unit_id": platform_id,
                "area_id": pt_id,
            },
            {
                "name": "Application",
                "slug": "application",
                "unit_id": platform_id,
                "area_id": pt_id,
            },
            {
                "name": "Release & Adoption",
                "slug": "release-adoption",
                "unit_id": platform_id,
                "area_id": pt_id,
            },
            {
                "name": "Architecture",
                "slug": "architecture",
                "unit_id": platform_id,
                "area_id": pt_id,
            },
        ]

        for t in teams_data:
            if not t.get("unit_id"):
                print(f"  Skipping team {t['name']} — parent unit missing", file=sys.stderr)
                continue
            if t["name"] in existing_teams:
                print(f"  Team exists: {t['name']}")
            else:
                payload = {k: v for k, v in t.items() if v is not None}
                r = c.post("/teams", headers=headers, json=payload)
                if r.status_code in (200, 201):
                    print(f"  Created team: {t['name']}")
                else:
                    print(f"  ERROR creating team {t['name']}: {r.text}", file=sys.stderr)

        print("\nDone.")


if __name__ == "__main__":
    main()
