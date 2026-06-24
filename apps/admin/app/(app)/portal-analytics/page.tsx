import React from 'react';
import { PageHead } from '@aigw/ui';

// Read at request time on the server — update infra/.env + restart (no rebuild needed)
const ADMIN_EMBED = process.env.RYBBIT_EMBED_URL_ADMIN ?? '';
const PORTAL_EMBED = process.env.RYBBIT_EMBED_URL_PORTAL ?? '';

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
              No embed URL configured. Set <code>RYBBIT_EMBED_URL_ADMIN</code>.
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
              No embed URL configured. Set <code>RYBBIT_EMBED_URL_PORTAL</code>.
            </p>
          )}
        </section>
      </div>
    </section>
  );
}
