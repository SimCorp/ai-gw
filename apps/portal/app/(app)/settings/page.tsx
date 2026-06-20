'use client';

import { useState } from 'react';
import { useAuth } from '../_lib/authContext';

const ADMIN_BASE = process.env.NEXT_PUBLIC_ADMIN_BASE_URL ?? 'http://localhost:8005';

export default function SettingsPage() {
  const { developer, token, setDeveloper, logout } = useAuth();

  const [displayName, setDisplayName] = useState(developer?.display_name ?? '');
  const [saving, setSaving] = useState(false);
  const [savedMsg, setSavedMsg] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  if (!developer) return null;

  const handleSave = async () => {
    if (!displayName.trim()) return;
    setSaving(true);
    setError(null);
    setSavedMsg(null);
    try {
      const res = await fetch(`${ADMIN_BASE}/dev-auth/profile`, {
        method: 'PATCH',
        headers: {
          'Content-Type': 'application/json',
          ...(token ? { Authorization: `Bearer ${token}` } : {}),
        },
        body: JSON.stringify({ display_name: displayName.trim() }),
      });
      if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        throw new Error(body.detail ?? `Save failed (${res.status})`);
      }
      const updated = await res.json();
      setDeveloper(updated);
      setSavedMsg('Saved.');
      setTimeout(() => setSavedMsg(null), 3000);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setSaving(false);
    }
  };

  return (
    <main className="pmain">
      <div className="phero">
        <div>
          <h1>Settings</h1>
          <p>Manage your profile and account preferences.</p>
        </div>
      </div>

      {/* Profile */}
      <section style={{ maxWidth: 560 }}>
        <h2 style={{ fontSize: 15, fontWeight: 600, marginBottom: 16 }}>Profile</h2>
        <div className="card">
          <div className="card__body" style={{ padding: '20px 24px', display: 'flex', flexDirection: 'column', gap: 18 }}>

            <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
              <label style={{ fontSize: 12.5, fontWeight: 500, color: 'var(--fg-2)' }}>
                Email
              </label>
              <div style={{
                padding: '8px 12px',
                border: '1px solid var(--rule)',
                borderRadius: 7,
                background: 'var(--surface-soft)',
                fontSize: 13,
                color: 'var(--fg-2)',
                fontFamily: 'var(--font-mono)',
              }}>
                {developer.email}
              </div>
              <div style={{ fontSize: 11.5, color: 'var(--fg-3)' }}>Email cannot be changed after registration.</div>
            </div>

            <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
              <label htmlFor="display-name" style={{ fontSize: 12.5, fontWeight: 500, color: 'var(--fg-2)' }}>
                Display name
              </label>
              <input
                id="display-name"
                type="text"
                value={displayName}
                onChange={e => setDisplayName(e.target.value)}
                onKeyDown={e => { if (e.key === 'Enter') handleSave(); }}
                placeholder="Your name"
                style={{
                  padding: '8px 12px',
                  border: '1px solid var(--rule)',
                  borderRadius: 7,
                  background: 'var(--surface)',
                  fontSize: 13,
                  color: 'var(--fg-1)',
                  fontFamily: 'inherit',
                  outline: 'none',
                  width: '100%',
                  boxSizing: 'border-box',
                }}
              />
            </div>

            {error && (
              <div style={{ fontSize: 12.5, color: 'var(--bad)', padding: '8px 12px', background: 'var(--bad-soft)', borderRadius: 6 }}>
                {error}
              </div>
            )}

            <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
              <button
                className="btn btn--primary"
                onClick={handleSave}
                disabled={saving || !displayName.trim() || displayName.trim() === developer.display_name}
              >
                {saving ? 'Saving…' : 'Save changes'}
              </button>
              {savedMsg && (
                <span style={{ fontSize: 12.5, color: 'var(--good)' }}>{savedMsg}</span>
              )}
            </div>
          </div>
        </div>
      </section>

      {/* Account info */}
      <section style={{ maxWidth: 560, marginTop: 28 }}>
        <h2 style={{ fontSize: 15, fontWeight: 600, marginBottom: 16 }}>Account</h2>
        <div className="card">
          <div className="card__body" style={{ padding: 0 }}>
            <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
              <tbody>
                <tr style={{ borderBottom: '1px solid var(--rule)' }}>
                  <td style={{ padding: '12px 20px', color: 'var(--fg-2)', width: '40%' }}>Developer ID</td>
                  <td style={{ padding: '12px 20px', fontFamily: 'var(--font-mono)', fontSize: 12, color: 'var(--fg-1)' }}>
                    {developer.developer_id}
                  </td>
                </tr>
                <tr style={{ borderBottom: '1px solid var(--rule)' }}>
                  <td style={{ padding: '12px 20px', color: 'var(--fg-2)' }}>Active team</td>
                  <td style={{ padding: '12px 20px', color: 'var(--fg-1)' }}>
                    {developer.team_name ?? <span style={{ color: 'var(--fg-3)' }}>None — use team picker in sidebar</span>}
                  </td>
                </tr>
                <tr>
                  <td style={{ padding: '12px 20px', color: 'var(--fg-2)' }}>API base URL</td>
                  <td style={{ padding: '12px 20px', fontFamily: 'var(--font-mono)', fontSize: 12, color: 'var(--fg-1)' }}>
                    {process.env.NEXT_PUBLIC_CACHE_BASE_URL ?? 'http://localhost:8002'}/v1
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
        </div>
      </section>

      {/* Danger zone */}
      <section style={{ maxWidth: 560, marginTop: 28 }}>
        <h2 style={{ fontSize: 15, fontWeight: 600, marginBottom: 16, color: 'var(--bad)' }}>Sign out</h2>
        <div className="card">
          <div className="card__body" style={{ padding: '16px 24px', display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
            <div>
              <div style={{ fontSize: 13, fontWeight: 500 }}>Sign out of this device</div>
              <div style={{ fontSize: 12.5, color: 'var(--fg-2)', marginTop: 2 }}>
                Your session token will be invalidated immediately.
              </div>
            </div>
            <button
              className="btn"
              style={{ color: 'var(--bad)', borderColor: 'var(--bad)', flexShrink: 0 }}
              onClick={logout}
            >
              Sign out
            </button>
          </div>
        </div>
      </section>
    </main>
  );
}
