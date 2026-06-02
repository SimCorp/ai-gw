'use client';

import { useState, useEffect, useCallback } from 'react';
import { useRouter } from 'next/navigation';
import { useTeam } from '../_lib/teamContext';
import { useAuth } from '../_lib/authContext';

const BASE = process.env.NEXT_PUBLIC_ADMIN_BASE_URL ?? 'http://localhost:8005';

interface PromptTemplate {
  id: string;
  title: string;
  slug: string;
  version: string;
  description: string;
  content: string;
  author: string;
  model: string | null;
  tags: string[];
  visibility: string;
  uses_total: number;
  stars_avg: number;
}

export default function PromptsPage() {
  const { teamId } = useTeam();
  const { token } = useAuth();
  const router = useRouter();
  const [prompts, setPrompts] = useState<PromptTemplate[]>([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState('');
  const [expanded, setExpanded] = useState<string | null>(null);
  const [copied, setCopied] = useState<string | null>(null);
  const [using, setUsing] = useState<string | null>(null);

  useEffect(() => {
    if (!token) return;
    const url = teamId ? `${BASE}/prompts?team_id=${teamId}` : `${BASE}/prompts`;
    fetch(url, { headers: { Authorization: `Bearer ${token}` } })
      .then(r => r.ok ? r.json() : [])
      .then((data: PromptTemplate[]) => setPrompts(Array.isArray(data) ? data : []))
      .catch(() => setPrompts([]))
      .finally(() => setLoading(false));
  }, [token, teamId]);

  const handleCopy = useCallback(async (p: PromptTemplate) => {
    await navigator.clipboard.writeText(p.content).catch(() => {});
    setCopied(p.id);
    setTimeout(() => setCopied(null), 2000);
    fetch(`${BASE}/prompts/${p.id}/use`, { method: 'POST', headers: { Authorization: `Bearer ${token}` } }).catch(() => {});
  }, [token]);

  const handleUseInPlayground = useCallback(async (p: PromptTemplate) => {
    setUsing(p.id);
    fetch(`${BASE}/prompts/${p.id}/use`, { method: 'POST', headers: { Authorization: `Bearer ${token}` } }).catch(() => {});
    const params = new URLSearchParams({ prompt_content: p.content, prompt_title: p.title });
    if (p.model) params.set('model', p.model);
    router.push(`/portal/playground?${params.toString()}`);
  }, [token, router]);

  const filtered = prompts.filter(p =>
    !search || p.title.toLowerCase().includes(search.toLowerCase()) ||
    p.description.toLowerCase().includes(search.toLowerCase()) ||
    p.tags.some(t => t.toLowerCase().includes(search.toLowerCase()))
  );

  return (
    <main className="pmain">
      <div className="phero">
        <div>
          <h1>Prompts</h1>
          <p>A shared prompt library — browse, copy, and launch prompts directly into the Playground.</p>
        </div>
      </div>

      <div style={{ display: 'flex', gap: 8, marginBottom: 20 }}>
        <input
          className="search"
          type="search"
          placeholder="Search prompts…"
          value={search}
          onChange={e => setSearch(e.target.value)}
          style={{ maxWidth: 360 }}
        />
        <span style={{ fontSize: 13, color: 'var(--fg-3)', alignSelf: 'center', marginLeft: 8 }}>
          {loading ? 'Loading…' : `${filtered.length} prompt${filtered.length !== 1 ? 's' : ''}`}
        </span>
      </div>

      {!loading && filtered.length === 0 && (
        <div className="card">
          <div className="card__body" style={{ textAlign: 'center', padding: '48px 20px', color: 'var(--fg-3)', fontSize: 13 }}>
            {prompts.length === 0 ? 'No prompts yet. Ask your admin to add some.' : 'No prompts match your search.'}
          </div>
        </div>
      )}

      <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
        {filtered.map(p => (
          <div key={p.id} className="card">
            <div className="card__head" style={{ alignItems: 'flex-start' }}>
              <div style={{ flex: 1, minWidth: 0 }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
                  <span style={{ fontWeight: 600, fontSize: 14 }}>{p.title}</span>
                  <span className="pill pill--info" style={{ fontSize: 11 }}>{p.version}</span>
                  {p.visibility === 'org' && <span className="pill pill--good" style={{ fontSize: 11 }}>org-wide</span>}
                </div>
                <div style={{ fontSize: 12.5, color: 'var(--fg-2)', marginTop: 4 }}>{p.description}</div>
                <div style={{ display: 'flex', gap: 6, marginTop: 6, flexWrap: 'wrap', alignItems: 'center' }}>
                  {p.model && <span className="mono" style={{ fontSize: 11.5, color: 'var(--fg-3)' }}>{p.model}</span>}
                  {p.uses_total > 0 && (
                    <><span style={{ color: 'var(--fg-3)', fontSize: 11 }}>·</span>
                    <span style={{ fontSize: 11.5, color: 'var(--fg-3)' }}>{p.uses_total.toLocaleString()} uses</span></>
                  )}
                  <span style={{ fontSize: 11.5, color: 'var(--fg-3)' }}>by {p.author}</span>
                  {p.tags.map(t => <span key={t} className="tag" style={{ fontSize: 11 }}>{t}</span>)}
                </div>
              </div>
              <div style={{ display: 'flex', gap: 6, flexShrink: 0 }}>
                <button className="btn btn--sm btn--ghost" onClick={() => setExpanded(expanded === p.id ? null : p.id)}>
                  {expanded === p.id ? 'Hide ▲' : 'Preview ▼'}
                </button>
                <button className="btn btn--sm btn--ghost" onClick={() => handleCopy(p)}>
                  {copied === p.id ? 'Copied!' : 'Copy'}
                </button>
                <button className="btn btn--sm btn--primary" onClick={() => handleUseInPlayground(p)} disabled={using === p.id}>
                  {using === p.id ? 'Opening…' : '▶ Use'}
                </button>
              </div>
            </div>
            {expanded === p.id && (
              <div className="card__body" style={{ borderTop: '1px solid var(--rule)' }}>
                <pre style={{ margin: 0, padding: '10px 14px', background: 'var(--surface-soft)', borderRadius: 8, fontSize: 12.5, fontFamily: 'var(--font-mono)', lineHeight: 1.5, whiteSpace: 'pre-wrap', wordBreak: 'break-word', color: 'var(--fg-2)' }}>
                  {p.content}
                </pre>
              </div>
            )}
          </div>
        ))}
      </div>
    </main>
  );
}
