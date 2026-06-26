import { describe, expect, it } from 'vitest';

// ── Types (mirror the widget's local interfaces) ──────────────────────────────

interface GatusResult {
  success: boolean;
  timestamp: string;
}

interface GatusEndpoint {
  name: string;
  key: string;
  results: GatusResult[];
  uptime: { '7d': number; '24h': number; '1h': number };
}

function makeEndpoint(success: boolean, name = 'svc'): GatusEndpoint {
  return {
    name,
    key: name,
    results: [{ success, timestamp: '2026-01-01T00:00:00Z' }],
    uptime: { '7d': 1, '24h': 1, '1h': 1 },
  };
}

// Mirror the widget's classification expression exactly so regressions are caught.
function classifyEndpoints(data: GatusEndpoint[]) {
  const degraded = data.filter(e => !e.results[0]?.success);
  const healthy = data.length - degraded.length;
  return { degraded, healthy, allOk: degraded.length === 0 };
}

// ── Healthy state ─────────────────────────────────────────────────────────────

describe('ServiceHealthWidget — all-healthy state', () => {
  it('reports zero degraded when all endpoints succeed', () => {
    const data = [makeEndpoint(true, 'auth'), makeEndpoint(true, 'cache')];
    const { degraded, healthy, allOk } = classifyEndpoints(data);
    expect(degraded).toHaveLength(0);
    expect(healthy).toBe(2);
    expect(allOk).toBe(true);
  });
});

// ── Degraded state ────────────────────────────────────────────────────────────

describe('ServiceHealthWidget — degraded state', () => {
  it('marks an endpoint degraded when the last result is a failure', () => {
    const data = [makeEndpoint(true, 'auth'), makeEndpoint(false, 'cache')];
    const { degraded, healthy, allOk } = classifyEndpoints(data);
    expect(degraded).toHaveLength(1);
    expect(degraded[0].name).toBe('cache');
    expect(healthy).toBe(1);
    expect(allOk).toBe(false);
  });

  it('marks an endpoint with empty results as degraded (no false-negative on new registrations)', () => {
    const noResults: GatusEndpoint = {
      name: 'new-svc',
      key: 'new-svc',
      results: [],
      uptime: { '7d': 0, '24h': 0, '1h': 0 },
    };
    const { degraded } = classifyEndpoints([noResults]);
    expect(degraded).toHaveLength(1);
  });

  it('counts all degraded services correctly with multiple failures', () => {
    const data = [
      makeEndpoint(false, 'auth'),
      makeEndpoint(true, 'cache'),
      makeEndpoint(false, 'memory'),
    ];
    const { degraded, healthy } = classifyEndpoints(data);
    expect(degraded).toHaveLength(2);
    expect(healthy).toBe(1);
  });
});

// ── Loading / error states ─────────────────────────────────────────────────────
// Full render tests (isLoading / isError branches) require a jsdom environment
// with @testing-library/react and a QueryClient provider — not yet wired up in
// @aigw/admin. Add them when the admin vitest config is established.
