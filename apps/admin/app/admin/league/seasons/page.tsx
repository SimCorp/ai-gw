'use client';

import React, { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { LoadingState, ErrorState } from '../../_components/PageStates';
import { apiFetch } from '../../../../lib/apiClient';

const LEAGUE = process.env.NEXT_PUBLIC_LEAGUE_API ?? 'http://localhost:8080/league';

type SeasonStatus = 'upcoming' | 'active' | 'closed';

interface Season {
  id: string;
  name: string;
  status: SeasonStatus;
  starts_at: string;
  ends_at: string;
  season_multiplier: number;
  scoring_weights: Record<string, number>;
}

const STATUS_COLORS: Record<SeasonStatus, string> = {
  upcoming: 'var(--warn, #B45309)',
  active: 'var(--good, #1F8A5B)',
  closed: 'var(--fg-3, #999)',
};

function fmt(iso: string) {
  return new Date(iso).toLocaleDateString('en-GB', { day: 'numeric', month: 'short', year: 'numeric' });
}

function StatusPill({ status }: { status: SeasonStatus }) {
  return (
    <span style={{
      display: 'inline-flex', alignItems: 'center', gap: 5,
      padding: '2px 10px', borderRadius: 20, fontSize: 12, fontWeight: 600,
      background: `color-mix(in srgb, ${STATUS_COLORS[status]} 15%, transparent)`,
      color: STATUS_COLORS[status],
    }}>
      <span style={{ width: 6, height: 6, borderRadius: '50%', background: STATUS_COLORS[status] }} />
      {status}
    </span>
  );
}

interface EditSeasonModalProps {
  season: Season;
  onClose: () => void;
  onSaved: () => void;
}

function EditSeasonModal({ season, onClose, onSaved }: EditSeasonModalProps) {
  const [status, setStatus] = useState<SeasonStatus>(season.status);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');

  // Status transitions are one-way: upcoming → active → closed
  const ALL: SeasonStatus[] = ['upcoming', 'active', 'closed'];
  const minIndex = ALL.indexOf(season.status);
  const allowed = ALL.slice(minIndex);

  async function handleSave() {
    if (status === season.status) { onClose(); return; }
    setSaving(true);
    setError('');
    try {
      const res = await fetch(`${LEAGUE}/seasons/${season.id}/status`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ status }),
      });
      if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(d.detail ?? 'Failed'); }
      onSaved();
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : 'Failed to update season');
    } finally {
      setSaving(false);
    }
  }

  return (
    <div style={{
      position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.5)',
      display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 1000,
    }}>
      <div style={{
        background: 'var(--surface)', border: '1px solid var(--rule)',
        borderRadius: 12, padding: '24px', width: 440, boxShadow: '0 20px 60px rgba(0,0,0,0.4)',
      }}>
        <h2 style={{ margin: '0 0 4px', fontSize: 17, fontWeight: 600 }}>Edit Season</h2>
        <p style={{ margin: '0 0 20px', fontSize: 13, color: 'var(--fg-3)' }}>{season.name}</p>
        {error && (
          <div style={{ marginBottom: 14, padding: '9px 12px', borderRadius: 6, fontSize: 13,
            background: 'rgba(220,38,38,0.1)', border: '1px solid rgba(220,38,38,0.3)', color: '#FCA5A5' }}>
            {error}
          </div>
        )}
        <label style={{ display: 'block', fontSize: 12.5, fontWeight: 500, color: 'var(--fg-2)', marginBottom: 16 }}>
          Status
          <div style={{ marginTop: 8, display: 'flex', gap: 6 }}>
            {ALL.map(s => {
              const disabled = !allowed.includes(s);
              const selected = s === status;
              return (
                <button
                  key={s}
                  type="button"
                  disabled={disabled}
                  onClick={() => !disabled && setStatus(s)}
                  style={{
                    flex: 1, padding: '8px 12px', borderRadius: 6, fontSize: 12.5, fontWeight: 600,
                    border: `1px solid ${selected ? STATUS_COLORS[s] : 'var(--rule)'}`,
                    background: selected ? `color-mix(in srgb, ${STATUS_COLORS[s]} 20%, transparent)` : 'transparent',
                    color: disabled ? 'var(--fg-3)' : (selected ? STATUS_COLORS[s] : 'var(--fg-2)'),
                    cursor: disabled ? 'not-allowed' : 'pointer',
                    opacity: disabled ? 0.5 : 1,
                  }}
                >
                  {s}
                </button>
              );
            })}
          </div>
          <div style={{ fontSize: 11.5, color: 'var(--fg-3)', marginTop: 8 }}>
            {season.status === 'upcoming' && 'Activate to start accepting submissions, or close without activating.'}
            {season.status === 'active' && 'Close the season to finalize the leaderboard. This cannot be undone.'}
            {season.status === 'closed' && 'This season is closed — no further changes possible.'}
          </div>
        </label>
        <div style={{ display: 'flex', gap: 10, justifyContent: 'flex-end' }}>
          <button onClick={onClose} style={{
            padding: '8px 16px', borderRadius: 6, border: '1px solid var(--rule)',
            background: 'transparent', color: 'var(--fg-2)', cursor: 'pointer', fontSize: 13,
          }}>Cancel</button>
          <button
            onClick={handleSave}
            disabled={saving || status === season.status || season.status === 'closed'}
            style={{
              padding: '8px 18px', borderRadius: 6, border: 'none',
              background: 'var(--sc-blue, #083EA7)', color: '#fff',
              cursor: (saving || status === season.status || season.status === 'closed') ? 'not-allowed' : 'pointer',
              fontSize: 13, fontWeight: 600,
              opacity: (saving || status === season.status || season.status === 'closed') ? 0.5 : 1,
            }}
          >{saving ? 'Saving…' : 'Save changes'}</button>
        </div>
      </div>
    </div>
  );
}

interface CreateSeasonModalProps {
  onClose: () => void;
  onSaved: () => void;
}

function CreateSeasonModal({ onClose, onSaved }: CreateSeasonModalProps) {
  const today = new Date().toISOString().split('T')[0];
  const [form, setForm] = useState({
    name: '',
    starts_at: today,
    ends_at: '',
    season_multiplier: '1.0',
  });
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');

  async function handleSave() {
    if (!form.name || !form.starts_at || !form.ends_at) {
      setError('Name, start date, and end date are required');
      return;
    }
    setSaving(true);
    setError('');
    try {
      const res = await fetch(`${LEAGUE}/seasons`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          ...form,
          starts_at: new Date(form.starts_at).toISOString(),
          ends_at: new Date(form.ends_at).toISOString(),
          season_multiplier: parseFloat(form.season_multiplier),
        }),
      });
      if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(d.detail ?? 'Failed'); }
      onSaved();
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : 'Failed to create season');
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
        borderRadius: 12, padding: '24px', width: 440, boxShadow: '0 20px 60px rgba(0,0,0,0.4)',
      }}>
        <h2 style={{ margin: '0 0 20px', fontSize: 17, fontWeight: 600 }}>New Season</h2>
        {error && (
          <div style={{ marginBottom: 14, padding: '9px 12px', borderRadius: 6, fontSize: 13,
            background: 'rgba(220,38,38,0.1)', border: '1px solid rgba(220,38,38,0.3)', color: '#FCA5A5' }}>
            {error}
          </div>
        )}
        <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
          <label style={{ fontSize: 12.5, fontWeight: 500, color: 'var(--fg-2)' }}>
            Season name
            <input value={form.name} onChange={e => setForm(f => ({ ...f, name: e.target.value }))}
              placeholder="Q3 2026" style={{ ...inputStyle, marginTop: 5 }} />
          </label>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10 }}>
            <label style={{ fontSize: 12.5, fontWeight: 500, color: 'var(--fg-2)' }}>
              Start date
              <input type="date" value={form.starts_at}
                onChange={e => setForm(f => ({ ...f, starts_at: e.target.value }))}
                style={{ ...inputStyle, marginTop: 5 }} />
            </label>
            <label style={{ fontSize: 12.5, fontWeight: 500, color: 'var(--fg-2)' }}>
              End date
              <input type="date" value={form.ends_at}
                onChange={e => setForm(f => ({ ...f, ends_at: e.target.value }))}
                style={{ ...inputStyle, marginTop: 5 }} />
            </label>
          </div>
          <label style={{ fontSize: 12.5, fontWeight: 500, color: 'var(--fg-2)' }}>
            Point multiplier
            <input type="number" min="0.1" max="5" step="0.1" value={form.season_multiplier}
              onChange={e => setForm(f => ({ ...f, season_multiplier: e.target.value }))}
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
          }}>{saving ? 'Creating…' : 'Create season'}</button>
        </div>
      </div>
    </div>
  );
}

export default function SeasonsPage() {
  const qc = useQueryClient();
  const [showCreate, setShowCreate] = useState(false);
  const [editing, setEditing] = useState<Season | null>(null);

  const { data, isLoading, error } = useQuery<Season[]>({
    queryKey: ['league-seasons'],
    queryFn: () => fetch(`${LEAGUE}/seasons`).then(r => r.json()),
  });

  const seasons = Array.isArray(data) ? data : (data as { seasons?: Season[] })?.seasons ?? [];

  if (isLoading) return <LoadingState />;
  if (error) return <ErrorState message="Could not load seasons" />;

  return (
    <div className="page">
      <div className="page__header">
        <div>
          <h1 className="page__title">Seasons</h1>
          <p className="page__sub">Manage AI-League competition seasons</p>
        </div>
        <button
          onClick={() => setShowCreate(true)}
          className="btn btn--primary"
        >+ New season</button>
      </div>

      {seasons.length === 0 ? (
        <div style={{
          textAlign: 'center', padding: '60px 20px',
          border: '1px dashed var(--rule)', borderRadius: 10, color: 'var(--fg-3)',
        }}>
          <div style={{ fontSize: 36, marginBottom: 12 }}>🏆</div>
          <div style={{ fontWeight: 600, marginBottom: 6 }}>No seasons yet</div>
          <div style={{ fontSize: 13 }}>Create the first AI-League season to get started</div>
        </div>
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
          {seasons.map((s) => (
            <div key={s.id} style={{
              background: 'var(--surface)', border: '1px solid var(--rule)',
              borderRadius: 10, padding: '18px 20px',
              display: 'flex', alignItems: 'center', gap: 20,
            }}>
              <div style={{ flex: 1 }}>
                <div style={{ fontWeight: 600, fontSize: 15, marginBottom: 4 }}>{s.name}</div>
                <div style={{ fontSize: 12.5, color: 'var(--fg-3)' }}>
                  {fmt(s.starts_at)} → {fmt(s.ends_at)} · {s.season_multiplier}× multiplier
                </div>
              </div>
              <StatusPill status={s.status} />
              <button
                onClick={() => setEditing(s)}
                disabled={s.status === 'closed'}
                style={{
                  padding: '6px 14px', borderRadius: 6, border: '1px solid var(--rule)',
                  background: 'transparent',
                  color: s.status === 'closed' ? 'var(--fg-3)' : 'var(--fg-2)',
                  cursor: s.status === 'closed' ? 'not-allowed' : 'pointer',
                  fontSize: 12.5,
                  opacity: s.status === 'closed' ? 0.5 : 1,
                }}
              >Edit</button>
            </div>
          ))}
        </div>
      )}

      {showCreate && (
        <CreateSeasonModal
          onClose={() => setShowCreate(false)}
          onSaved={() => { setShowCreate(false); qc.invalidateQueries({ queryKey: ['league-seasons'] }); }}
        />
      )}

      {editing && (
        <EditSeasonModal
          season={editing}
          onClose={() => setEditing(null)}
          onSaved={() => { setEditing(null); qc.invalidateQueries({ queryKey: ['league-seasons'] }); }}
        />
      )}
    </div>
  );
}
