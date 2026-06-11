'use client';

import { useState, useEffect } from 'react';
import { getAdminToken } from '../../../lib/adminAuth';

const BASE = process.env.NEXT_PUBLIC_ADMIN_API ?? 'http://localhost:8005';

interface OrgWeek {
  week: string;
  total_sessions: number;
  agentic_sessions: number;
  active_devs: number;
  agentic_devs: number;
  agentic_pct: number;
}

interface TeamRow {
  team_id: string;
  team_name: string;
  dev_count: number;
  agentic_devs_30d: number;
  agentic_session_pct_30d: number;
  laggard: boolean;
}

interface DevRow {
  developer_id: string;
  email: string;
  display_name: string;
  team_id: string | null;
  team_name: string | null;
  total_sessions_30d: number;
  agentic_sessions_30d: number;
  agentic_pct: number;
  achievement_count: number;
}

interface TransformData {
  org_weekly: OrgWeek[];
  teams: TeamRow[];
  developers: DevRow[];
}

function OrgChart({ data }: { data: OrgWeek[] }) {
  if (!data.length) return <div style={{ color: 'var(--panel-fg-mute)', fontSize: 13 }}>No session data yet.</div>;
  const max = Math.max(...data.map(w => w.total_sessions), 1);
  return (
    <div style={{ display: 'flex', alignItems: 'flex-end', gap: 3, height: 80 }}>
      {data.map(w => (
        <div key={w.week}
          title={`Week of ${w.week}: ${w.agentic_pct}% agentic, ${w.agentic_devs}/${w.active_devs} devs`}
          style={{ flex: 1, display: 'flex', flexDirection: 'column', alignItems: 'center' }}>
          <div style={{ width: '100%', height: 72, display: 'flex', flexDirection: 'column', justifyContent: 'flex-end' }}>
            <div style={{
              width: '100%',
              height: `${(w.total_sessions / max) * 68}px`,
              background: 'var(--panel-rule)',
              borderRadius: '3px 3px 0 0',
              position: 'relative', overflow: 'hidden',
            }}>
              <div style={{
                position: 'absolute', bottom: 0, left: 0, right: 0,
                height: `${w.agentic_pct}%`,
                background: 'var(--accent)',
              }} />
            </div>
          </div>
          <div style={{ fontSize: 9, color: 'var(--panel-fg-mute)', whiteSpace: 'nowrap', marginTop: 2 }}>
            {w.week.slice(5)}
          </div>
        </div>
      ))}
    </div>
  );
}

function pctBar(pct: number, laggard: boolean) {
  const color = laggard ? 'var(--bad)' : pct >= 60 ? 'var(--good)' : 'var(--accent)';
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
      <div style={{ flex: 1, height: 6, background: 'var(--panel-rule)', borderRadius: 3, overflow: 'hidden' }}>
        <div style={{ width: `${pct}%`, height: '100%', background: color, borderRadius: 3 }} />
      </div>
      <span style={{ fontSize: 12, color: 'var(--panel-fg)', minWidth: 36, textAlign: 'right' }}>{pct}%</span>
    </div>
  );
}

export default function TransformationPage() {
  const [data, setData] = useState<TransformData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [classifying, setClassifying] = useState(false);
  const [expandTeam, setExpandTeam] = useState<string | null>(null);

  useEffect(() => {
    const token = getAdminToken();
    fetch(`${BASE}/admin/transformation`, {
      headers: token ? { Authorization: `Bearer ${token}` } : {},
    })
      .then(r => r.ok ? r.json() : Promise.reject(`HTTP ${r.status}`))
      .then(setData)
      .catch(e => setError(String(e)))
      .finally(() => setLoading(false));
  }, []);

  async function runClassifier() {
    const token = getAdminToken();
    setClassifying(true);
    try {
      const res = await fetch(`${BASE}/admin/transformation/classify`, {
        method: 'POST',
        headers: token ? { Authorization: `Bearer ${token}` } : {},
      });
      const result = await res.json();
      alert(`Classified ${result.sessions_classified} sessions. Achievements awarded: ${JSON.stringify(result.achievements_awarded)}`);
      window.location.reload();
    } finally {
      setClassifying(false);
    }
  }

  if (loading) return <main className="amain"><div style={{ color: 'var(--panel-fg-mute)', padding: 32 }}>Loading…</div></main>;
  if (error) return <main className="amain"><div style={{ color: 'var(--bad)', padding: 32 }}>Error: {error}</div></main>;
  if (!data) return null;

  const latestWeek = data.org_weekly[data.org_weekly.length - 1];
  const totalDevs = data.developers.length;
  const agenticDevs = data.developers.filter(d => d.agentic_pct >= 50).length;
  const laggardTeams = data.teams.filter(t => t.laggard).length;

  return (
    <main className="amain">
      <div className="aheader">
        <div>
          <h1 className="aheader__title">AI Transformation</h1>
          <p className="aheader__sub">Organisation-wide agentic adoption — last 30 days</p>
        </div>
        <button
          onClick={runClassifier}
          disabled={classifying}
          className="btn btn--primary"
          style={{ fontSize: 13 }}
        >
          {classifying ? 'Running…' : 'Run classifier now'}
        </button>
      </div>

      {/* Org summary cards */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(160px, 1fr))', gap: 12, marginBottom: 24 }}>
        {[
          { label: 'Agentic adoption', value: latestWeek ? `${latestWeek.agentic_pct}%` : '—', sub: 'sessions this week' },
          { label: 'Agentic developers', value: `${agenticDevs}`, sub: `of ${totalDevs} active devs` },
          { label: 'Laggard teams', value: `${laggardTeams}`, sub: '<20% agentic sessions', warn: laggardTeams > 0 },
          { label: 'Active this week', value: latestWeek ? String(latestWeek.active_devs) : '—', sub: 'developers' },
        ].map(c => (
          <div key={c.label} style={{
            background: 'var(--surface-2)',
            border: `1px solid ${c.warn ? 'var(--bad)' : 'var(--panel-rule)'}`,
            borderRadius: 10, padding: '16px 18px',
          }}>
            <div style={{ fontSize: 12, color: 'var(--panel-fg-mute)', marginBottom: 4 }}>{c.label}</div>
            <div style={{ fontSize: 24, fontWeight: 700, color: c.warn ? 'var(--bad)' : 'var(--fg-1)' }}>{c.value}</div>
            <div style={{ fontSize: 11, color: 'var(--panel-fg-mute)', marginTop: 2 }}>{c.sub}</div>
          </div>
        ))}
      </div>

      {/* Org adoption chart */}
      <div style={{
        background: 'var(--surface-2)',
        border: '1px solid var(--panel-rule)',
        borderRadius: 10, padding: '18px 22px', marginBottom: 24,
      }}>
        <div style={{ fontSize: 13, fontWeight: 600, color: 'var(--panel-fg)', marginBottom: 14 }}>
          Organisation adoption over time
          <span style={{ fontSize: 11, color: 'var(--panel-fg-mute)', fontWeight: 400, marginLeft: 8 }}>blue = agentic sessions</span>
        </div>
        <OrgChart data={data.org_weekly} />
      </div>

      {/* Teams table */}
      <div style={{
        background: 'var(--surface-2)',
        border: '1px solid var(--panel-rule)',
        borderRadius: 10, marginBottom: 24, overflow: 'hidden',
      }}>
        <div style={{ padding: '16px 22px', borderBottom: '1px solid var(--panel-rule)', fontSize: 13, fontWeight: 600, color: 'var(--panel-fg)' }}>
          Teams
        </div>
        <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
          <thead>
            <tr style={{ borderBottom: '1px solid var(--panel-rule)' }}>
              {['Team', 'Developers', 'Agentic devs (30d)', 'Agentic session %', 'Status', ''].map(h => (
                <th key={h} style={{ padding: '10px 16px', textAlign: 'left', color: 'var(--panel-fg-mute)', fontWeight: 500, fontSize: 12 }}>{h}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {data.teams.map(t => (
              <>
                <tr key={t.team_id} style={{ borderBottom: '1px solid var(--panel-rule)' }}>
                  <td style={{ padding: '12px 16px', color: 'var(--fg-1)', fontWeight: 500 }}>{t.team_name ?? '—'}</td>
                  <td className="num" style={{ padding: '12px 16px', color: 'var(--panel-fg)' }}>{t.dev_count}</td>
                  <td className="num" style={{ padding: '12px 16px', color: 'var(--panel-fg)' }}>{t.agentic_devs_30d}</td>
                  <td style={{ padding: '12px 16px', minWidth: 160 }}>{pctBar(t.agentic_session_pct_30d, t.laggard)}</td>
                  <td style={{ padding: '12px 16px' }}>
                    {t.laggard
                      ? <span className="pill pill--bad"><span className="dot" />Laggard</span>
                      : t.agentic_session_pct_30d >= 60
                        ? <span className="pill pill--good"><span className="dot" />Advanced</span>
                        : <span className="pill pill--warn"><span className="dot" />Transitioning</span>}
                  </td>
                  <td style={{ padding: '12px 16px' }}>
                    <button
                      onClick={() => setExpandTeam(expandTeam === t.team_id ? null : t.team_id)}
                      style={{ background: 'none', border: 0, color: 'var(--accent-text)', cursor: 'pointer', fontSize: 12, fontFamily: 'inherit' }}
                    >
                      {expandTeam === t.team_id ? 'Hide' : 'Show developers'}
                    </button>
                  </td>
                </tr>
                {expandTeam === t.team_id && (
                  <tr key={`${t.team_id}-devs`}>
                    <td colSpan={6} style={{ padding: '0 16px 12px 32px', background: 'var(--surface-soft)' }}>
                      <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 12 }}>
                        <thead>
                          <tr>
                            {['Developer', 'Sessions (30d)', 'Agentic', 'Agentic %', 'Achievements'].map(h => (
                              <th key={h} style={{ padding: '8px 12px', textAlign: 'left', color: 'var(--panel-fg-mute)', fontWeight: 500 }}>{h}</th>
                            ))}
                          </tr>
                        </thead>
                        <tbody>
                          {data.developers.filter(d => d.team_id === t.team_id).map(d => (
                            <tr key={d.developer_id}>
                              <td style={{ padding: '8px 12px', color: 'var(--panel-fg)' }}>
                                <div style={{ fontWeight: 500, color: 'var(--fg-1)' }}>{d.display_name}</div>
                                <div style={{ color: 'var(--panel-fg-mute)', fontSize: 11 }}>{d.email}</div>
                              </td>
                              <td className="num" style={{ padding: '8px 12px', color: 'var(--panel-fg)' }}>{d.total_sessions_30d}</td>
                              <td className="num" style={{ padding: '8px 12px', color: 'var(--panel-fg)' }}>{d.agentic_sessions_30d}</td>
                              <td style={{ padding: '8px 12px' }}>{pctBar(d.agentic_pct, d.agentic_pct < 20 && d.total_sessions_30d > 5)}</td>
                              <td className="num" style={{ padding: '8px 12px', color: 'var(--panel-fg-mute)' }}>{d.achievement_count} 🏅</td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </td>
                  </tr>
                )}
              </>
            ))}
          </tbody>
        </table>
      </div>
    </main>
  );
}
