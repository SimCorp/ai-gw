import { http, HttpResponse } from "msw";

/**
 * Dev-only handlers for mock mode (NEXT_PUBLIC_USE_MOCKS=1).
 * Wildcard origins so they match whatever NEXT_PUBLIC_*_BASE_URL is set to.
 * Extend per flow as pages are verified.
 */

const DEVELOPER = {
  developer_id: "01900000-0000-7000-a000-000000000001",
  email: "dev@simcorp.com",
  display_name: "Mock Developer",
  team_id: "01900000-0000-7000-b000-000000000001",
  team_name: "Developer Experience",
};

const MEMBERSHIPS = [
  {
    membership_id: "01900000-0000-7000-c000-000000000001",
    role: "admin",
    joined_at: "2026-01-15T09:00:00Z",
    team_id: "01900000-0000-7000-b000-000000000001",
    team_name: "Developer Experience",
    team_slug: "devex",
    area_name: "Platform",
    area_color: "#6366F1",
  },
  {
    membership_id: "01900000-0000-7000-c000-000000000002",
    role: "member",
    joined_at: "2026-03-02T09:00:00Z",
    team_id: "01900000-0000-7000-b000-000000000005",
    team_name: "Agent Platform",
    team_slug: "agent-platform",
    area_name: "Platform",
    area_color: "#D946EF",
  },
];

export const handlers = [
  http.get("*/dev-auth/me", () => HttpResponse.json(DEVELOPER)),
  http.post("*/dev-auth/login", () =>
    HttpResponse.json({ token: "mock-dev-token", developer: DEVELOPER }),
  ),
  http.post("*/dev-auth/logout", () => HttpResponse.json({ ok: true })),
  http.get("*/developers/:id/teams", () => HttpResponse.json(MEMBERSHIPS)),
];
