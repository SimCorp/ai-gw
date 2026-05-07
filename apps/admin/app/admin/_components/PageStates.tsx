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
