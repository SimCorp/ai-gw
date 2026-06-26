'use client';

import { useQuery } from '@tanstack/react-query';
import Link from 'next/link';
import { Pill } from '@aigw/ui';

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

async function fetchGatusStatuses(): Promise<GatusEndpoint[]> {
  const res = await fetch('/api/v1/endpoints/statuses');
  if (!res.ok) throw new Error(`gatus ${res.status}`);
  return res.json();
}

export function ServiceHealthWidget() {
  const { data, isError, isLoading } = useQuery<GatusEndpoint[]>({
    queryKey: ['gatus-statuses'],
    queryFn: fetchGatusStatuses,
    staleTime: 30_000,
    refetchInterval: 30_000,
    retry: 1,
  });

  if (isLoading) {
    return (
      <div className="card">
        <div className="card__head">
          <h3 className="card__title">Gatus probes</h3>
          <span className="card__sub">loading…</span>
        </div>
      </div>
    );
  }

  if (isError || data === undefined) {
    return (
      <div className="card">
        <div className="card__head">
          <h3 className="card__title">Gatus probes</h3>
          <span className="card__sub">live</span>
          <div className="card__actions">
            <Link href="/status/" className="btn btn--sm btn--ghost">Full view →</Link>
          </div>
        </div>
        <div className="card__body">
          <span className="muted">Health data unavailable</span>
        </div>
      </div>
    );
  }

  const total = data.length;
  const degraded = data.filter(e => !e.results[0]?.success);
  const healthy = total - degraded.length;
  const allOk = degraded.length === 0;

  return (
    <div className="card">
      <div className="card__head">
        <h3 className="card__title">Gatus probes</h3>
        <span className="card__sub">live · {total} endpoints</span>
        <div className="card__actions">
          <Link href="/status/" className="btn btn--sm btn--ghost">Full view →</Link>
        </div>
      </div>
      <div className="card__body" style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          <span className={`statusdot ${allOk ? 'statusdot--good' : 'statusdot--warn'}`} />
          <Pill variant={allOk ? 'good' : 'warn'}>
            {healthy}/{total} healthy
          </Pill>
          {!allOk && (
            <span className="muted" style={{ fontSize: 12 }}>
              {degraded.length} degraded
            </span>
          )}
        </div>
        {degraded.map(e => (
          <div
            key={e.key}
            style={{
              display: 'flex',
              gap: 10,
              padding: '8px 10px',
              border: '1px solid var(--rule)',
              borderRadius: 6,
              background: 'var(--warn-soft)',
              alignItems: 'center',
            }}
          >
            <span className="statusdot statusdot--warn" />
            <span style={{ fontWeight: 600, fontSize: 12.5, flex: 1 }}>{e.name}</span>
            {e.results[0]?.timestamp && (
              <span className="muted mono" style={{ fontSize: 11 }}>
                {new Date(e.results[0].timestamp).toLocaleTimeString('en-GB', {
                  hour: '2-digit',
                  minute: '2-digit',
                  second: '2-digit',
                })}
              </span>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}
