'use client';

import React, { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { apiFetch } from '../../../lib/apiClient';
import { LoadingState, ErrorState } from '../_components/PageStates';

const BASE = process.env.NEXT_PUBLIC_ADMIN_API ?? 'http://localhost:8005';

interface Skill {
  id: string;
  name: string;
  slug: string;
  version: string;
  model: string;
  description: string;
  system_prompt: string;
  tools: string[];
  tags: string[];
  visibility: 'draft' | 'team' | 'org';
  team_id: string | null;
  author: string;
  uses_total: number;
  stars_avg: number;
  created_at: string;
}

const VISIBILITY_LABELS: Record<string, string> = { draft: 'Draft', team: 'Team', org: 'Org-wide' };

function visibilityPill(v: string) {
  if (v === 'org')   return <span className="pill pill--good">{VISIBILITY_LABELS[v]}</span>;
  if (v === 'team')  return <span className="pill pill--info">{VISIBILITY_LABELS[v]}</span>;
  return <span className="pill">{VISIBILITY_LABELS[v] ?? v}</span>;
}

export default function AdminSkillsPage() {
  const qc = useQueryClient();
  const [filter, setFilter] = useState('all');
  const [creating, setCreating] = useState(false);
  const [form, setForm] = useState({ name: '', slug: '', model: 'claude-sonnet-4-6', description: '', system_prompt: '', tags: '', visibility: 'team' as string });
  const [saving, setSaving] = useState(false);
  const [saveErr, setSaveErr] = useState('');

  const { data: skills = [], isLoading, isError, error, refetch } = useQuery<Skill[]>({
    queryKey: ['admin-skills', filter],
    queryFn: () => apiFetch<Skill[]>(`/skills${filter !== 'all' ? `?visibility=${filter}` : ''}`),
  });

  const deleteMut = useMutation({
    mutationFn: (id: string) => fetch(`${BASE}/skills/${id}`, { method: 'DELETE', headers: { Authorization: `Bearer ${(window as any).__adminToken ?? ''}` } }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['admin-skills'] }),
  });

  const promoteMut = useMutation({
    mutationFn: ({ id, visibility }: { id: string; visibility: string }) =>
      fetch(`${BASE}/skills/${id}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${(window as any).__adminToken ?? ''}` },
        body: JSON.stringify({ visibility }),
      }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['admin-skills'] }),
  });

  async function handleCreate(e: React.FormEvent) {
    e.preventDefault();
    setSaving(true); setSaveErr('');
    try {
      const r = await fetch(`${BASE}/skills`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${(window as any).__adminToken ?? ''}` },
        body: JSON.stringify({ ...form, slug: form.slug || form.name.toLowerCase().replace(/\s+/g, '-').replace(/[^a-z0-9-]/g, ''), tags: form.tags.split(',').map(t => t.trim()).filter(Boolean) }),
      });
      if (!r.ok) { setSaveErr(`Error ${r.status}`); return; }
      qc.invalidateQueries({ queryKey: ['admin-skills'] });
      setCreating(false);
      setForm({ name: '', slug: '', model: 'claude-sonnet-4-6', description: '', system_prompt: '', tags: '', visibility: 'team' });
    } catch (e) { setSaveErr(String(e)); }
    finally { setSaving(false); }
  }

  if (isLoading) return <section className="page"><LoadingState rows={6} /></section>;
  if (isError) return <section className="page"><ErrorState error={error as Error} retry={() => refetch()} /></section>;

  return (
    <section className="page">
      <div className="page__head">
        <div>
          <h1 className="page__title">Skills</h1>
          <p className="page__sub">Reusable AI skills — system prompts + tools packaged for org-wide use · {skills.length} skill{skills.length !== 1 ? 's' : ''}</p>
        </div>
        <div className="page__actions">
          <button className="btn btn--primary" onClick={() => setCreating(true)}>+ New skill</button>
        </div>
      </div>

      <div style={{ display: 'flex', gap: 8, marginBottom: 16 }}>
        {['all', 'org', 'team', 'draft'].map(v => (
          <button key={v} className={`btn btn--sm ${filter === v ? 'btn--primary' : 'btn--ghost'}`} onClick={() => setFilter(v)}>
            {v === 'all' ? 'All' : VISIBILITY_LABELS[v]}
          </button>
        ))}
      </div>

      {creating && (
        <div className="card" style={{ marginBottom: 20, border: '1px solid var(--accent)' }}>
          <div className="card__head"><h3 className="card__title">New skill</h3><button className="btn btn--sm btn--ghost" onClick={() => setCreating(false)}>Cancel</button></div>
          <div className="card__body">
            <form onSubmit={handleCreate} style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
                <div>
                  <label style={{ fontSize: 11.5, color: 'var(--fg-2)', display: 'block', marginBottom: 4 }}>Name *</label>
                  <input className="search" value={form.name} onChange={e => setForm(f => ({ ...f, name: e.target.value }))} placeholder="PR reviewer · Python" required style={{ width: '100%' }} />
                </div>
                <div>
                  <label style={{ fontSize: 11.5, color: 'var(--fg-2)', display: 'block', marginBottom: 4 }}>Model</label>
                  <input className="search" value={form.model} onChange={e => setForm(f => ({ ...f, model: e.target.value }))} placeholder="claude-sonnet-4-6" style={{ width: '100%' }} />
                </div>
              </div>
              <div>
                <label style={{ fontSize: 11.5, color: 'var(--fg-2)', display: 'block', marginBottom: 4 }}>Description</label>
                <input className="search" value={form.description} onChange={e => setForm(f => ({ ...f, description: e.target.value }))} placeholder="What this skill does…" style={{ width: '100%' }} />
              </div>
              <div>
                <label style={{ fontSize: 11.5, color: 'var(--fg-2)', display: 'block', marginBottom: 4 }}>System prompt *</label>
                <textarea value={form.system_prompt} onChange={e => setForm(f => ({ ...f, system_prompt: e.target.value }))} rows={5} required
                  style={{ width: '100%', padding: '8px 10px', background: 'var(--surface)', border: '1px solid var(--rule)', borderRadius: 6, color: 'var(--fg-1)', fontSize: 13, fontFamily: 'var(--font-mono)', resize: 'vertical' }}
                  placeholder="You are a senior engineer…" />
              </div>
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: 12 }}>
                <div>
                  <label style={{ fontSize: 11.5, color: 'var(--fg-2)', display: 'block', marginBottom: 4 }}>Tags (comma-separated)</label>
                  <input className="search" value={form.tags} onChange={e => setForm(f => ({ ...f, tags: e.target.value }))} placeholder="code-review, python" style={{ width: '100%' }} />
                </div>
                <div>
                  <label style={{ fontSize: 11.5, color: 'var(--fg-2)', display: 'block', marginBottom: 4 }}>Visibility</label>
                  <select value={form.visibility} onChange={e => setForm(f => ({ ...f, visibility: e.target.value }))}
                    style={{ width: '100%', padding: '7px 10px', background: 'var(--surface)', border: '1px solid var(--rule)', borderRadius: 6, color: 'var(--fg-1)', fontSize: 13 }}>
                    <option value="draft">Draft</option>
                    <option value="team">Team</option>
                    <option value="org">Org-wide</option>
                  </select>
                </div>
              </div>
              {saveErr && <div style={{ fontSize: 12.5, color: 'var(--bad)' }}>{saveErr}</div>}
              <div><button className="btn btn--primary" type="submit" disabled={saving}>{saving ? 'Creating…' : 'Create skill'}</button></div>
            </form>
          </div>
        </div>
      )}

      <div className="card">
        <div className="card__body" style={{ padding: 0 }}>
          {skills.length === 0 ? (
            <div style={{ padding: '40px 20px', textAlign: 'center', color: 'var(--fg-3)', fontSize: 13 }}>No skills yet. Create the first one above.</div>
          ) : (
            <table className="tbl">
              <thead>
                <tr><th>Name</th><th>Model</th><th>Tags</th><th>Visibility</th><th className="num">Uses</th><th className="num">★</th><th>Author</th><th></th></tr>
              </thead>
              <tbody>
                {skills.map(s => (
                  <tr key={s.id}>
                    <td>
                      <div className="cell-2">
                        <span style={{ fontWeight: 500 }}>{s.name}</span>
                        <span className="lo mono">{s.version} · {s.description.slice(0, 60)}{s.description.length > 60 ? '…' : ''}</span>
                      </div>
                    </td>
                    <td className="mono" style={{ fontSize: 12 }}>{s.model}</td>
                    <td>{s.tags.map(t => <span key={t} className="tag" style={{ marginRight: 4 }}>{t}</span>)}</td>
                    <td>{visibilityPill(s.visibility)}</td>
                    <td className="num mono">{s.uses_total.toLocaleString()}</td>
                    <td className="num mono">{s.stars_avg > 0 ? s.stars_avg.toFixed(1) : '—'}</td>
                    <td style={{ fontSize: 12.5, color: 'var(--fg-2)' }}>{s.author}</td>
                    <td>
                      <div style={{ display: 'flex', gap: 4 }}>
                        {s.visibility !== 'org' && (
                          <button className="btn btn--sm btn--ghost" onClick={() => promoteMut.mutate({ id: s.id, visibility: s.visibility === 'draft' ? 'team' : 'org' })}>
                            {s.visibility === 'draft' ? 'Publish' : 'Promote →'}
                          </button>
                        )}
                        <button className="btn btn--sm btn--ghost" style={{ color: 'var(--bad)' }}
                          onClick={() => { if (confirm(`Delete "${s.name}"?`)) deleteMut.mutate(s.id); }}>
                          Delete
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      </div>
    </section>
  );
}
