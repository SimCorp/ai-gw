'use client';

import { useState, useEffect, useCallback } from 'react';
import { useRouter } from 'next/navigation';
import { useTeam } from '../_lib/teamContext';
import { useAuth } from '../_lib/authContext';

const BASE = process.env.NEXT_PUBLIC_ADMIN_BASE_URL ?? 'http://localhost:8005';

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
  visibility: string;
  author: string;
  uses_total: number;
  stars_avg: number;
}

export default function SkillsPage() {
  const { teamId } = useTeam();
  const { token } = useAuth();
  const router = useRouter();
  const [skills, setSkills] = useState<Skill[]>([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState('');
  const [expanded, setExpanded] = useState<string | null>(null);
  const [using, setUsing] = useState<string | null>(null);

  useEffect(() => {
    if (!token) return;
    const url = teamId ? `${BASE}/skills?team_id=${teamId}` : `${BASE}/skills?visibility=org`;
    fetch(url, { headers: { Authorization: `Bearer ${token}` } })
      .then(r => r.ok ? r.json() : [])
      .then((data: Skill[]) => setSkills(Array.isArray(data) ? data : []))
      .catch(() => setSkills([]))
      .finally(() => setLoading(false));
  }, [token, teamId]);

  const handleUse = useCallback(async (skill: Skill) => {
    setUsing(skill.id);
    try {
      await fetch(`${BASE}/skills/${skill.id}/use`, {
        method: 'POST',
        headers: { Authorization: `Bearer ${token}` },
      });
    } catch { /* best-effort */ }
    const params = new URLSearchParams({ skill_system_prompt: skill.system_prompt, skill_name: skill.name });
    router.push(`/playground?${params.toString()}`);
  }, [token, router]);

  const filtered = skills.filter(s =>
    !search || s.name.toLowerCase().includes(search.toLowerCase()) ||
    s.description.toLowerCase().includes(search.toLowerCase()) ||
    s.tags.some(t => t.toLowerCase().includes(search.toLowerCase()))
  );

  return (
    <main className="pmain">
      <div className="phero">
        <div>
          <h1>Skills</h1>
          <p>Reusable AI skills — pre-configured system prompts and tool bundles ready to use in the Playground.</p>
        </div>
      </div>

      <div style={{ display: 'flex', gap: 8, marginBottom: 20 }}>
        <input
          className="search"
          type="search"
          placeholder="Search skills…"
          value={search}
          onChange={e => setSearch(e.target.value)}
          style={{ maxWidth: 360 }}
        />
        <span style={{ fontSize: 13, color: 'var(--fg-3)', alignSelf: 'center', marginLeft: 8 }}>
          {loading ? 'Loading…' : `${filtered.length} skill${filtered.length !== 1 ? 's' : ''}`}
        </span>
      </div>

      {!loading && filtered.length === 0 && (
        <div className="card">
          <div className="card__body" style={{ textAlign: 'center', padding: '48px 20px', color: 'var(--fg-3)', fontSize: 13 }}>
            {skills.length === 0 ? 'No skills published yet. Ask your admin to create the first one.' : 'No skills match your search.'}
          </div>
        </div>
      )}

      <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
        {filtered.map(s => (
          <div key={s.id} className="card">
            <div className="card__head" style={{ alignItems: 'flex-start' }}>
              <div style={{ flex: 1, minWidth: 0 }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
                  <span style={{ fontWeight: 600, fontSize: 14 }}>{s.name}</span>
                  <span className="pill pill--info" style={{ fontSize: 11 }}>{s.version}</span>
                  {s.visibility === 'org' && <span className="pill pill--good" style={{ fontSize: 11 }}>org-wide</span>}
                </div>
                <div style={{ fontSize: 12.5, color: 'var(--fg-2)', marginTop: 4 }}>{s.description}</div>
                <div style={{ display: 'flex', gap: 6, marginTop: 6, flexWrap: 'wrap', alignItems: 'center' }}>
                  <span className="mono" style={{ fontSize: 11.5, color: 'var(--fg-3)' }}>{s.model}</span>
                  {s.tools.length > 0 && (
                    <><span style={{ color: 'var(--fg-3)', fontSize: 11 }}>·</span>
                    <span style={{ fontSize: 11.5, color: 'var(--fg-3)' }}>{s.tools.length} tool{s.tools.length !== 1 ? 's' : ''}</span></>
                  )}
                  {s.uses_total > 0 && (
                    <><span style={{ color: 'var(--fg-3)', fontSize: 11 }}>·</span>
                    <span style={{ fontSize: 11.5, color: 'var(--fg-3)' }}>{s.uses_total.toLocaleString()} uses</span></>
                  )}
                  {s.tags.map(t => <span key={t} className="tag" style={{ fontSize: 11 }}>{t}</span>)}
                </div>
              </div>
              <div style={{ display: 'flex', gap: 6, flexShrink: 0 }}>
                <button className="btn btn--sm btn--ghost" onClick={() => setExpanded(expanded === s.id ? null : s.id)}>
                  {expanded === s.id ? 'Hide prompt ▲' : 'Preview ▼'}
                </button>
                <button
                  className="btn btn--sm btn--primary"
                  onClick={() => handleUse(s)}
                  disabled={using === s.id}
                >
                  {using === s.id ? 'Opening…' : '▶ Use'}
                </button>
              </div>
            </div>
            {expanded === s.id && (
              <div className="card__body" style={{ borderTop: '1px solid var(--rule)' }}>
                <div className="microlabel" style={{ marginBottom: 6 }}>System prompt</div>
                <pre style={{ margin: 0, padding: '10px 14px', background: 'var(--surface-soft)', borderRadius: 8, fontSize: 12.5, fontFamily: 'var(--font-mono)', lineHeight: 1.5, whiteSpace: 'pre-wrap', wordBreak: 'break-word', color: 'var(--fg-2)' }}>
                  {s.system_prompt || '(no system prompt)'}
                </pre>
              </div>
            )}
          </div>
        ))}
      </div>
    </main>
  );
}
