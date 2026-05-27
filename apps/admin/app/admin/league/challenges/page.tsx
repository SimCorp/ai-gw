'use client';

import React, { useState } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { LoadingState, ErrorState } from '../../_components/PageStates';

const LEAGUE = process.env.NEXT_PUBLIC_LEAGUE_API ?? 'http://localhost:8080/league';

type ChallengeStatus = 'draft' | 'active' | 'closed';

interface Challenge {
  id: string;
  season_id: string;
  title: string;
  goal: string;
  status: ChallengeStatus;
  max_league_attempts: number;
  scores_revealed_at: string | null;
}

interface Season {
  id: string;
  name: string;
  status: string;
}

const STATUS_COLORS: Record<ChallengeStatus, string> = {
  draft: 'var(--fg-3)',
  active: 'var(--good, #1F8A5B)',
  closed: 'var(--warn, #B45309)',
};

function StatusPill({ status }: { status: ChallengeStatus }) {
  return (
    <span style={{
      display: 'inline-flex', alignItems: 'center', gap: 5,
      padding: '2px 10px', borderRadius: 20, fontSize: 12, fontWeight: 600,
      background: `color-mix(in srgb, ${STATUS_COLORS[status]} 15%, transparent)`,
      color: STATUS_COLORS[status],
    }}>
      {status}
    </span>
  );
}

interface CreateChallengeModalProps {
  seasons: Season[];
  onClose: () => void;
  onSaved: () => void;
}

function CreateChallengeModal({ seasons, onClose, onSaved }: CreateChallengeModalProps) {
  const [form, setForm] = useState({
    season_id: seasons[0]?.id ?? '',
    title: '',
    goal: '',
    max_league_attempts: '3',
    allowed_models: 'claude-sonnet-4-6',
    max_tokens_budget: '4096',
  });
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');

  async function handleSave() {
    if (!form.season_id || !form.title || !form.goal) {
      setError('Season, title, and goal are required');
      return;
    }
    setSaving(true);
    setError('');
    try {
      const res = await fetch(`${LEAGUE}/seasons/${form.season_id}/challenges`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          title: form.title,
          goal: form.goal,
          max_league_attempts: parseInt(form.max_league_attempts),
          max_tokens_budget: parseInt(form.max_tokens_budget),
          allowed_models: form.allowed_models.split(',').map(s => s.trim()).filter(Boolean),
          training_inputs: [],
          hidden_test_suite: [],
        }),
      });
      if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(d.detail ?? 'Failed'); }
      onSaved();
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : 'Failed to create challenge');
    } finally {
      setSaving(false);
    }
  }

  const inputStyle: React.CSSProperties = {
    width: '100%', boxSizing: 'border-box',
    padding: '8px 10px', fontSize: 13,
    background: 'var(--bg)', border: '1px solid var(--rule)',
    borderRadius: 6, color: 'var(--fg-1)',
  };

  return (
    <div style={{
      position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.5)',
      display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 1000,
    }}>
      <div style={{
        background: 'var(--surface)', border: '1px solid var(--rule)',
        borderRadius: 12, padding: '24px', width: 520, boxShadow: '0 20px 60px rgba(0,0,0,0.4)',
        maxHeight: '80vh', overflowY: 'auto',
      }}>
        <h2 style={{ margin: '0 0 20px', fontSize: 17, fontWeight: 600 }}>New Challenge</h2>
        {error && (
          <div style={{ marginBottom: 14, padding: '9px 12px', borderRadius: 6, fontSize: 13,
            background: 'rgba(220,38,38,0.1)', border: '1px solid rgba(220,38,38,0.3)', color: '#FCA5A5' }}>
            {error}
          </div>
        )}
        <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
          <label style={{ fontSize: 12.5, fontWeight: 500, color: 'var(--fg-2)' }}>
            Season
            <select value={form.season_id} onChange={e => setForm(f => ({ ...f, season_id: e.target.value }))}
              style={{ ...inputStyle, marginTop: 5 }}>
              {seasons.map(s => <option key={s.id} value={s.id}>{s.name}</option>)}
            </select>
          </label>
          <label style={{ fontSize: 12.5, fontWeight: 500, color: 'var(--fg-2)' }}>
            Title
            <input value={form.title} onChange={e => setForm(f => ({ ...f, title: e.target.value }))}
              placeholder="e.g. Code Review Agent" style={{ ...inputStyle, marginTop: 5 }} />
          </label>
          <label style={{ fontSize: 12.5, fontWeight: 500, color: 'var(--fg-2)' }}>
            Goal (visible to engineers)
            <textarea value={form.goal} onChange={e => setForm(f => ({ ...f, goal: e.target.value }))}
              rows={3} placeholder="Describe what the agent must achieve..."
              style={{ ...inputStyle, marginTop: 5, resize: 'vertical' }} />
          </label>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10 }}>
            <label style={{ fontSize: 12.5, fontWeight: 500, color: 'var(--fg-2)' }}>
              Max attempts
              <input type="number" min="1" max="10" value={form.max_league_attempts}
                onChange={e => setForm(f => ({ ...f, max_league_attempts: e.target.value }))}
                style={{ ...inputStyle, marginTop: 5 }} />
            </label>
            <label style={{ fontSize: 12.5, fontWeight: 500, color: 'var(--fg-2)' }}>
              Token budget
              <input type="number" min="512" max="32768" step="512" value={form.max_tokens_budget}
                onChange={e => setForm(f => ({ ...f, max_tokens_budget: e.target.value }))}
                style={{ ...inputStyle, marginTop: 5 }} />
            </label>
          </div>
          <label style={{ fontSize: 12.5, fontWeight: 500, color: 'var(--fg-2)' }}>
            Allowed models (comma-separated)
            <input value={form.allowed_models}
              onChange={e => setForm(f => ({ ...f, allowed_models: e.target.value }))}
              style={{ ...inputStyle, marginTop: 5 }} />
          </label>
        </div>
        <div style={{ display: 'flex', gap: 10, marginTop: 22, justifyContent: 'flex-end' }}>
          <button onClick={onClose} style={{
            padding: '8px 16px', borderRadius: 6, border: '1px solid var(--rule)',
            background: 'transparent', color: 'var(--fg-2)', cursor: 'pointer', fontSize: 13,
          }}>Cancel</button>
          <button onClick={handleSave} disabled={saving} style={{
            padding: '8px 18px', borderRadius: 6, border: 'none',
            background: 'var(--sc-blue, #083EA7)', color: '#fff', cursor: saving ? 'not-allowed' : 'pointer',
            fontSize: 13, fontWeight: 600, opacity: saving ? 0.7 : 1,
          }}>{saving ? 'Creating…' : 'Create challenge'}</button>
        </div>
      </div>
    </div>
  );
}

export default function ChallengesPage() {
  const qc = useQueryClient();
  const [showCreate, setShowCreate] = useState(false);
  const [filterSeason, setFilterSeason] = useState('all');

  const { data: seasonsData } = useQuery<Season[]>({
    queryKey: ['league-seasons'],
    queryFn: () => fetch(`${LEAGUE}/seasons`).then(r => r.json()),
  });

  const seasons = Array.isArray(seasonsData) ? seasonsData : (seasonsData as { seasons?: Season[] })?.seasons ?? [];

  // No "all seasons" endpoint exists — fan out across seasons when filter is "all"
  const { data, isLoading, error } = useQuery<Challenge[]>({
    queryKey: ['league-challenges', filterSeason, seasons.map(s => s.id).join(',')],
    enabled: filterSeason !== 'all' || seasons.length > 0,
    queryFn: async () => {
      if (filterSeason !== 'all') {
        return fetch(`${LEAGUE}/seasons/${filterSeason}/challenges`).then(r => r.json());
      }
      const lists = await Promise.all(
        seasons.map(s =>
          fetch(`${LEAGUE}/seasons/${s.id}/challenges`).then(r => r.ok ? r.json() : [])
        )
      );
      return lists.flat();
    },
  });

  const challenges = Array.isArray(data) ? data : (data as { challenges?: Challenge[] })?.challenges ?? [];

  if (isLoading) return <LoadingState />;
  if (error) return <ErrorState message="Could not load challenges" />;

  return (
    <div className="page">
      <div className="page__header">
        <div>
          <h1 className="page__title">Challenge Builder</h1>
          <p className="page__sub">Create and manage AI-League challenges</p>
        </div>
        <div style={{ display: 'flex', gap: 10, alignItems: 'center' }}>
          <select
            value={filterSeason}
            onChange={e => setFilterSeason(e.target.value)}
            style={{
              padding: '7px 12px', borderRadius: 6, border: '1px solid var(--rule)',
              background: 'var(--surface)', color: 'var(--fg-1)', fontSize: 13,
            }}
          >
            <option value="all">All seasons</option>
            {seasons.map(s => <option key={s.id} value={s.id}>{s.name}</option>)}
          </select>
          <button onClick={() => setShowCreate(true)} className="btn btn--primary">
            + New challenge
          </button>
        </div>
      </div>

      {challenges.length === 0 ? (
        <div style={{
          textAlign: 'center', padding: '60px 20px',
          border: '1px dashed var(--rule)', borderRadius: 10, color: 'var(--fg-3)',
        }}>
          <div style={{ fontSize: 36, marginBottom: 12 }}>⚔️</div>
          <div style={{ fontWeight: 600, marginBottom: 6 }}>No challenges yet</div>
          <div style={{ fontSize: 13 }}>Create the first challenge for this season</div>
        </div>
      ) : (
        <div style={{ display: 'grid', gap: 10 }}>
          {challenges.map((c) => (
            <div key={c.id} style={{
              background: 'var(--surface)', border: '1px solid var(--rule)',
              borderRadius: 10, padding: '18px 20px',
              display: 'flex', alignItems: 'flex-start', gap: 16,
            }}>
              <div style={{
                width: 40, height: 40, borderRadius: 8, flexShrink: 0,
                background: 'rgba(8,62,167,0.15)',
                display: 'flex', alignItems: 'center', justifyContent: 'center',
                fontSize: 18,
              }}>⚔️</div>
              <div style={{ flex: 1, minWidth: 0 }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 6 }}>
                  <span style={{ fontWeight: 600, fontSize: 14 }}>{c.title}</span>
                  <StatusPill status={c.status} />
                </div>
                <div style={{ fontSize: 12.5, color: 'var(--fg-3)', marginBottom: 4 }}>{c.goal}</div>
                <div style={{ fontSize: 11.5, color: 'var(--fg-3)' }}>
                  {c.max_league_attempts} attempts allowed
                  {c.scores_revealed_at && ` · Scores revealed ${new Date(c.scores_revealed_at).toLocaleDateString()}`}
                </div>
              </div>
              <div style={{ display: 'flex', gap: 8, flexShrink: 0 }}>
                <button style={{
                  padding: '6px 14px', borderRadius: 6, border: '1px solid var(--rule)',
                  background: 'transparent', color: 'var(--fg-2)', cursor: 'pointer', fontSize: 12.5,
                }}>Edit</button>
                {c.status === 'draft' && (
                  <button style={{
                    padding: '6px 14px', borderRadius: 6, border: 'none',
                    background: 'var(--good, #1F8A5B)', color: '#fff', cursor: 'pointer', fontSize: 12.5, fontWeight: 600,
                  }}>Publish</button>
                )}
              </div>
            </div>
          ))}
        </div>
      )}

      {showCreate && (
        <CreateChallengeModal
          seasons={seasons}
          onClose={() => setShowCreate(false)}
          onSaved={() => { setShowCreate(false); qc.invalidateQueries({ queryKey: ['league-challenges'] }); }}
        />
      )}
    </div>
  );
}
