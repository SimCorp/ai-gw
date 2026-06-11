'use client';

import { useEffect, useState } from 'react';
import { getAdminToken } from '../../../../lib/adminAuth';

const BASE = process.env.NEXT_PUBLIC_ADMIN_API ?? 'http://localhost:8005';

interface OrgStats {
  active_champions: number;
  contributions_total: number;
  contributions_30d: number;
  asks_open: number;
  asks_resolved_30d: number;
  bookings_done_30d: number;
}

interface PerChampion {
  developer_id: string;
  contributions: number;
  asks_resolved: number;
  bookings_done: number;
  points_30d: number;
}

interface ActivityData {
  org: OrgStats;
  per_champion: PerChampion[];
}

const KPI_LABELS: Array<{ key: keyof OrgStats; label: string }> = [
  { key: 'active_champions', label: 'Active champions' },
  { key: 'contributions_total', label: 'Contributions (all-time)' },
  { key: 'contributions_30d', label: 'Contributions (30d)' },
  { key: 'asks_open', label: 'Open asks' },
  { key: 'asks_resolved_30d', label: 'Asks resolved (30d)' },
  { key: 'bookings_done_30d', label: 'Bookings done (30d)' },
];

export default function ChampionsActivityPage() {
  const [data, setData] = useState<ActivityData | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const token = getAdminToken();
    fetch(`${BASE}/admin/champions/activity`, {
      headers: token ? { Authorization: `Bearer ${token}` } : {},
    })
      .then((r) => (r.ok ? r.json() : Promise.reject(`HTTP ${r.status}`)))
      .then((d: ActivityData) => setData(d))
      .catch((e) => setError(String(e)))
      .finally(() => setLoading(false));
  }, []);

  const sorted = (data?.per_champion ?? []).slice().sort((a, b) => b.points_30d - a.points_30d);

  return (
    <main className="amain">
      <div className="aheader">
        <div>
          <h1 className="aheader__title">Champions activity</h1>
          <p className="aheader__sub">Organisation-wide and per-champion contribution metrics</p>
        </div>
      </div>

      {loading && (
        <div style={{ color: 'var(--panel-fg-mute)', fontSize: 13 }}>Loading…</div>
      )}
      {error && (
        <div style={{ color: 'var(--bad)', fontSize: 13, marginBottom: 16 }}>{error}</div>
      )}

      {data && (
        <>
          {/* Org KPIs */}
          <div
            style={{
              display: 'grid',
              gridTemplateColumns: 'repeat(auto-fill, minmax(180px, 1fr))',
              gap: 12,
              marginBottom: 24,
            }}
          >
            {KPI_LABELS.map(({ key, label }) => (
              <div
                key={key}
                style={{
                  background: 'var(--surface-2)',
                  border: '1px solid var(--panel-rule)',
                  borderRadius: 10,
                  padding: '16px 18px',
                }}
              >
                <div className="microlabel" style={{ marginBottom: 6 }}>
                  {label}
                </div>
                <div style={{ fontSize: 22, fontWeight: 700, color: 'var(--fg-1)' }}>
                  {data.org[key]}
                </div>
              </div>
            ))}
          </div>

          {/* Per-champion table */}
          <div
            style={{
              background: 'var(--surface-2)',
              border: '1px solid var(--panel-rule)',
              borderRadius: 10,
              overflow: 'hidden',
            }}
          >
            <div
              style={{
                padding: '16px 22px',
                borderBottom: '1px solid var(--panel-rule)',
                fontSize: 13,
                fontWeight: 600,
                color: 'var(--panel-fg)',
              }}
            >
              Per champion (last 30 days)
            </div>
            {sorted.length === 0 ? (
              <div style={{ padding: 22, color: 'var(--panel-fg-mute)', fontSize: 13 }}>
                No champion activity yet.
              </div>
            ) : (
              <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
                <thead>
                  <tr style={{ borderBottom: '1px solid var(--panel-rule)' }}>
                    {['Developer', 'Contributions', 'Asks resolved', 'Bookings done', 'Points (30d)'].map((h) => (
                      <th
                        key={h}
                        style={{
                          padding: '10px 16px',
                          textAlign: 'left',
                          color: 'var(--panel-fg-mute)',
                          fontWeight: 500,
                          fontSize: 12,
                        }}
                      >
                        {h}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {sorted.map((c) => (
                    <tr key={c.developer_id} style={{ borderBottom: '1px solid var(--panel-rule)' }}>
                      <td
                        style={{
                          padding: '12px 16px',
                          color: 'var(--fg-1)',
                          fontFamily: 'ui-monospace, SFMono-Regular, Menlo, monospace',
                        }}
                      >
                        {c.developer_id.slice(0, 8)}…
                      </td>
                      <td className="num" style={{ padding: '12px 16px', color: 'var(--panel-fg)' }}>{c.contributions}</td>
                      <td className="num" style={{ padding: '12px 16px', color: 'var(--panel-fg)' }}>{c.asks_resolved}</td>
                      <td className="num" style={{ padding: '12px 16px', color: 'var(--panel-fg)' }}>{c.bookings_done}</td>
                      <td className="num" style={{ padding: '12px 16px', color: 'var(--fg-1)', fontWeight: 600 }}>
                        {c.points_30d}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>
        </>
      )}
    </main>
  );
}
