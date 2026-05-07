'use client';

import React, { useEffect, useState } from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 30_000,
      retry: 1,
    },
  },
});

function MSWGate({ children }: { children: React.ReactNode }) {
  useEffect(() => {
    if (process.env.NODE_ENV !== 'development') return;
    import('./_mocks/browser').then(({ worker }) =>
      worker.start({ onUnhandledRequest: 'bypass' })
    ).catch(() => { /* service worker unavailable — MSW runs in node mode */ });
  }, []);

  return <>{children}</>;
}

export default function AdminLayout({ children }: { children: React.ReactNode }) {
  // Apply dark theme before first paint
  useEffect(() => {
    document.documentElement.setAttribute('data-theme', 'dark');
    return () => {
      document.documentElement.removeAttribute('data-theme');
    };
  }, []);

  return (
    <QueryClientProvider client={queryClient}>
      <MSWGate>
        <div className="app">
          <aside className="sidebar">
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

            <NavSection label="Overview">
              <NavItem href="/admin/dashboard" label="Dashboard" />
              <NavItem href="/admin/requests" label="Live requests" />
              <NavItem href="/admin/teams" label="Teams" />
            </NavSection>

            <NavSection label="Govern">
              <NavItem href="/admin/guardrails" label="Guardrails" />
              <NavItem href="/admin/audit" label="Audit log" />
              <NavItem href="/admin/policies" label="Policies" />
              <NavItem href="/admin/quotas" label="Quotas & budgets" />
              <NavItem href="/admin/approvals" label="Approvals" />
            </NavSection>

            <NavSection label="Catalog">
              <NavItem href="/admin/mcp" label="MCP servers" />
              <NavItem href="/admin/skills" label="Skills" />
              <NavItem href="/admin/plugins" label="Plugins" />
            </NavSection>

            <NavSection label="Configure">
              <NavItem href="/admin/models" label="Model registry" />
              <NavItem href="/admin/cache" label="Semantic cache" />
              <NavItem href="/admin/providers" label="Providers" />
            </NavSection>

            <NavSection label="Operate">
              <NavItem href="/admin/alerts" label="Alerts" />
            </NavSection>
          </aside>

          <main className="main">
            {children}
          </main>
        </div>
      </MSWGate>
    </QueryClientProvider>
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
    <a
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
    </a>
  );
}
