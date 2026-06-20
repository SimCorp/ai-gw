import { http, HttpResponse } from 'msw';
import {
  TEAMS_DATA, AGENT_PLATFORM_TEAM, POLICIES_DATA, GUARDRAILS_DATA,
  QUOTAS_DATA, APPROVALS_DATA, MODELS_DATA, MCP_DATA, SKILLS_DATA,
  PLUGINS_DATA, CACHE_STATS, CACHE_POLICY, CACHE_TEAM_OVERRIDES,
  CACHE_TOP_PROMPTS, PROVIDERS_DATA, ALERTS_DATA, ALERT_RULES,
  ALERT_CHANNELS, AUDIT_DATA, generateRequests,
} from './data';

const BASE = '/api/v1';

export const handlers = [
  http.get(`${BASE}/teams`, () => HttpResponse.json(TEAMS_DATA)),
  http.get(`${BASE}/teams/:id`, ({ params }) => {
    const team = TEAMS_DATA.find(t => t.id === params.id) ?? AGENT_PLATFORM_TEAM;
    return HttpResponse.json(team);
  }),
  http.get(`${BASE}/teams/:id/detail`, () => HttpResponse.json(AGENT_PLATFORM_TEAM)),

  http.get(`${BASE}/policies`, () => HttpResponse.json(POLICIES_DATA)),
  http.get(`${BASE}/guardrails`, () => HttpResponse.json(GUARDRAILS_DATA)),
  http.get(`${BASE}/quotas`, () => HttpResponse.json(QUOTAS_DATA)),
  http.get(`${BASE}/approvals`, () => HttpResponse.json(APPROVALS_DATA)),

  http.get(`${BASE}/models`, () => HttpResponse.json(MODELS_DATA)),
  http.get(`${BASE}/mcp/servers`, () => HttpResponse.json(MCP_DATA)),
  http.get(`${BASE}/skills`, () => HttpResponse.json(SKILLS_DATA)),
  http.get(`${BASE}/plugins`, () => HttpResponse.json(PLUGINS_DATA)),

  http.get(`${BASE}/cache`, () => HttpResponse.json({
    stats: CACHE_STATS,
    policy: CACHE_POLICY,
    teamOverrides: CACHE_TEAM_OVERRIDES,
    topPrompts: CACHE_TOP_PROMPTS,
  })),

  http.get(`${BASE}/providers`, () => HttpResponse.json(PROVIDERS_DATA)),

  http.get(`${BASE}/alerts`, () => HttpResponse.json({
    alerts: ALERTS_DATA,
    rules: ALERT_RULES,
    channels: ALERT_CHANNELS,
  })),

  http.get(`${BASE}/audit`, () => HttpResponse.json({
    events: AUDIT_DATA,
    total: 14208,
    page: 1,
    totalPages: 1184,
  })),

  http.get(`${BASE}/requests`, () => HttpResponse.json(generateRequests())),

  // Dashboard summary
  http.get(`${BASE}/dashboard`, () => HttpResponse.json({
    totalSpend: '$3,847.21',
    cacheSavings: '$1,209.45',
    requests: '2.41M',
    p99Latency: '38ms',
    cacheHitRate: '31.4%',
    activeKeys: 487,
    errorRate: '0.21%',
    tokensIn: '412M',
    tokensOut: '188M',
  })),

  // SSE endpoint for live requests
  http.get(`${BASE}/requests/stream`, () => {
    const rows = generateRequests();
    const encoder = new TextEncoder();
    const stream = new ReadableStream({
      start(controller) {
        let i = 0;
        const timer = setInterval(() => {
          if (i >= rows.length) {
            clearInterval(timer);
            controller.close();
            return;
          }
          controller.enqueue(encoder.encode(`data: ${JSON.stringify(rows[i])}\n\n`));
          i++;
        }, 400);
      },
    });
    return new Response(stream, {
      headers: {
        'Content-Type': 'text/event-stream',
        'Cache-Control': 'no-cache',
      },
    });
  }),

  // Mutations (no-op 200)
  http.post(`${BASE}/approvals/:id/approve`, () => HttpResponse.json({ ok: true })),
  http.post(`${BASE}/approvals/:id/deny`, () => HttpResponse.json({ ok: true })),
  http.post(`${BASE}/teams`, () => HttpResponse.json({ ok: true })),
  http.post(`${BASE}/teams/:id/keys`, () => HttpResponse.json({ ok: true })),
];
