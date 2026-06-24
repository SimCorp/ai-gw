'use client';

import React from 'react';
import { PageHead } from '@aigw/ui';

const ADMIN_EMBED = process.env.NEXT_PUBLIC_RYBBIT_ADMIN_EMBED_URL ?? '';
const PORTAL_EMBED = process.env.NEXT_PUBLIC_RYBBIT_PORTAL_EMBED_URL ?? '';

export default function PortalAnalyticsPage() {
  return (
    <section className="page">
      <PageHead title="Portal Analytics" subtitle="Cookieless usage analytics for admin and developer portals" />

      <div className="stack">
        <section>
          <h2 style={{ marginBottom: '0.75rem', fontSize: '0.875rem', fontWeight: 600, color: 'var(--fg-3)' }}>
            Admin Portal
          </h2>
          {ADMIN_EMBED ? (
            <iframe
              src={ADMIN_EMBED}
              style={{ width: '100%', height: '600px', border: 'none', borderRadius: '0.5rem' }}
              title="Admin Portal Analytics"
            />
          ) : (
            <p style={{ color: 'var(--fg-3)', fontSize: '0.875rem' }}>
              No embed URL configured. Set <code>NEXT_PUBLIC_RYBBIT_ADMIN_EMBED_URL</code>.
            </p>
          )}
        </section>

        <section>
          <h2 style={{ marginBottom: '0.75rem', fontSize: '0.875rem', fontWeight: 600, color: 'var(--fg-3)' }}>
            Developer Portal
          </h2>
          {PORTAL_EMBED ? (
            <iframe
              src={PORTAL_EMBED}
              style={{ width: '100%', height: '600px', border: 'none', borderRadius: '0.5rem' }}
              title="Developer Portal Analytics"
            />
          ) : (
            <p style={{ color: 'var(--fg-3)', fontSize: '0.875rem' }}>
              No embed URL configured. Set <code>NEXT_PUBLIC_RYBBIT_PORTAL_EMBED_URL</code>.
            </p>
          )}
        </section>
      </div>
    </section>
  );
}
