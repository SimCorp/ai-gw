'use client';

import { useState, FormEvent } from 'react';
import { useRouter } from 'next/navigation';
import { setAdminToken } from '../../lib/adminAuth';

const ADMIN_API = process.env.NEXT_PUBLIC_ADMIN_API ?? 'http://localhost:8005';

export default function LoginPage() {
  const router = useRouter();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [rememberMe, setRememberMe] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleSubmit(e: FormEvent<HTMLFormElement>) {
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
      setAdminToken(data.token);
      router.replace('/admin');
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Login failed');
    } finally {
      setLoading(false);
    }
  }

  return (
    <div style={{
      minHeight: '100vh',
      background: 'var(--bg, #0F1224)',
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'center',
      fontFamily: 'var(--font-sans, "Geist", system-ui, sans-serif)',
    }}>
      <div style={{
        width: '100%',
        maxWidth: 400,
        padding: '0 16px',
      }}>
        {/* Logo / branding */}
        <div style={{ textAlign: 'center', marginBottom: 32 }}>
          <div style={{
            display: 'inline-flex',
            alignItems: 'center',
            justifyContent: 'center',
            width: 44,
            height: 44,
            borderRadius: 10,
            background: 'var(--sc-blue, #083EA7)',
            color: '#fff',
            fontWeight: 700,
            fontSize: 16,
            marginBottom: 16,
          }}>AI</div>
          <h1 style={{
            margin: 0,
            fontSize: 22,
            fontWeight: 700,
            color: 'var(--fg-inv, #FFFFFF)',
            letterSpacing: '-0.02em',
          }}>AI Gateway</h1>
          <p style={{
            margin: '4px 0 0',
            fontSize: 13,
            color: 'var(--side-fg-mute, #8089A3)',
          }}>Admin portal — sign in to continue</p>
        </div>

        {/* Card */}
        <div style={{
          background: 'var(--surface, #161A33)',
          border: '1px solid var(--side-rule, #232950)',
          borderRadius: 12,
          padding: '28px 24px',
          boxShadow: 'var(--shadow-pop, 0 12px 32px rgba(0,0,0,0.3))',
        }}>
          <form onSubmit={handleSubmit} noValidate>
            {/* Error message */}
            {error && (
              <div style={{
                background: 'rgba(220, 38, 38, 0.12)',
                border: '1px solid rgba(220, 38, 38, 0.4)',
                borderRadius: 6,
                padding: '10px 12px',
                marginBottom: 16,
                fontSize: 13,
                color: '#FCA5A5',
              }}>
                {error}
              </div>
            )}

            {/* Email */}
            <div style={{ marginBottom: 16 }}>
              <label style={{
                display: 'block',
                fontSize: 12.5,
                fontWeight: 500,
                color: 'var(--side-fg, #C8CDDC)',
                marginBottom: 6,
              }}>
                Email
              </label>
              <input
                type="email"
                autoComplete="email"
                required
                value={email}
                onChange={e => setEmail(e.target.value)}
                placeholder="admin@simcorp.com"
                style={{
                  width: '100%',
                  boxSizing: 'border-box',
                  padding: '9px 12px',
                  fontSize: 13,
                  background: 'var(--side-bg, #0F1224)',
                  border: '1px solid var(--side-rule, #232950)',
                  borderRadius: 6,
                  color: 'var(--side-fg, #C8CDDC)',
                  outline: 'none',
                }}
                onFocus={e => { e.currentTarget.style.borderColor = 'var(--sc-blue, #083EA7)'; }}
                onBlur={e => { e.currentTarget.style.borderColor = 'var(--side-rule, #232950)'; }}
              />
            </div>

            {/* Password */}
            <div style={{ marginBottom: 20 }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 6 }}>
                <label style={{
                  fontSize: 12.5,
                  fontWeight: 500,
                  color: 'var(--side-fg, #C8CDDC)',
                }}>
                  Password
                </label>
                <a href="#" style={{
                  fontSize: 12,
                  color: 'var(--sc-link, #0A7BD7)',
                  textDecoration: 'none',
                }}>
                  Forgot password?
                </a>
              </div>
              <input
                type="password"
                autoComplete="current-password"
                required
                value={password}
                onChange={e => setPassword(e.target.value)}
                style={{
                  width: '100%',
                  boxSizing: 'border-box',
                  padding: '9px 12px',
                  fontSize: 13,
                  background: 'var(--side-bg, #0F1224)',
                  border: '1px solid var(--side-rule, #232950)',
                  borderRadius: 6,
                  color: 'var(--side-fg, #C8CDDC)',
                  outline: 'none',
                }}
                onFocus={e => { e.currentTarget.style.borderColor = 'var(--sc-blue, #083EA7)'; }}
                onBlur={e => { e.currentTarget.style.borderColor = 'var(--side-rule, #232950)'; }}
              />
            </div>

            {/* Remember me */}
            <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 20 }}>
              <input
                id="remember"
                type="checkbox"
                checked={rememberMe}
                onChange={e => setRememberMe(e.target.checked)}
                style={{ cursor: 'pointer', accentColor: 'var(--sc-blue, #083EA7)' }}
              />
              <label htmlFor="remember" style={{
                fontSize: 12.5,
                color: 'var(--side-fg-mute, #8089A3)',
                cursor: 'pointer',
              }}>
                Stay signed in for 30 days
              </label>
            </div>

            {/* Submit */}
            <button
              type="submit"
              disabled={loading}
              style={{
                width: '100%',
                padding: '10px 16px',
                fontSize: 14,
                fontWeight: 600,
                background: loading ? 'var(--sc-blue-hover, #062E7D)' : 'var(--sc-blue, #083EA7)',
                color: '#fff',
                border: 'none',
                borderRadius: 7,
                cursor: loading ? 'not-allowed' : 'pointer',
                transition: 'background 0.15s',
                opacity: loading ? 0.75 : 1,
              }}
              onMouseEnter={e => { if (!loading) (e.currentTarget as HTMLElement).style.background = 'var(--sc-blue-hover, #062E7D)'; }}
              onMouseLeave={e => { if (!loading) (e.currentTarget as HTMLElement).style.background = 'var(--sc-blue, #083EA7)'; }}
            >
              {loading ? 'Signing in…' : 'Sign in'}
            </button>
          </form>
        </div>

        <p style={{
          textAlign: 'center',
          marginTop: 20,
          fontSize: 12,
          color: 'var(--side-fg-mute, #8089A3)',
        }}>
          SimCorp AI Gateway · Admin access only
        </p>
      </div>
    </div>
  );
}
