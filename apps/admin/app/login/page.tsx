'use client';

import { useState, FormEvent, useEffect } from 'react';
import { useRouter } from 'next/navigation';
import { setAdminToken } from '../../lib/adminAuth';

const ADMIN_API = process.env.NEXT_PUBLIC_ADMIN_API ?? 'http://localhost:8005';

const inputStyle: React.CSSProperties = {
  width: '100%',
  boxSizing: 'border-box',
  padding: '9px 12px',
  fontSize: 13,
  background: 'var(--side-bg, #0F1224)',
  border: '1px solid var(--side-rule, #232950)',
  borderRadius: 6,
  color: 'var(--side-fg, #C8CDDC)',
  outline: 'none',
};

const labelStyle: React.CSSProperties = {
  display: 'block',
  fontSize: 12.5,
  fontWeight: 500,
  color: 'var(--side-fg, #C8CDDC)',
  marginBottom: 6,
};

export default function LoginPage() {
  const router = useRouter();

  // Handle SSO callback: ?sso_token=<token> redirected from /auth/oidc/callback
  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const ssoToken = params.get('sso_token');
    if (ssoToken) {
      setAdminToken(ssoToken, false);
      router.replace('/admin');
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
        router.replace('/admin');
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
      router.replace('/admin');
    } catch (err: unknown) {
      setChangeError(err instanceof Error ? err.message : 'Failed to change password');
    } finally {
      setChangeLoading(false);
    }
  }

  const cardStyle: React.CSSProperties = {
    background: 'var(--surface, #161A33)',
    border: '1px solid var(--side-rule, #232950)',
    borderRadius: 12,
    padding: '28px 24px',
    boxShadow: 'var(--shadow-pop, 0 12px 32px rgba(0,0,0,0.3))',
  };

  const submitButtonStyle = (disabled: boolean): React.CSSProperties => ({
    width: '100%',
    padding: '10px 16px',
    fontSize: 14,
    fontWeight: 600,
    background: disabled ? 'var(--sc-blue-hover, #062E7D)' : 'var(--sc-blue, #083EA7)',
    color: '#fff',
    border: 'none',
    borderRadius: 7,
    cursor: disabled ? 'not-allowed' : 'pointer',
    transition: 'background 0.15s',
    opacity: disabled ? 0.75 : 1,
  });

  return (
    <div style={{
      minHeight: '100vh',
      background: 'var(--bg, #0F1224)',
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'center',
      fontFamily: 'var(--font-sans, "Geist", system-ui, sans-serif)',
    }}>
      <div style={{ width: '100%', maxWidth: 400, padding: '0 16px' }}>

        {/* Branding */}
        <div style={{ textAlign: 'center', marginBottom: 32 }}>
          <div style={{
            display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
            width: 44, height: 44, borderRadius: 10,
            background: 'var(--sc-blue, #083EA7)', color: '#fff',
            fontWeight: 700, fontSize: 16, marginBottom: 16,
          }}>AI</div>
          <h1 style={{ margin: 0, fontSize: 22, fontWeight: 700, color: 'var(--fg-inv, #FFFFFF)', letterSpacing: '-0.02em' }}>
            AI Gateway
          </h1>
          <p style={{ margin: '4px 0 0', fontSize: 13, color: 'var(--side-fg-mute, #8089A3)' }}>
            {pendingToken ? 'Set a new password to continue' : 'Admin portal — sign in to continue'}
          </p>
        </div>

        {/* ── Change-password form (shown after first login) ── */}
        {pendingToken ? (
          <div style={cardStyle}>
            <div style={{
              background: 'rgba(8, 62, 167, 0.15)',
              border: '1px solid rgba(8, 62, 167, 0.4)',
              borderRadius: 6, padding: '10px 12px', marginBottom: 20,
              fontSize: 13, color: '#93C5FD',
            }}>
              Your account requires a password change before you can continue.
              Choose a password that is at least 12 characters and includes uppercase,
              lowercase, a digit, and a special character.
            </div>

            <form onSubmit={handleChangePassword} noValidate>
              {changeError && (
                <div style={{
                  background: 'rgba(220,38,38,0.12)', border: '1px solid rgba(220,38,38,0.4)',
                  borderRadius: 6, padding: '10px 12px', marginBottom: 16,
                  fontSize: 13, color: '#FCA5A5',
                }}>{changeError}</div>
              )}

              <div style={{ marginBottom: 16 }}>
                <label style={labelStyle}>New password</label>
                <input
                  type="password"
                  required
                  autoFocus
                  value={newPassword}
                  onChange={e => setNewPassword(e.target.value)}
                  style={inputStyle}
                  onFocus={e => { e.currentTarget.style.borderColor = 'var(--sc-blue, #083EA7)'; }}
                  onBlur={e => { e.currentTarget.style.borderColor = 'var(--side-rule, #232950)'; }}
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
                  onFocus={e => { e.currentTarget.style.borderColor = 'var(--sc-blue, #083EA7)'; }}
                  onBlur={e => { e.currentTarget.style.borderColor = 'var(--side-rule, #232950)'; }}
                />
              </div>

              <button
                type="submit"
                disabled={changeLoading}
                style={submitButtonStyle(changeLoading)}
                onMouseEnter={e => { if (!changeLoading) (e.currentTarget as HTMLElement).style.background = 'var(--sc-blue-hover, #062E7D)'; }}
                onMouseLeave={e => { if (!changeLoading) (e.currentTarget as HTMLElement).style.background = 'var(--sc-blue, #083EA7)'; }}
              >
                {changeLoading ? 'Saving…' : 'Set password and continue'}
              </button>
            </form>
          </div>
        ) : (

        /* ── Normal login form ── */
        <div style={cardStyle}>
          <form onSubmit={handleLogin} noValidate>
            {error && (
              <div style={{
                background: 'rgba(220,38,38,0.12)', border: '1px solid rgba(220,38,38,0.4)',
                borderRadius: 6, padding: '10px 12px', marginBottom: 16,
                fontSize: 13, color: '#FCA5A5',
              }}>{error}</div>
            )}

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
                onFocus={e => { e.currentTarget.style.borderColor = 'var(--sc-blue, #083EA7)'; }}
                onBlur={e => { e.currentTarget.style.borderColor = 'var(--side-rule, #232950)'; }}
              />
              {process.env.NODE_ENV !== 'production' && (
                <div style={{ fontSize: 11, color: 'var(--fg-3, #666)', marginTop: 4 }}>
                  Local dev: <code style={{ fontFamily: 'monospace' }}>admin@simcorp.com</code> / <code style={{ fontFamily: 'monospace' }}>password</code>
                </div>
              )}
            </div>

            <div style={{ marginBottom: 20 }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 6 }}>
                <label style={{ fontSize: 12.5, fontWeight: 500, color: 'var(--side-fg, #C8CDDC)' }}>
                  Password
                </label>
                <a href="#" style={{ fontSize: 12, color: 'var(--sc-link, #0A7BD7)', textDecoration: 'none' }}>
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
                onFocus={e => { e.currentTarget.style.borderColor = 'var(--sc-blue, #083EA7)'; }}
                onBlur={e => { e.currentTarget.style.borderColor = 'var(--side-rule, #232950)'; }}
              />
            </div>

            <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 20 }}>
              <input
                id="remember"
                type="checkbox"
                checked={rememberMe}
                onChange={e => setRememberMe(e.target.checked)}
                style={{ cursor: 'pointer', accentColor: 'var(--sc-blue, #083EA7)' }}
              />
              <label htmlFor="remember" style={{ fontSize: 12.5, color: 'var(--side-fg-mute, #8089A3)', cursor: 'pointer' }}>
                Stay signed in for 30 days
              </label>
            </div>

            <button
              type="submit"
              disabled={loading}
              style={submitButtonStyle(loading)}
              onMouseEnter={e => { if (!loading) (e.currentTarget as HTMLElement).style.background = 'var(--sc-blue-hover, #062E7D)'; }}
              onMouseLeave={e => { if (!loading) (e.currentTarget as HTMLElement).style.background = 'var(--sc-blue, #083EA7)'; }}
            >
              {loading ? 'Signing in…' : 'Sign in'}
            </button>

            <div style={{ display: 'flex', alignItems: 'center', gap: 10, margin: '16px 0' }}>
              <div style={{ flex: 1, height: 1, background: 'var(--side-rule, #232950)' }} />
              <span style={{ fontSize: 11, color: 'var(--side-fg-mute, #8089A3)', whiteSpace: 'nowrap' }}>or</span>
              <div style={{ flex: 1, height: 1, background: 'var(--side-rule, #232950)' }} />
            </div>

            <a
              href={`${ADMIN_API}/auth/oidc/login`}
              style={{
                display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 8,
                width: '100%', padding: '9px 16px', fontSize: 13, fontWeight: 600,
                background: 'transparent', color: 'var(--side-fg, #C8CDDC)',
                border: '1px solid var(--side-rule, #232950)', borderRadius: 7,
                cursor: 'pointer', textDecoration: 'none', transition: 'border-color 0.15s',
              }}
              onMouseEnter={e => { (e.currentTarget as HTMLElement).style.borderColor = 'var(--sc-blue, #083EA7)'; }}
              onMouseLeave={e => { (e.currentTarget as HTMLElement).style.borderColor = 'var(--side-rule, #232950)'; }}
            >
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/>
              </svg>
              Sign in with Entra ID (SSO)
            </a>
          </form>
        </div>
        )}

        <p style={{ textAlign: 'center', marginTop: 20, fontSize: 12, color: 'var(--side-fg-mute, #8089A3)' }}>
          SimCorp AI Gateway · Admin access only
        </p>
      </div>
    </div>
  );
}
