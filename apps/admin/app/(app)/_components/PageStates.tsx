'use client';

import React from 'react';

export function LoadingState({ rows = 5 }: { rows?: number }) {
  return (
    <div className="card">
      <div className="card__body" style={{ padding: '20px', display: 'flex', flexDirection: 'column', gap: 12 }}>
        {Array.from({ length: rows }).map((_, i) => (
          <div key={i} style={{
            height: 20,
            borderRadius: 4,
            background: 'var(--surface-soft)',
            opacity: 1 - i * 0.1,
            animation: 'pulse 1.4s ease-in-out infinite',
            animationDelay: `${i * 0.07}s`,
            width: i % 3 === 0 ? '60%' : i % 3 === 1 ? '80%' : '100%',
          }} />
        ))}
      </div>
    </div>
  );
}

export function ErrorState({ error, retry }: { error: Error; retry?: () => void }) {
  return (
    <div className="card" style={{ borderColor: 'var(--bad)' }}>
      <div className="card__body" style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
        <span className="statusdot statusdot--bad" />
        <div style={{ flex: 1 }}>
          <div style={{ fontWeight: 600, fontSize: 13 }}>Failed to load</div>
          <div className="muted" style={{ fontSize: 12 }}>{error.message}</div>
        </div>
        {retry && (
          <button className="btn btn--sm" onClick={retry}>Retry</button>
        )}
      </div>
    </div>
  );
}

export function EmptyState({ message = 'No data to display.' }: { message?: string }) {
  return (
    <div className="card">
      <div className="card__body" style={{ textAlign: 'center', padding: '40px 20px', color: 'var(--fg-3)' }}>
        <div style={{ fontSize: 13 }}>{message}</div>
      </div>
    </div>
  );
}

export function ComingSoon({ title, description }: { title: string; description?: string }) {
  return (
    <section className="page">
      <div className="page__head">
        <div>
          <h1 className="page__title">{title}</h1>
          {description && <p className="page__sub">{description}</p>}
        </div>
        <span style={{
          display: 'inline-flex', alignItems: 'center', gap: 6,
          padding: '4px 10px', borderRadius: 6,
          background: 'var(--surface-soft, rgba(0,0,0,0.06))',
          border: '1px solid var(--rule)',
          fontSize: 11.5, fontWeight: 600, color: 'var(--fg-3)',
          letterSpacing: '0.04em', textTransform: 'uppercase',
        }}>Coming soon</span>
      </div>
      <div className="card" style={{ marginTop: 8 }}>
        <div className="card__body" style={{ textAlign: 'center', padding: '60px 20px', color: 'var(--fg-3)' }}>
          <div style={{ fontSize: 32, marginBottom: 12, opacity: 0.3 }}>⚙️</div>
          <div style={{ fontSize: 14, fontWeight: 500, color: 'var(--fg-2)', marginBottom: 6 }}>Not yet implemented</div>
          <div style={{ fontSize: 12.5 }}>This section is planned for a future release.</div>
        </div>
      </div>
    </section>
  );
}
