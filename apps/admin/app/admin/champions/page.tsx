'use client';

import { useEffect, useState } from 'react';
import { getAdminToken } from '../../../lib/adminAuth';

const BASE = process.env.NEXT_PUBLIC_ADMIN_API ?? 'http://localhost:8005';

interface Champion {
  developer_id: string;
  bio: string | null;
  focus_areas: string[];
  active: boolean;
}

function authHeaders(json = false): HeadersInit {
  const token = getAdminToken();
  const h: Record<string, string> = {};
  if (token) h.Authorization = `Bearer ${token}`;
  if (json) h['Content-Type'] = 'application/json';
  return h;
}

export default function AdminChampionsPage() {
  const [list, setList] = useState<Champion[]>([]);
  const [devId, setDevId] = useState('');
  const [bio, setBio] = useState('');
  const [focus, setFocus] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);

  const refresh = async () => {
    try {
      const r = await fetch(`${BASE}/champions`);
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      setList(await r.json());
    } catch (e) {
      setError(String(e));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    refresh();
  }, []);

  const nominate = async () => {
    setError(null);
    setSubmitting(true);
    try {
      const resp = await fetch(`${BASE}/admin/champions`, {
        method: 'POST',
        headers: authHeaders(true),
        body: JSON.stringify({
          developer_id: devId,
          bio: bio || null,
          focus_areas: focus
            .split(',')
            .map((s) => s.trim())
            .filter(Boolean),
        }),
      });
      if (!resp.ok) {
        setError(await resp.text());
        return;
      }
      setDevId('');
      setBio('');
      setFocus('');
      await refresh();
    } catch (e) {
      setError(String(e));
    } finally {
      setSubmitting(false);
    }
  };

  const retire = async (id: string) => {
    setError(null);
    try {
      const resp = await fetch(`${BASE}/admin/champions/${id}`, {
        method: 'DELETE',
        headers: authHeaders(),
      });
      if (!resp.ok) {
        setError(await resp.text());
        return;
      }
      await refresh();
    } catch (e) {
      setError(String(e));
    }
  };

  const inputStyle: React.CSSProperties = {
    background: 'var(--surface, #161A33)',
    border: '1px solid var(--side-rule, #232950)',
    borderRadius: 6,
    color: 'var(--fg-inv, #fff)',
    padding: '8px 10px',
    fontSize: 13,
    fontFamily: 'inherit',
  };

  return (
    <main className="amain">
      <div className="aheader">
        <div>
          <h1 className="aheader__title">AI Champions</h1>
          <p className="aheader__sub">Nominate and retire AI Champions across the organisation</p>
        </div>
      </div>

      {/* Nominate form */}
      <div
        style={{
          background: 'var(--surface, #161A33)',
          border: '1px solid var(--side-rule, #232950)',
          borderRadius: 10,
          padding: '18px 22px',
          marginBottom: 24,
        }}
      >
        <div style={{ fontSize: 13, fontWeight: 600, color: 'var(--side-fg)', marginBottom: 14 }}>
          Nominate a champion
        </div>
        <div
          style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))',
            gap: 10,
          }}
        >
          <input
            value={devId}
            onChange={(e) => setDevId(e.target.value)}
            placeholder="Developer UUID"
            style={inputStyle}
          />
          <input
            value={bio}
            onChange={(e) => setBio(e.target.value)}
            placeholder="Bio"
            style={inputStyle}
          />
          <input
            value={focus}
            onChange={(e) => setFocus(e.target.value)}
            placeholder="Focus areas (comma-separated)"
            style={inputStyle}
          />
        </div>
        {error && (
          <div style={{ color: 'var(--bad, #EF3E4A)', fontSize: 12, marginTop: 10 }}>{error}</div>
        )}
        <button
          onClick={nominate}
          disabled={!devId || submitting}
          className="btn btn--primary"
          style={{ fontSize: 13, marginTop: 12 }}
        >
          {submitting ? 'Nominating…' : 'Nominate'}
        </button>
      </div>

      {/* Active champions table */}
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
          Active champions
        </div>
        {loading ? (
          <div style={{ padding: 22, color: 'var(--side-fg-mute)', fontSize: 13 }}>Loading…</div>
        ) : list.length === 0 ? (
          <div style={{ padding: 22, color: 'var(--side-fg-mute)', fontSize: 13 }}>
            No champions yet.
          </div>
        ) : (
          <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
            <thead>
              <tr style={{ borderBottom: '1px solid var(--side-rule)' }}>
                {['Developer', 'Bio', 'Focus areas', ''].map((h) => (
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
              {list.map((c) => (
                <tr key={c.developer_id} style={{ borderBottom: '1px solid var(--side-rule)' }}>
                  <td
                    style={{
                      padding: '12px 16px',
                      color: 'var(--fg-inv)',
                      fontFamily: 'ui-monospace, SFMono-Regular, Menlo, monospace',
                    }}
                  >
                    {c.developer_id.slice(0, 8)}…
                  </td>
                  <td style={{ padding: '12px 16px', color: 'var(--side-fg)' }}>{c.bio ?? '—'}</td>
                  <td style={{ padding: '12px 16px', color: 'var(--side-fg)' }}>
                    {c.focus_areas.join(', ') || '—'}
                  </td>
                  <td style={{ padding: '12px 16px', textAlign: 'right' }}>
                    <button
                      onClick={() => retire(c.developer_id)}
                      style={{
                        background: 'none',
                        border: '1px solid var(--side-rule, #232950)',
                        borderRadius: 6,
                        color: 'var(--bad, #EF3E4A)',
                        cursor: 'pointer',
                        fontSize: 12,
                        fontFamily: 'inherit',
                        padding: '6px 12px',
                      }}
                    >
                      Retire
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
