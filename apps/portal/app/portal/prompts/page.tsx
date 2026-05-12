'use client';

export default function PromptsPage() {
  return (
    <main className="pmain">
      <div className="phero">
        <div>
          <h1>Prompts</h1>
          <p>A shared prompt library for your team — save, version, and reuse prompts across models.</p>
        </div>
        <span style={{
          padding: '4px 10px', borderRadius: 6,
          border: '1px solid var(--rule)',
          fontSize: 11.5, fontWeight: 600, color: 'var(--fg-3)',
          letterSpacing: '0.04em', textTransform: 'uppercase' as const,
        }}>Coming soon</span>
      </div>
      <div className="card">
        <div className="card__body" style={{ textAlign: 'center', padding: '60px 20px', color: 'var(--fg-3)' }}>
          <div style={{ fontSize: 36, marginBottom: 12, opacity: 0.3 }}>
            <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" style={{ width: 40, height: 40, display: 'inline-block' }}>
              <path d="M2 3h12v8H2zM5 11l-2 3M11 11l2 3M5 7h6M5 5h3"/>
            </svg>
          </div>
          <div style={{ fontSize: 14, fontWeight: 500, color: 'var(--fg-2)', marginBottom: 6 }}>Prompt library coming soon</div>
          <div style={{ fontSize: 12.5, maxWidth: 360, margin: '0 auto', lineHeight: 1.6 }}>
            Save and version prompts directly from the Playground, share them with your team,
            and track which prompts drive the best results.
          </div>
        </div>
      </div>
    </main>
  );
}
