'use client';

import { useState, FormEvent, useEffect } from 'react';
import { useRouter } from 'next/navigation';
import { BrandMark } from '@aigw/ui';
import { setAdminToken } from '../../lib/adminAuth';

const ADMIN_API = process.env.NEXT_PUBLIC_ADMIN_API ?? 'http://localhost:8005';

const inputStyle: React.CSSProperties = {
  width: '100%',
  boxSizing: 'border-box',
  padding: '9px 12px',
  fontSize: 13,
  fontFamily: 'inherit',
  background: 'var(--surface-2)',
  border: '1px solid var(--rule-strong)',
  borderRadius: 'var(--r-2)',
  color: 'var(--fg-1)',
  outline: 'none',
};

const labelStyle: React.CSSProperties = {
  display: 'block',
  fontSize: 12.5,
  fontWeight: 500,
  color: 'var(--fg-2)',
  marginBottom: 6,
};

const errorBoxStyle: React.CSSProperties = {
  background: 'var(--bad-soft)',
  border: '1px solid var(--bad)',
  borderRadius: 'var(--r-2)',
  padding: '10px 12px',
  marginBottom: 16,
  fontSize: 13,
  color: 'var(--bad)',
};

export default function LoginPage() {
  const router = useRouter();

  // Handle SSO callback: ?sso_token=<token> redirected from /auth/oidc/callback
  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const ssoToken = params.get('sso_token');
    if (ssoToken) {
      setAdminToken(ssoToken, false);
      router.replace('/');
    }
  }, [router]);

  // Login state
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [rememberMe, setRememberMe] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Force-change-password state
  const [pendingToken, setPendingToken] = useState<string | null>(null);
  const [newPassword, setNewPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [changeLoading, setChangeLoading] = useState(false);
  const [changeError, setChangeError] = useState<string | null>(null);

  async function handleLogin(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setError(null);
    setLoading(true);

    try {
      const res = await fetch(`${ADMIN_API}/admin-auth/login`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email, password, remember_me: rememberMe }),
      });

      if (!res.ok) {
        const data = await res.json().catch(() => ({}));
        throw new Error(data.detail ?? 'Login failed');
      }

      const data = await res.json();

      if (data.must_change_password) {
        setPendingToken(data.token);
        setAdminToken(data.token, false); // temporary — replaced after password change
      } else {
        setAdminToken(data.token, rememberMe);
        router.replace('/');
      }
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Login failed');
    } finally {
      setLoading(false);
    }
  }

  async function handleChangePassword(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setChangeError(null);

    if (newPassword !== confirmPassword) {
      setChangeError('Passwords do not match');
      return;
    }
    if (newPassword.length < 12) {
      setChangeError('Password must be at least 12 characters');
      return;
    }

    setChangeLoading(true);
    try {
      const res = await fetch(`${ADMIN_API}/admin-auth/change-password`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${pendingToken}`,
        },
        body: JSON.stringify({ current_password: password, new_password: newPassword }),
      });

      if (!res.ok) {
        const data = await res.json().catch(() => ({}));
        throw new Error(data.detail ?? 'Failed to change password');
      }

      // change-password invalidates the old session — log in fresh with new password
      const loginRes = await fetch(`${ADMIN_API}/admin-auth/login`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email, password: newPassword, remember_me: rememberMe }),
      });
      if (!loginRes.ok) throw new Error('Re-login after password change failed');
      const loginData = await loginRes.json();
      setAdminToken(loginData.token, rememberMe);
      router.replace('/');
    } catch (err: unknown) {
      setChangeError(err instanceof Error ? err.message : 'Failed to change password');
    } finally {
      setChangeLoading(false);
    }
  }

  return (
    <div
      style={{
        minHeight: '100vh',
        background: 'var(--bg)',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
      }}
    >
      <div style={{ width: '100%', maxWidth: 400, padding: '0 16px' }}>
        {/* Branding */}
        <div style={{ textAlign: 'center', marginBottom: 28 }}>
          <div style={{ display: 'inline-flex', marginBottom: 12 }}>
            <BrandMark size={40} />
          </div>
          <h1 style={{ margin: 0, fontSize: 21, fontWeight: 650, color: 'var(--fg-1)', letterSpacing: '-0.02em' }}>
            ai-gw <span className="mono" style={{ fontSize: 13, color: 'var(--fg-3)' }}>/admin</span>
          </h1>
          <p style={{ margin: '4px 0 0', fontSize: 13, color: 'var(--fg-2)' }}>
            {pendingToken ? 'Set a new password to continue' : 'Sign in to continue'}
          </p>
        </div>

        {/* ── Change-password form (shown after first login) ── */}
        {pendingToken ? (
          <div className="card card--trace" style={{ padding: '26px 24px' }}>
            <div
              style={{
                background: 'var(--accent-soft)',
                border: '1px solid var(--accent)',
                borderRadius: 'var(--r-2)',
                padding: '10px 12px',
                marginBottom: 20,
                fontSize: 13,
                color: 'var(--accent-text)',
              }}
            >
              Your account requires a password change before you can continue.
              Choose a password that is at least 12 characters and includes uppercase,
              lowercase, a digit, and a special character.
            </div>

            <form onSubmit={handleChangePassword} noValidate>
              {changeError && <div style={errorBoxStyle}>{changeError}</div>}

              <div style={{ marginBottom: 16 }}>
                <label style={labelStyle}>New password</label>
                <input
                  type="password"
                  required
                  autoFocus
                  value={newPassword}
                  onChange={e => setNewPassword(e.target.value)}
                  style={inputStyle}
                />
              </div>

              <div style={{ marginBottom: 24 }}>
                <label style={labelStyle}>Confirm new password</label>
                <input
                  type="password"
                  required
                  value={confirmPassword}
                  onChange={e => setConfirmPassword(e.target.value)}
                  style={inputStyle}
                />
              </div>

              <button
                type="submit"
                disabled={changeLoading}
                className="btn btn--primary"
                style={{ width: '100%', justifyContent: 'center', padding: '10px 16px', fontSize: 13.5 }}
              >
                {changeLoading ? 'Saving…' : 'Set password and continue'}
              </button>
            </form>
          </div>
        ) : (
          /* ── Normal login form ── */
          <div className="card card--trace" style={{ padding: '26px 24px' }}>
            <form onSubmit={handleLogin} noValidate>
              {error && <div style={errorBoxStyle}>{error}</div>}

              <div style={{ marginBottom: 16 }}>
                <label style={labelStyle}>Email</label>
                <input
                  type="email"
                  autoComplete="email"
                  required
                  value={email}
                  onChange={e => setEmail(e.target.value)}
                  placeholder="you@simcorp.com"
                  style={inputStyle}
                />
              </div>

              <div style={{ marginBottom: 20 }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 6 }}>
                  <label style={{ fontSize: 12.5, fontWeight: 500, color: 'var(--fg-2)' }}>Password</label>
                  <a href="#" style={{ fontSize: 12, color: 'var(--accent-text)' }}>
                    Forgot password?
                  </a>
                </div>
                <input
                  type="password"
                  autoComplete="current-password"
                  required
                  value={password}
                  onChange={e => setPassword(e.target.value)}
                  style={inputStyle}
                />
              </div>

              <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 20 }}>
                <input
                  id="remember"
                  type="checkbox"
                  checked={rememberMe}
                  onChange={e => setRememberMe(e.target.checked)}
                  style={{ cursor: 'pointer', accentColor: 'var(--accent)' }}
                />
                <label htmlFor="remember" style={{ fontSize: 12.5, color: 'var(--fg-2)', cursor: 'pointer' }}>
                  Stay signed in for 30 days
                </label>
              </div>

              <button
                type="submit"
                disabled={loading}
                className="btn btn--primary"
                style={{ width: '100%', justifyContent: 'center', padding: '10px 16px', fontSize: 13.5 }}
              >
                {loading ? 'Signing in…' : 'Sign in'}
              </button>

              <div style={{ display: 'flex', alignItems: 'center', gap: 10, margin: '16px 0' }}>
                <div style={{ flex: 1, height: 1, background: 'var(--rule)' }} />
                <span style={{ fontSize: 11, color: 'var(--fg-3)', whiteSpace: 'nowrap' }}>or</span>
                <div style={{ flex: 1, height: 1, background: 'var(--rule)' }} />
              </div>

              <a
                href={`${ADMIN_API}/auth/oidc/login`}
                className="btn"
                style={{ width: '100%', justifyContent: 'center', padding: '9px 16px', fontSize: 13 }}
              >
                <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z" />
                </svg>
                Sign in with Entra ID (SSO)
              </a>
            </form>
          </div>
        )}

        <p
          className="microlabel"
          style={{ textAlign: 'center', marginTop: 20 }}
        >
          ai-gw · admin access only
        </p>
      </div>
    </div>
  );
}
