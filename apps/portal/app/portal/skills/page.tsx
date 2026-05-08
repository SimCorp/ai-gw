export default function SkillsPage() {
  return (
    <main className="pmain">
      <div className="phero">
        <div>
          <h1>Skills</h1>
          <p>Discover and invoke reusable AI skills published by your team or the organisation.</p>
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
          <div style={{ fontSize: 13, color: 'var(--fg-2)', marginBottom: 6 }}>Not yet implemented</div>
          <div style={{ fontSize: 12.5 }}>Skill library is planned for a future release.</div>
        </div>
      </div>
    </main>
  );
}
