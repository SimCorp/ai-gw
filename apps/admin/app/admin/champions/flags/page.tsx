'use client';

import { useEffect, useState } from 'react';
import { getAdminToken } from '../../../../lib/adminAuth';

const BASE = process.env.NEXT_PUBLIC_ADMIN_API ?? 'http://localhost:8005';

interface Flag {
  id: string;
  contribution_id: string;
  contribution_title: string | null;
  reason: string | null;
  flagged_by: string;
  created_at: string | null;
  status: string;
}

function authHeaders(json = false): HeadersInit {
  const token = getAdminToken();
  const h: Record<string, string> = {};
  if (token) h.Authorization = `Bearer ${token}`;
  if (json) h['Content-Type'] = 'application/json';
  return h;
}

export default function AdminChampionsFlagsPage() {
  const [flags, setFlags] = useState<Flag[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [busyId, setBusyId] = useState<string | null>(null);

  const refresh = async () => {
    setLoading(true);
    try {
      const r = await fetch(`${BASE}/admin/champions/flags`, { headers: authHeaders() });
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      setFlags(await r.json());
    } catch (e) {
      setError(String(e));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    refresh();
  }, []);

  const resolve = async (id: string, action: 'dismiss' | 'remove') => {
    setError(null);
    setBusyId(id);
    try {
      const resp = await fetch(`${BASE}/admin/champions/flags/${id}/resolve`, {
        method: 'POST',
        headers: authHeaders(true),
        body: JSON.stringify({ action }),
      });
      if (!resp.ok) {
        setError(await resp.text());
        return;
      }
      await refresh();
    } catch (e) {
      setError(String(e));
    } finally {
      setBusyId(null);
    }
  };

  return (
    <main className="amain">
      <div className="aheader">
        <div>
          <h1 className="aheader__title">Champions · Flags</h1>
          <p className="aheader__sub">
            Review user-flagged contributions. Dismiss restores the content; Remove tombstones it from the feed.
          </p>
        </div>
      </div>

      {error && (
        <div
          style={{
            color: 'var(--bad, #EF3E4A)',
            fontSize: 12,
            background: 'rgba(239,62,74,0.06)',
            border: '1px solid rgba(239,62,74,0.2)',
            padding: '8px 12px',
            borderRadius: 6,
            marginBottom: 14,
          }}
        >
          {error}
        </div>
      )}

      <div
        style={{
          background: 'var(--surface, #161A33)',
          border: '1px solid var(--side-rule, #232950)',
          borderRadius: 10,
          overflow: 'hidden',
        }}
      >
        <div
          style={{
            padding: '16px 22px',
            borderBottom: '1px solid var(--side-rule)',
            fontSize: 13,
            fontWeight: 600,
            color: 'var(--side-fg)',
          }}
        >
          Open flags
        </div>
        {loading ? (
          <div style={{ padding: 22, color: 'var(--side-fg-mute)', fontSize: 13 }}>Loading…</div>
        ) : flags.length === 0 ? (
          <div style={{ padding: 22, color: 'var(--side-fg-mute)', fontSize: 13 }}>
            No open flags. Nice and quiet.
          </div>
        ) : (
          <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
            <thead>
              <tr style={{ borderBottom: '1px solid var(--side-rule)' }}>
                {['Contribution', 'Reason', 'Flagged by', 'When', ''].map((h) => (
                  <th
                    key={h}
                    style={{
                      padding: '10px 16px',
                      textAlign: 'left',
                      color: 'var(--side-fg-mute)',
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
              {flags.map((f) => (
                <tr key={f.id} style={{ borderBottom: '1px solid var(--side-rule)' }}>
                  <td style={{ padding: '12px 16px', color: 'var(--fg-inv)' }}>
                    <div style={{ fontWeight: 600 }}>{f.contribution_title ?? '—'}</div>
                    <div
                      style={{
                        fontSize: 11,
                        color: 'var(--side-fg-mute)',
                        fontFamily: 'ui-monospace, SFMono-Regular, Menlo, monospace',
                        marginTop: 2,
                      }}
                    >
                      {f.contribution_id.slice(0, 8)}…
                    </div>
                  </td>
                  <td style={{ padding: '12px 16px', color: 'var(--side-fg)', maxWidth: 320 }}>
                    {f.reason ? (
                      <span style={{ whiteSpace: 'pre-wrap' }}>{f.reason}</span>
                    ) : (
                      <span style={{ color: 'var(--side-fg-mute)' }}>(no reason given)</span>
                    )}
                  </td>
                  <td
                    style={{
                      padding: '12px 16px',
                      color: 'var(--side-fg)',
                      fontFamily: 'ui-monospace, SFMono-Regular, Menlo, monospace',
                      fontSize: 12,
                    }}
                  >
                    {f.flagged_by.slice(0, 8)}…
                  </td>
                  <td style={{ padding: '12px 16px', color: 'var(--side-fg-mute)', fontSize: 12 }}>
                    {f.created_at ? new Date(f.created_at).toLocaleString() : '—'}
                  </td>
                  <td style={{ padding: '12px 16px', textAlign: 'right', whiteSpace: 'nowrap' }}>
                    <button
                      onClick={() => resolve(f.id, 'dismiss')}
                      disabled={busyId === f.id}
                      style={{
                        background: 'none',
                        border: '1px solid var(--side-rule, #232950)',
                        borderRadius: 6,
                        color: 'var(--side-fg)',
                        cursor: busyId === f.id ? 'not-allowed' : 'pointer',
                        fontSize: 12,
                        fontFamily: 'inherit',
                        padding: '6px 12px',
                        marginRight: 6,
                        opacity: busyId === f.id ? 0.5 : 1,
                      }}
                    >
                      Dismiss
                    </button>
                    <button
                      onClick={() => resolve(f.id, 'remove')}
                      disabled={busyId === f.id}
                      style={{
                        background: 'none',
                        border: '1px solid var(--side-rule, #232950)',
                        borderRadius: 6,
                        color: 'var(--bad, #EF3E4A)',
                        cursor: busyId === f.id ? 'not-allowed' : 'pointer',
                        fontSize: 12,
                        fontFamily: 'inherit',
                        padding: '6px 12px',
                        opacity: busyId === f.id ? 0.5 : 1,
                      }}
                    >
                      Remove content
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </main>
  );
}
