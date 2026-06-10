'use client';

import React from 'react';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { AuthGuard } from './_components/AuthGuard';
import { getAdminToken, clearAdminToken } from '../../lib/adminAuth';
import AiHelpWidget from './_components/AiHelpWidget';

const ADMIN_API = process.env.NEXT_PUBLIC_ADMIN_API ?? 'http://localhost:8005';

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 30_000,
      retry: 1,
    },
  },
});

function SignOutButton() {
  const router = useRouter();

  async function handleSignOut() {
    const token = getAdminToken();
    if (token) {
      try {
        await fetch(`${ADMIN_API}/admin-auth/logout`, {
          method: 'POST',
          headers: { Authorization: `Bearer ${token}` },
        });
      } catch {
        // Best-effort — clear locally regardless
      }
    }
    clearAdminToken();
    router.replace('/login');
  }

  return (
    <button
      onClick={handleSignOut}
      style={{
        display: 'block',
        width: 'calc(100% - 12px)',
        margin: '4px 6px',
        padding: '7px 14px',
        fontSize: 13,
        color: 'var(--side-fg-mute)',
        background: 'transparent',
        border: 'none',
        borderRadius: 4,
        cursor: 'pointer',
        textAlign: 'left',
      }}
      onMouseEnter={e => { (e.currentTarget as HTMLElement).style.background = 'var(--side-active)'; (e.currentTarget as HTMLElement).style.color = 'var(--side-fg)'; }}
      onMouseLeave={e => { (e.currentTarget as HTMLElement).style.background = ''; (e.currentTarget as HTMLElement).style.color = 'var(--side-fg-mute)'; }}
    >
      Sign out
    </button>
  );
}

export default function AdminLayout({ children }: { children: React.ReactNode }) {
  return (
    <QueryClientProvider client={queryClient}>
      <AuthGuard>
        <div className="app">
            <aside className="sidebar" style={{ display: 'flex', flexDirection: 'column' }}>
              <div style={{ padding: '16px 14px', borderBottom: '1px solid var(--side-rule)', marginBottom: 8 }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                  <span style={{
                    display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
                    width: 28, height: 28, borderRadius: 6, background: 'var(--sc-blue)',
                    color: '#fff', fontWeight: 700, fontSize: 11, flexShrink: 0,
                  }}>AI</span>
                  <div>
                    <div style={{ color: 'var(--side-fg)', fontWeight: 600, fontSize: 13 }}>AI Gateway</div>
                    <div style={{ color: 'var(--side-fg-mute)', fontSize: 11 }}>Admin</div>
                  </div>
                </div>
              </div>

              <div style={{ flex: 1, overflowY: 'auto' }}>
                <NavSection label="Monitor">
                  <NavItem href="/admin/dashboard" label="Dashboard" />
                  <NavItem href="/admin/requests" label="Live requests" />
                  <NavItem href="/admin/reports" label="Cost reports" />
                  <NavItem href="/admin/alerts" label="Alerts" />
                </NavSection>

                <NavSection label="Organisation">
                  <NavItem href="/admin/org" label="Org tree" />
                  <NavItem href="/admin/users" label="Users" />
                </NavSection>

                <NavSectionLink href="/admin/transformation" label="AI Transformation">
                  <NavItem href="/admin/genai-adoption" label="GenAI Adoption" />
                  <NavItem href="/admin/insights" label="AI Insights" />
                  <NavItem href="/admin/devops" label="DevOps Agent" />
                  <NavItem href="/admin/champions" label="Champions" />
                  <NavSubItem href="/admin/champions/activity" label="Activity" />
                  <NavSubItem href="/admin/champions/flags" label="Flags" />
                </NavSectionLink>

                <NavSection label="Govern">
                  <NavItem href="/admin/guardrails" label="Guardrails" />
                  <NavItem href="/admin/policies" label="Policies" />
                  <NavItem href="/admin/quotas" label="Quotas & budgets" />
                  <NavItem href="/admin/approvals" label="Approvals" />
                  <NavItem href="/admin/audit" label="Audit log" />
                </NavSection>

                <NavSection label="Security">
                  <NavItem href="/admin/security/targets" label="Targets" />
                  <NavItem href="/admin/security/jobs" label="Scan jobs" />
                  <NavItem href="/admin/security/quotas" label="Team quotas" />
                </NavSection>

                <NavSection label="Catalog">
                  <NavItem href="/admin/mcp" label="MCP servers" />
                  <NavItem href="/admin/memory" label="Memory" />
                  <NavItem href="/admin/skills" label="Skills" />
                  <NavItem href="/admin/plugins" label="Plugins" />
                </NavSection>

                <NavSection label="Configure">
                  <NavItem href="/admin/models" label="Model registry" />
                  <NavItem href="/admin/cache" label="Semantic cache" />
                  <NavItem href="/admin/providers" label="Providers" />
                  <NavItem href="/admin/providers#auto-drive" label="Auto-Drive" />
                  <NavItem href="/admin/tools" label="Developer tools" />
                </NavSection>

                <NavSection label="League">
                  <NavItem href="/admin/league/seasons" label="Seasons" />
                  <NavItem href="/admin/league/challenges" label="Challenges" />
                  <NavItem href="/admin/league/proposals" label="Proposals" />
                  <NavItem href="/admin/league/store" label="Store editor" />
                </NavSection>

                <NavSection label="Settings">
                  <NavItem href="/admin/settings/entra" label="Entra ID groups" />
                  <NavItem href="/admin/settings/sessions" label="Sessions" />
                </NavSection>
              </div>

              <div style={{ borderTop: '1px solid var(--side-rule)', paddingTop: 8, paddingBottom: 8 }}>
                <SignOutButton />
              </div>
            </aside>

            <main className="main">
              {children}
            </main>
          </div>
          <AiHelpWidget />
      </AuthGuard>
    </QueryClientProvider>
  );
}

function NavSectionLink({ href, label, children }: { href: string; label: string; children?: React.ReactNode }) {
  return (
    <div style={{ marginBottom: 4 }}>
      <Link
        href={href}
        style={{
          display: 'block',
          padding: '10px 14px 4px',
          fontSize: 10.5, fontWeight: 600, letterSpacing: '0.06em',
          textTransform: 'uppercase', color: 'var(--side-fg-mute)',
          textDecoration: 'none',
        }}
        onMouseEnter={e => { (e.currentTarget as HTMLElement).style.color = 'var(--side-fg)'; }}
        onMouseLeave={e => { (e.currentTarget as HTMLElement).style.color = 'var(--side-fg-mute)'; }}
      >{label}</Link>
      {children}
    </div>
  );
}

function NavSection({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div style={{ marginBottom: 4 }}>
      <div style={{
        padding: '10px 14px 4px',
        fontSize: 10.5, fontWeight: 600, letterSpacing: '0.06em',
        textTransform: 'uppercase', color: 'var(--side-fg-mute)',
      }}>{label}</div>
      {children}
    </div>
  );
}

function NavItem({ href, label }: { href: string; label: string }) {
  return (
    <Link
      href={href}
      style={{
        display: 'block',
        padding: '7px 14px',
        fontSize: 13,
        color: 'var(--side-fg)',
        borderRadius: 4,
        margin: '1px 6px',
        textDecoration: 'none',
      }}
      onMouseEnter={e => { (e.currentTarget as HTMLElement).style.background = 'var(--side-active)'; }}
      onMouseLeave={e => { (e.currentTarget as HTMLElement).style.background = ''; }}
    >
      {label}
    </Link>
  );
}

function NavSubItem({ href, label }: { href: string; label: string }) {
  return (
    <Link
      href={href}
      style={{
        display: 'block',
        padding: '6px 14px 6px 30px',
        fontSize: 12.5,
        color: 'var(--side-fg-mute)',
        borderRadius: 4,
        margin: '1px 6px',
        textDecoration: 'none',
      }}
      onMouseEnter={e => { (e.currentTarget as HTMLElement).style.background = 'var(--side-active)'; (e.currentTarget as HTMLElement).style.color = 'var(--side-fg)'; }}
      onMouseLeave={e => { (e.currentTarget as HTMLElement).style.background = ''; (e.currentTarget as HTMLElement).style.color = 'var(--side-fg-mute)'; }}
    >
      {label}
    </Link>
  );
}
