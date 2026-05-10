'use client';

import { useState, useEffect, useCallback } from 'react';
import { getAdminToken } from '../../../lib/adminAuth';

const ADMIN_API = process.env.NEXT_PUBLIC_ADMIN_API ?? 'http://localhost:8005';

interface Insight {
  id: string;
  generated_at: string | null;
  category: string;
  severity: 'critical' | 'warning' | 'info';
  title: string;
  description: string;
  action: string | null;
  team_name: string | null;
  dismissed: boolean;
  auto_applied: boolean;
  source: string;
}

const SEVERITY_STYLE: Record<string, { bg: string; color: string; label: string }> = {
  critical: { bg: 'rgba(239,62,74,0.1)',  color: '#EF3E4A', label: 'Critical' },
  warning:  { bg: 'rgba(245,158,11,0.1)', color: '#F59E0B', label: 'Warning' },
  info:     { bg: 'rgba(10,123,215,0.1)', color: '#0A7BD7', label: 'Info' },
};

const CATEGORY_ICON: Record<string, string> = {
  cache: '⚡',
  model: '🤖',
  budget: '💰',
  error: '🚨',
  health: '🩺',
  usage: '📊',
};

function InsightCard({ insight, onDismiss }: { insight: Insight; onDismiss: (id: string) => void }) {
  const sty = SEVERITY_STYLE[insight.severity] ?? SEVERITY_STYLE.info;
  const icon = CATEGORY_ICON[insight.category] ?? '✦';
  const ts = insight.generated_at ? new Date(insight.generated_at).toLocaleString() : '';

  return (
    <div style={{
      background: 'var(--side-bg, #1a1f2e)',
      border: `1px solid ${sty.color}33`,
      borderLeft: `3px solid ${sty.color}`,
      borderRadius: 10,
      padding: '14px 18px',
      display: 'flex', gap: 14, alignItems: 'flex-start',
    }}>
      <span style={{ fontSize: 22, flexShrink: 0, marginTop: 1 }}>{icon}</span>
      <div style={{ flex: 1, minWidth: 0 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap', marginBottom: 4 }}>
          <span style={{
            fontSize: 11, fontWeight: 600, padding: '2px 6px',
            borderRadius: 4, background: sty.bg, color: sty.color,
            textTransform: 'uppercase', letterSpacing: '0.04em',
          }}>
            {sty.label}
          </span>
          <span style={{
            fontSize: 11, padding: '2px 6px', borderRadius: 4,
            background: 'rgba(255,255,255,0.06)',
            color: 'var(--side-fg-mute, #8b8fa8)',
            textTransform: 'capitalize',
          }}>
            {insight.category}
          </span>
          {insight.team_name && (
            <span style={{ fontSize: 11, color: 'var(--side-fg-mute, #8b8fa8)' }}>
              · {insight.team_name}
            </span>
          )}
          {insight.auto_applied && (
            <span style={{
              fontSize: 11, padding: '2px 6px', borderRadius: 4,
              background: 'rgba(29,149,142,0.12)', color: '#1D958E',
            }}>
              Auto-applied
            </span>
          )}
          <span style={{ marginLeft: 'auto', fontSize: 11, color: 'var(--side-fg-mute, #8b8fa8)', whiteSpace: 'nowrap' }}>
            {ts}
          </span>
        </div>

        <div style={{ fontWeight: 600, fontSize: 14, color: 'var(--side-fg, #e8eaf0)', marginBottom: 4 }}>
          {insight.title}
        </div>
        <div style={{ fontSize: 13, lineHeight: 1.6, color: 'var(--side-fg-mute, #c8cad8)', marginBottom: insight.action ? 8 : 0 }}>
          {insight.description}
        </div>
        {insight.action && (
          <div style={{
            fontSize: 12.5, padding: '7px 10px',
            background: 'rgba(255,255,255,0.04)',
            borderRadius: 6, color: 'var(--side-fg, #e8eaf0)',
            fontStyle: 'italic',
          }}>
            → {insight.action}
          </div>
        )}
      </div>
      <button
        onClick={() => onDismiss(insight.id)}
        title="Dismiss"
        style={{
          background: 'none', border: 'none', cursor: 'pointer',
          color: 'var(--side-fg-mute, #8b8fa8)', fontSize: 16,
          padding: 4, flexShrink: 0, marginTop: -2,
        }}
      >
        ×
      </button>
    </div>
  );
}

export default function InsightsPage() {
  const [insights, setInsights] = useState<Insight[]>([]);
  const [summary, setSummary] = useState<{ critical: number; warning: number; info: number; last_run: string | null } | null>(null);
  const [loading, setLoading] = useState(true);
  const [triggering, setTriggering] = useState(false);
  const [categoryFilter, setCategoryFilter] = useState('');
  const [severityFilter, setSeverityFilter] = useState('');
  const [error, setError] = useState('');

  const authHeader = () => {
    const t = getAdminToken();
    return t ? { Authorization: `Bearer ${t}` } : {};
  };

  const load = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      const params = new URLSearchParams();
      if (categoryFilter) params.set('category', categoryFilter);
      if (severityFilter) params.set('severity', severityFilter);

      const [insRes, sumRes] = await Promise.all([
        fetch(`${ADMIN_API}/insights?${params}`, { headers: authHeader() }),
        fetch(`${ADMIN_API}/insights/summary`, { headers: authHeader() }),
      ]);

      if (insRes.ok) setInsights(await insRes.json());
      if (sumRes.ok) setSummary(await sumRes.json());
    } catch {
      setError('Failed to load insights');
    } finally {
      setLoading(false);
    }
  }, [categoryFilter, severityFilter]);

  useEffect(() => { load(); }, [load]);

  async function dismiss(id: string) {
    const res = await fetch(`${ADMIN_API}/insights/${id}/dismiss`, {
      method: 'POST', headers: authHeader(),
    });
    if (res.ok) setInsights(prev => prev.filter(i => i.id !== id));
  }

  async function triggerRun() {
    setTriggering(true);
    setError('');
    try {
      const res = await fetch(`${ADMIN_API}/insights/trigger`, {
        method: 'POST', headers: authHeader(),
      });
      if (!res.ok) throw new Error(`${res.status}`);
      await load();
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Unknown error';
      setError(`Run failed: ${msg}`);
    } finally {
      setTriggering(false);
    }
  }

  const critical = insights.filter(i => i.severity === 'critical');
  const warnings = insights.filter(i => i.severity === 'warning');
  const infos    = insights.filter(i => i.severity === 'info');

  return (
    <div style={{ padding: '28px 32px', maxWidth: 900 }}>
      {/* Header */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 16, marginBottom: 24 }}>
        <div>
          <h1 style={{ margin: 0, fontSize: 22, fontWeight: 700, color: 'var(--side-fg, #e8eaf0)' }}>
            AI Insights
          </h1>
          <div style={{ fontSize: 13, color: 'var(--side-fg-mute, #8b8fa8)', marginTop: 3 }}>
            Auto-generated optimization findings · refreshed every 6 hours
            {summary?.last_run && (
              <> · last run {new Date(summary.last_run).toLocaleString()}</>
            )}
          </div>
        </div>
        <button
          onClick={triggerRun}
          disabled={triggering}
          style={{
            marginLeft: 'auto',
            padding: '8px 16px',
            background: 'var(--sc-blue, #0A7BD7)',
            color: '#fff', border: 'none', borderRadius: 8,
            cursor: triggering ? 'not-allowed' : 'pointer',
            fontSize: 13, fontFamily: 'inherit', fontWeight: 500,
            opacity: triggering ? 0.6 : 1,
          }}
        >
          {triggering ? 'Running…' : '▷ Run now'}
        </button>
      </div>

      {/* Summary badges */}
      {summary && (
        <div style={{ display: 'flex', gap: 12, marginBottom: 24 }}>
          {[
            { key: 'critical', label: 'Critical', count: summary.critical, color: '#EF3E4A' },
            { key: 'warning',  label: 'Warnings', count: summary.warning,  color: '#F59E0B' },
            { key: 'info',     label: 'Info',     count: summary.info,     color: '#0A7BD7' },
          ].map(s => (
            <button
              key={s.key}
              onClick={() => setSeverityFilter(severityFilter === s.key ? '' : s.key)}
              style={{
                padding: '8px 16px',
                background: severityFilter === s.key ? `${s.color}22` : 'rgba(255,255,255,0.05)',
                border: `1px solid ${severityFilter === s.key ? s.color : 'rgba(255,255,255,0.1)'}`,
                borderRadius: 8, cursor: 'pointer', fontFamily: 'inherit',
                display: 'flex', gap: 8, alignItems: 'center',
              }}
            >
              <span style={{ fontWeight: 700, fontSize: 18, color: s.color }}>{s.count}</span>
              <span style={{ fontSize: 12, color: 'var(--side-fg-mute, #8b8fa8)' }}>{s.label}</span>
            </button>
          ))}

          <select
            value={categoryFilter}
            onChange={e => setCategoryFilter(e.target.value)}
            style={{
              marginLeft: 'auto',
              padding: '6px 12px', borderRadius: 8,
              background: 'rgba(255,255,255,0.05)',
              border: '1px solid rgba(255,255,255,0.1)',
              color: 'var(--side-fg, #e8eaf0)', fontFamily: 'inherit', fontSize: 13,
              cursor: 'pointer',
            }}
          >
            <option value="">All categories</option>
            {['cache', 'model', 'budget', 'error', 'health', 'usage'].map(c => (
              <option key={c} value={c}>{c.charAt(0).toUpperCase() + c.slice(1)}</option>
            ))}
          </select>
        </div>
      )}

      {error && (
        <div style={{ padding: '10px 14px', background: 'rgba(239,62,74,0.1)', border: '1px solid #EF3E4A', borderRadius: 8, color: '#EF3E4A', fontSize: 13, marginBottom: 16 }}>
          {error}
        </div>
      )}

      {loading ? (
        <div style={{ color: 'var(--side-fg-mute, #8b8fa8)', fontSize: 14 }}>Loading insights…</div>
      ) : insights.length === 0 ? (
        <div style={{ padding: '48px 0', textAlign: 'center', color: 'var(--side-fg-mute, #8b8fa8)' }}>
          <div style={{ fontSize: 32, marginBottom: 12 }}>✦</div>
          <div style={{ fontSize: 15, fontWeight: 500, marginBottom: 8 }}>No insights yet</div>
          <div style={{ fontSize: 13 }}>Click "Run now" to trigger an optimization analysis.</div>
        </div>
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
          {[...critical, ...warnings, ...infos].map(ins => (
            <InsightCard key={ins.id} insight={ins} onDismiss={dismiss} />
          ))}
        </div>
      )}
    </div>
  );
}
