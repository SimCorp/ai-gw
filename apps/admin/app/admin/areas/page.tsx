'use client';

import React, { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { LoadingState, ErrorState, EmptyState } from '../_components/PageStates';

const BASE = 'http://localhost:8005';

const PRESET_COLORS = [
  { value: '#0A7BD7', label: 'Blue' },
  { value: '#1D958E', label: 'Teal' },
  { value: '#4B17B6', label: 'Purple' },
  { value: '#EF3E4A', label: 'Red' },
  { value: '#FB9B2A', label: 'Orange' },
  { value: '#1A7A3C', label: 'Green' },
];

const EMBEDDING_MODELS = [
  'text-embedding-3-small',
  'text-embedding-3-large',
  'text-embedding-ada-002',
];

const POLICY_DEFAULTS = {
  cache_ttl_seconds: 3600,
  cache_similarity_threshold: 0.95,
  cache_opt_out: false,
  embedding_model: 'text-embedding-3-small',
  rate_limit_rpm: 1000,
  allowed_models: [] as string[],
};

interface Area {
  id: string;
  name: string;
  slug: string;
  description: string | null;
  color: string;
  team_count: number;
  has_policy: boolean;
  created_at?: string;
}

interface Team {
  id: string;
  name: string;
  slug: string;
  area_id: string | null;
  area_name: string | null;
}

interface Model {
  id: string;
  name: string;
  model_id: string;
  provider: string;
  enabled: boolean;
}

interface AreaPolicy {
  cache_ttl_seconds: number;
  cache_similarity_threshold: number;
  cache_opt_out: boolean;
  embedding_model: string;
  rate_limit_rpm: number;
  allowed_models: string[];
  updated_at: string | null;
}

function formatDate(iso: string | null | undefined) {
  if (!iso) return '—';
  return new Date(iso).toLocaleDateString('en-GB', { day: 'numeric', month: 'short', year: 'numeric' });
}

function formatTtl(secs: number) {
  if (secs >= 86400) return `${secs / 86400}d`;
  if (secs >= 3600) return `${secs / 3600}h`;
  if (secs >= 60) return `${secs / 60}m`;
  return `${secs}s`;
}

function toSlug(name: string): string {
  return name.trim().toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '');
}

// ── Policy modal ───────────────────────────────────────────────────────────

interface PolicyModalProps {
  area: Area;
  models: Model[];
  onClose: () => void;
  onSaved: () => void;
}

function PolicyModal({ area, models, onClose, onSaved }: PolicyModalProps) {
  const policyQuery = useQuery<AreaPolicy | Record<string, never>>({
    queryKey: ['area-policy', area.id],
    queryFn: () => fetch(`${BASE}/areas/${area.id}/policy`).then(r => r.json()),
  });

  const existing = policyQuery.data && 'cache_ttl_seconds' in policyQuery.data
    ? policyQuery.data as AreaPolicy
    : null;

  const [form, setForm] = useState<typeof POLICY_DEFAULTS>(() => ({
    cache_ttl_seconds: POLICY_DEFAULTS.cache_ttl_seconds,
    cache_similarity_threshold: POLICY_DEFAULTS.cache_similarity_threshold,
    cache_opt_out: POLICY_DEFAULTS.cache_opt_out,
    embedding_model: POLICY_DEFAULTS.embedding_model,
    rate_limit_rpm: POLICY_DEFAULTS.rate_limit_rpm,
    allowed_models: [],
  }));
  const [formInitialized, setFormInitialized] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Pre-fill form once policy data is loaded
  React.useEffect(() => {
    if (!policyQuery.isLoading && !formInitialized) {
      if (existing) {
        setForm({
          cache_ttl_seconds: existing.cache_ttl_seconds,
          cache_similarity_threshold: existing.cache_similarity_threshold,
          cache_opt_out: existing.cache_opt_out,
          embedding_model: existing.embedding_model,
          rate_limit_rpm: existing.rate_limit_rpm,
          allowed_models: existing.allowed_models,
        });
      }
      setFormInitialized(true);
    }
  }, [policyQuery.isLoading, existing, formInitialized]);

  const toggleModel = (modelId: string) => {
    setForm(f => ({
      ...f,
      allowed_models: f.allowed_models.includes(modelId)
        ? f.allowed_models.filter(m => m !== modelId)
        : [...f.allowed_models, modelId],
    }));
  };

  const save = async () => {
    setSaving(true);
    setError(null);
    try {
      const res = await fetch(`${BASE}/areas/${area.id}/policy`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(form),
      });
      if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        setError((body as { detail?: string }).detail ?? `Error ${res.status}`);
        return;
      }
      onSaved();
      onClose();
    } catch (e) {
      setError(String(e));
    } finally {
      setSaving(false);
    }
  };

  const field = (label: string, children: React.ReactNode) => (
    <div style={{ marginBottom: 16 }}>
      <label style={{ display: 'block', fontSize: 12.5, color: 'var(--fg-2)', marginBottom: 5 }}>{label}</label>
      {children}
    </div>
  );

  const inputStyle: React.CSSProperties = {
    width: '100%', padding: '7px 10px', fontSize: 13,
    background: 'var(--surface-2)', border: '1px solid var(--rule)',
    borderRadius: 6, color: 'var(--fg-1)', fontFamily: 'inherit',
  };

  return (
    <div
      style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.55)', zIndex: 300, display: 'flex', alignItems: 'center', justifyContent: 'center' }}
      onClick={e => { if (e.target === e.currentTarget) onClose(); }}
    >
      <div style={{
        background: 'var(--surface)', border: '1px solid var(--rule)',
        borderRadius: 12, padding: 28, width: 520, maxWidth: '95vw', maxHeight: '90vh', overflowY: 'auto',
      }}>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 20 }}>
          <div>
            <h3 style={{ margin: 0, fontSize: 15, display: 'flex', alignItems: 'center', gap: 8 }}>
              <span style={{ display: 'inline-block', width: 10, height: 10, borderRadius: 3, background: area.color }} />
              Policy — {area.name}
            </h3>
            <div style={{ fontSize: 12, color: 'var(--fg-3)', marginTop: 3 }}>
              {policyQuery.isLoading
                ? 'Loading…'
                : existing
                  ? `Last updated ${formatDate(existing.updated_at)}`
                  : '(inherited from org defaults)'}
            </div>
          </div>
          <button onClick={onClose} style={{ background: 'none', border: 0, cursor: 'pointer', fontSize: 18, color: 'var(--fg-3)' }}>✕</button>
        </div>

        {policyQuery.isLoading ? (
          <LoadingState rows={5} />
        ) : (
          <>
            {field('Cache TTL (seconds)', (
              <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
                <input
                  type="number" min={0} style={{ ...inputStyle, flex: 1 }}
                  value={form.cache_ttl_seconds}
                  onChange={e => setForm(f => ({ ...f, cache_ttl_seconds: Number(e.target.value) }))}
                />
                <span style={{ fontSize: 12.5, color: 'var(--fg-3)', whiteSpace: 'nowrap' }}>{formatTtl(form.cache_ttl_seconds)}</span>
              </div>
            ))}

            {field('Semantic similarity threshold (0–1)', (
              <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
                <input
                  type="range" min={0.5} max={1} step={0.01}
                  style={{ flex: 1 }}
                  value={form.cache_similarity_threshold}
                  onChange={e => setForm(f => ({ ...f, cache_similarity_threshold: Number(e.target.value) }))}
                />
                <span style={{ fontSize: 13, fontFamily: 'var(--font-mono, monospace)', width: 40, textAlign: 'right' }}>
                  {form.cache_similarity_threshold.toFixed(2)}
                </span>
              </div>
            ))}

            {field('Rate limit (requests / minute)', (
              <input
                type="number" min={1} style={inputStyle}
                value={form.rate_limit_rpm}
                onChange={e => setForm(f => ({ ...f, rate_limit_rpm: Number(e.target.value) }))}
              />
            ))}

            {field('Embedding model', (
              <select
                style={inputStyle}
                value={form.embedding_model}
                onChange={e => setForm(f => ({ ...f, embedding_model: e.target.value }))}
              >
                {EMBEDDING_MODELS.map(m => <option key={m} value={m}>{m}</option>)}
              </select>
            ))}

            {field('Allowed models (empty = all models permitted)', (
              <div style={{ display: 'flex', flexDirection: 'column', gap: 6, maxHeight: 180, overflowY: 'auto' }}>
                {models.filter(m => m.enabled).map(m => (
                  <label key={m.id} style={{ display: 'flex', alignItems: 'center', gap: 8, cursor: 'pointer', fontSize: 13 }}>
                    <input
                      type="checkbox"
                      checked={form.allowed_models.includes(m.model_id)}
                      onChange={() => toggleModel(m.model_id)}
                    />
                    <span>{m.name}</span>
                    <span style={{ fontSize: 11.5, color: 'var(--fg-3)', fontFamily: 'monospace' }}>{m.model_id}</span>
                  </label>
                ))}
                {models.filter(m => m.enabled).length === 0 && (
                  <span style={{ fontSize: 12.5, color: 'var(--fg-3)' }}>No enabled models found</span>
                )}
              </div>
            ))}

            {field('Cache opt-out', (
              <label style={{ display: 'flex', alignItems: 'center', gap: 8, cursor: 'pointer', fontSize: 13 }}>
                <input
                  type="checkbox"
                  checked={form.cache_opt_out}
                  onChange={e => setForm(f => ({ ...f, cache_opt_out: e.target.checked }))}
                />
                Disable semantic cache for this area
              </label>
            ))}

            {error && <p style={{ color: 'var(--bad)', fontSize: 12.5, margin: '0 0 12px' }}>{error}</p>}

            <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end', paddingTop: 8, borderTop: '1px solid var(--rule)' }}>
              <button className="btn btn--sm btn--ghost" onClick={onClose}>Cancel</button>
              <button className="btn btn--sm btn--primary" onClick={save} disabled={saving}>
                {saving ? 'Saving…' : 'Save policy'}
              </button>
            </div>
          </>
        )}
      </div>
    </div>
  );
}

// ── Manage teams modal ─────────────────────────────────────────────────────

interface ManageTeamsModalProps {
  area: Area;
  onClose: () => void;
  onChanged: () => void;
}

function ManageTeamsModal({ area, onClose, onChanged }: ManageTeamsModalProps) {
  const queryClient = useQueryClient();
  const [selectedAdd, setSelectedAdd] = useState('');
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const allTeamsQuery = useQuery<Team[]>({
    queryKey: ['teams'],
    queryFn: () => fetch(`${BASE}/teams`).then(r => r.json()),
    staleTime: 30_000,
  });

  const areaTeamsQuery = useQuery<{ area: Area; teams: Team[] }>({
    queryKey: ['area-teams', area.id],
    queryFn: () => fetch(`${BASE}/areas/${area.id}`).then(r => r.json()),
  });

  const allTeams = allTeamsQuery.data ?? [];
  const areaTeams = areaTeamsQuery.data?.teams ?? [];
  const areaTeamIds = new Set(areaTeams.map(t => t.id));

  // Teams not currently in this area
  const available = allTeams.filter(t => !areaTeamIds.has(t.id));

  const assignTeam = useMutation({
    mutationFn: async (teamId: string) => {
      const team = allTeams.find(t => t.id === teamId)!;
      const res = await fetch(`${BASE}/teams/${teamId}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name: team.name, slug: team.slug, area_id: area.id }),
      });
      if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        throw new Error((body as { detail?: string }).detail ?? `Error ${res.status}`);
      }
    },
    onSuccess: () => {
      setSelectedAdd('');
      queryClient.invalidateQueries({ queryKey: ['area-teams', area.id] });
      queryClient.invalidateQueries({ queryKey: ['teams'] });
      queryClient.invalidateQueries({ queryKey: ['areas'] });
      onChanged();
    },
    onError: (e: Error) => setError(e.message),
  });

  const unassignTeam = useMutation({
    mutationFn: async (team: Team) => {
      const res = await fetch(`${BASE}/teams/${team.id}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name: team.name, slug: team.slug, area_id: null }),
      });
      if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        throw new Error((body as { detail?: string }).detail ?? `Error ${res.status}`);
      }
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['area-teams', area.id] });
      queryClient.invalidateQueries({ queryKey: ['teams'] });
      queryClient.invalidateQueries({ queryKey: ['areas'] });
      onChanged();
    },
    onError: (e: Error) => setError(e.message),
  });

  const handleAdd = async () => {
    if (!selectedAdd) return;
    setError(null);
    setBusy(selectedAdd);
    try { await assignTeam.mutateAsync(selectedAdd); } finally { setBusy(null); }
  };

  const handleRemove = async (team: Team) => {
    setError(null);
    setBusy(team.id);
    try { await unassignTeam.mutateAsync(team); } finally { setBusy(null); }
  };

  const inputStyle: React.CSSProperties = {
    flex: 1, padding: '7px 10px', fontSize: 13,
    background: 'var(--surface-2)', border: '1px solid var(--rule)',
    borderRadius: 6, color: 'var(--fg-1)', fontFamily: 'inherit',
  };

  return (
    <div
      style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.55)', zIndex: 300, display: 'flex', alignItems: 'center', justifyContent: 'center' }}
      onClick={e => { if (e.target === e.currentTarget) onClose(); }}
    >
      <div style={{
        background: 'var(--surface)', border: '1px solid var(--rule)',
        borderRadius: 12, padding: 28, width: 500, maxWidth: '95vw', maxHeight: '85vh',
        display: 'flex', flexDirection: 'column', gap: 0,
      }}>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 20 }}>
          <div>
            <h3 style={{ margin: 0, fontSize: 15, display: 'flex', alignItems: 'center', gap: 8 }}>
              <span style={{ display: 'inline-block', width: 10, height: 10, borderRadius: 3, background: area.color }} />
              {area.name} — Teams
            </h3>
            <p style={{ margin: '3px 0 0', fontSize: 12, color: 'var(--fg-3)' }}>
              {areaTeams.length} team{areaTeams.length !== 1 ? 's' : ''} in this area
            </p>
          </div>
          <button onClick={onClose} style={{ background: 'none', border: 0, cursor: 'pointer', fontSize: 18, color: 'var(--fg-3)' }}>✕</button>
        </div>

        {/* Add team row */}
        <div style={{ display: 'flex', gap: 8, marginBottom: 16 }}>
          <select
            value={selectedAdd}
            onChange={e => setSelectedAdd(e.target.value)}
            style={inputStyle}
            disabled={available.length === 0}
          >
            <option value="">
              {available.length === 0 ? 'All teams already assigned' : 'Select a team to add…'}
            </option>
            {available.map(t => (
              <option key={t.id} value={t.id}>
                {t.name}{t.area_name ? ` (from ${t.area_name})` : ''}
              </option>
            ))}
          </select>
          <button
            className="btn btn--primary btn--sm"
            onClick={handleAdd}
            disabled={!selectedAdd || busy !== null}
            style={{ whiteSpace: 'nowrap' }}
          >
            {busy === selectedAdd ? 'Adding…' : '+ Add team'}
          </button>
        </div>

        {error && <p style={{ color: 'var(--bad)', fontSize: 12.5, margin: '0 0 10px' }}>{error}</p>}

        {/* Current teams list */}
        <div style={{ flex: 1, overflowY: 'auto', minHeight: 0 }}>
          {areaTeamsQuery.isLoading ? (
            <LoadingState rows={3} />
          ) : areaTeams.length === 0 ? (
            <div style={{ textAlign: 'center', padding: '32px 0', color: 'var(--fg-3)', fontSize: 13 }}>
              No teams in this area yet
            </div>
          ) : (
            <table className="tbl">
              <thead>
                <tr><th>Team</th><th>Slug</th><th></th></tr>
              </thead>
              <tbody>
                {areaTeams.map(t => (
                  <tr key={t.id}>
                    <td style={{ fontWeight: 500 }}>{t.name}</td>
                    <td><span className="mono" style={{ fontSize: 12, color: 'var(--fg-3)' }}>{t.slug}</span></td>
                    <td style={{ textAlign: 'right' }}>
                      <button
                        className="btn btn--sm btn--ghost"
                        style={{ color: 'var(--bad)' }}
                        disabled={busy === t.id}
                        onClick={() => handleRemove(t)}
                      >
                        {busy === t.id ? '…' : 'Remove'}
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>

        <div style={{ paddingTop: 16, borderTop: '1px solid var(--rule)', marginTop: 8, textAlign: 'right' }}>
          <button className="btn btn--sm btn--ghost" onClick={onClose}>Done</button>
        </div>
      </div>
    </div>
  );
}

// ── Area modal ─────────────────────────────────────────────────────────────

interface AreaModalProps {
  area: Area | null;
  onClose: () => void;
  onSaved: () => void;
}

function AreaModal({ area, onClose, onSaved }: AreaModalProps) {
  const isEdit = area !== null;
  const [form, setForm] = useState({
    name: area?.name ?? '',
    slug: area?.slug ?? '',
    description: area?.description ?? '',
    color: area?.color ?? '#0A7BD7',
  });
  const [slugManual, setSlugManual] = useState(isEdit);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleNameChange = (name: string) => {
    setForm(f => ({
      ...f,
      name,
      slug: slugManual ? f.slug : toSlug(name),
    }));
  };

  const handleSlugChange = (slug: string) => {
    setSlugManual(true);
    setForm(f => ({ ...f, slug }));
  };

  const save = async () => {
    if (!form.name.trim()) { setError('Name is required.'); return; }
    if (!form.slug.trim()) { setError('Slug is required.'); return; }
    setSaving(true);
    setError(null);
    try {
      const url = isEdit ? `${BASE}/areas/${area!.id}` : `${BASE}/areas`;
      const res = await fetch(url, {
        method: isEdit ? 'PUT' : 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          name: form.name.trim(),
          slug: form.slug.trim(),
          description: form.description.trim() || null,
          color: form.color,
        }),
      });
      if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        setError((body as { detail?: string }).detail ?? `Error ${res.status}`);
        return;
      }
      onSaved();
      onClose();
    } catch (e) {
      setError(String(e));
    } finally {
      setSaving(false);
    }
  };

  const field = (label: string, children: React.ReactNode) => (
    <div style={{ marginBottom: 16 }}>
      <label style={{ display: 'block', fontSize: 12.5, color: 'var(--fg-2)', marginBottom: 5 }}>{label}</label>
      {children}
    </div>
  );

  const inputStyle: React.CSSProperties = {
    width: '100%', padding: '7px 10px', fontSize: 13,
    background: 'var(--surface-2)', border: '1px solid var(--rule)',
    borderRadius: 6, color: 'var(--fg-1)', fontFamily: 'inherit', boxSizing: 'border-box',
  };

  return (
    <div
      style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.55)', zIndex: 300, display: 'flex', alignItems: 'center', justifyContent: 'center' }}
      onClick={e => { if (e.target === e.currentTarget) onClose(); }}
    >
      <div style={{
        background: 'var(--surface)', border: '1px solid var(--rule)',
        borderRadius: 12, padding: 28, width: 480, maxWidth: '95vw', maxHeight: '90vh', overflowY: 'auto',
      }}>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 20 }}>
          <h3 style={{ margin: 0, fontSize: 15 }}>{isEdit ? `Edit area — ${area!.name}` : 'New area'}</h3>
          <button onClick={onClose} style={{ background: 'none', border: 0, cursor: 'pointer', fontSize: 18, color: 'var(--fg-3)' }}>✕</button>
        </div>

        {field('Name', (
          <input
            type="text"
            style={inputStyle}
            value={form.name}
            placeholder="e.g. Platform Engineering"
            onChange={e => handleNameChange(e.target.value)}
            autoFocus
          />
        ))}

        {field('Slug', (
          <input
            type="text"
            style={{ ...inputStyle, fontFamily: 'var(--font-mono, monospace)', fontSize: 12.5 }}
            value={form.slug}
            placeholder="e.g. platform-engineering"
            onChange={e => handleSlugChange(e.target.value)}
          />
        ))}

        {field('Description (optional)', (
          <textarea
            style={{ ...inputStyle, resize: 'vertical', minHeight: 72 }}
            value={form.description}
            placeholder="Short description of this area…"
            onChange={e => setForm(f => ({ ...f, description: e.target.value }))}
          />
        ))}

        {field('Color', (
          <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
            {PRESET_COLORS.map(c => (
              <button
                key={c.value}
                title={c.label}
                onClick={() => setForm(f => ({ ...f, color: c.value }))}
                style={{
                  width: 32, height: 32, borderRadius: 8,
                  background: c.value,
                  border: form.color === c.value ? '3px solid var(--fg-1)' : '2px solid transparent',
                  cursor: 'pointer', outline: 'none',
                  boxShadow: form.color === c.value ? `0 0 0 2px var(--surface), 0 0 0 4px ${c.value}` : 'none',
                  transition: 'box-shadow 0.1s',
                }}
              />
            ))}
          </div>
        ))}

        {error && <p style={{ color: 'var(--bad)', fontSize: 12.5, margin: '0 0 12px' }}>{error}</p>}

        <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end', paddingTop: 8, borderTop: '1px solid var(--rule)' }}>
          <button className="btn btn--sm btn--ghost" onClick={onClose}>Cancel</button>
          <button className="btn btn--sm btn--primary" onClick={save} disabled={saving}>
            {saving ? 'Saving…' : isEdit ? 'Save changes' : 'Create area'}
          </button>
        </div>
      </div>
    </div>
  );
}

// ── Delete confirm ──────────────────────────────────────────────────────────

interface DeleteConfirmProps {
  area: Area;
  onClose: () => void;
  onDeleted: () => void;
}

function DeleteConfirm({ area, onClose, onDeleted }: DeleteConfirmProps) {
  const [deleting, setDeleting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const doDelete = async () => {
    setDeleting(true);
    setError(null);
    try {
      const res = await fetch(`${BASE}/areas/${area.id}`, { method: 'DELETE' });
      if (!res.ok && res.status !== 204) {
        const body = await res.json().catch(() => ({}));
        setError((body as { detail?: string }).detail ?? `Error ${res.status}`);
        return;
      }
      onDeleted();
      onClose();
    } catch (e) {
      setError(String(e));
    } finally {
      setDeleting(false);
    }
  };

  return (
    <div
      style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.55)', zIndex: 300, display: 'flex', alignItems: 'center', justifyContent: 'center' }}
      onClick={e => { if (e.target === e.currentTarget) onClose(); }}
    >
      <div style={{
        background: 'var(--surface)', border: '1px solid var(--rule)',
        borderRadius: 12, padding: 28, width: 420, maxWidth: '95vw',
      }}>
        <h3 style={{ margin: '0 0 10px', fontSize: 15 }}>Delete area</h3>
        <p style={{ margin: '0 0 18px', fontSize: 13.5, color: 'var(--fg-2)', lineHeight: 1.5 }}>
          Are you sure you want to delete <strong>{area.name}</strong>?
          {area.team_count > 0 && (
            <> This area contains <strong>{area.team_count} team{area.team_count !== 1 ? 's' : ''}</strong> which will be unlinked.</>
          )}
        </p>
        {error && <p style={{ color: 'var(--bad)', fontSize: 12.5, margin: '0 0 12px' }}>{error}</p>}
        <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end' }}>
          <button className="btn btn--sm btn--ghost" onClick={onClose}>Cancel</button>
          <button
            className="btn btn--sm"
            style={{ background: 'var(--bad)', color: '#fff', borderColor: 'var(--bad)' }}
            onClick={doDelete}
            disabled={deleting}
          >
            {deleting ? 'Deleting…' : 'Delete area'}
          </button>
        </div>
      </div>
    </div>
  );
}

// ── Main page ───────────────────────────────────────────────────────────────

export default function AreasPage() {
  const [showModal, setShowModal] = useState(false);
  const [editingArea, setEditingArea] = useState<Area | null>(null);
  const [deletingArea, setDeletingArea] = useState<Area | null>(null);
  const [managingArea, setManagingArea] = useState<Area | null>(null);
  const [policyArea, setPolicyArea] = useState<Area | null>(null);
  const queryClient = useQueryClient();

  const areasQuery = useQuery<Area[]>({
    queryKey: ['areas'],
    queryFn: () => fetch(`${BASE}/areas`).then(r => {
      if (!r.ok) throw new Error(`Failed to fetch areas: ${r.status}`);
      return r.json();
    }),
  });

  const modelsQuery = useQuery<Model[]>({
    queryKey: ['models'],
    queryFn: () => fetch(`${BASE}/models`).then(r => r.json()),
    staleTime: 120_000,
  });

  const onSaved = () => queryClient.invalidateQueries({ queryKey: ['areas'] });

  if (areasQuery.isLoading) return <section className="page"><LoadingState rows={8} /></section>;
  if (areasQuery.isError) return <section className="page"><ErrorState error={areasQuery.error as Error} retry={() => areasQuery.refetch()} /></section>;

  const areas = areasQuery.data ?? [];
  const models = modelsQuery.data ?? [];

  const totalTeams = areas.reduce((sum, a) => sum + a.team_count, 0);
  const avgTeams = areas.length > 0 ? (totalTeams / areas.length).toFixed(1) : '—';

  return (
    <section className="page">
      {(showModal || editingArea) && (
        <AreaModal
          area={editingArea}
          onClose={() => { setShowModal(false); setEditingArea(null); }}
          onSaved={onSaved}
        />
      )}
      {deletingArea && (
        <DeleteConfirm
          area={deletingArea}
          onClose={() => setDeletingArea(null)}
          onDeleted={onSaved}
        />
      )}
      {managingArea && (
        <ManageTeamsModal
          area={managingArea}
          onClose={() => setManagingArea(null)}
          onChanged={onSaved}
        />
      )}
      {policyArea && (
        <PolicyModal
          area={policyArea}
          models={models}
          onClose={() => setPolicyArea(null)}
          onSaved={() => {
            onSaved();
            queryClient.invalidateQueries({ queryKey: ['area-policy', policyArea.id] });
          }}
        />
      )}

      <div className="page__head">
        <div>
          <h1 className="page__title">Areas</h1>
          <p className="page__sub">Organisational areas that group teams of developers.</p>
        </div>
        <div className="page__actions">
          <button className="btn btn--primary" onClick={() => { setEditingArea(null); setShowModal(true); }}>
            + New area
          </button>
        </div>
      </div>

      <div className="kpi-grid" style={{ marginBottom: 18 }}>
        <div className="kpi">
          <div className="kpi__label">Total areas</div>
          <div className="kpi__value">{areas.length}</div>
          <div className="kpi__delta flat">configured</div>
        </div>
        <div className="kpi">
          <div className="kpi__label">Total teams</div>
          <div className="kpi__value">{totalTeams}</div>
          <div className="kpi__delta flat">across all areas</div>
        </div>
        <div className="kpi">
          <div className="kpi__label">Avg teams / area</div>
          <div className="kpi__value">{avgTeams}</div>
          <div className="kpi__delta flat">average</div>
        </div>
      </div>

      {areas.length === 0 ? (
        <EmptyState message="No areas yet. Create your first area to group teams." />
      ) : (
        <div className="card">
          <div className="card__body" style={{ padding: 0 }}>
            <table className="tbl">
              <thead>
                <tr>
                  <th>Name</th>
                  <th>Slug</th>
                  <th>Description</th>
                  <th className="num">Teams</th>
                  <th>Created</th>
                  <th></th>
                </tr>
              </thead>
              <tbody>
                {areas.map(area => (
                  <tr key={area.id}>
                    <td>
                      <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
                        <span style={{
                          display: 'inline-block', width: 10, height: 10, borderRadius: 3,
                          background: area.color, flexShrink: 0,
                        }} />
                        <span style={{ fontWeight: 500 }}>{area.name}</span>
                        {area.has_policy
                          ? <span className="pill pill--good">Policy set</span>
                          : <span className="pill">Org defaults</span>}
                      </div>
                    </td>
                    <td><span className="mono" style={{ fontSize: 12.5, color: 'var(--fg-2)' }}>{area.slug}</span></td>
                    <td style={{ maxWidth: 280 }}>
                      {area.description
                        ? <span style={{ color: 'var(--fg-2)', fontSize: 13 }}>{area.description}</span>
                        : <span className="muted">—</span>}
                    </td>
                    <td className="num">
                      <button
                        className="btn btn--sm btn--ghost"
                        style={{ fontFamily: 'var(--font-mono, monospace)', fontWeight: 600, minWidth: 28 }}
                        onClick={() => setManagingArea(area)}
                        title="Manage teams in this area"
                      >
                        {area.team_count}
                      </button>
                    </td>
                    <td style={{ fontSize: 12.5, color: 'var(--fg-3)' }}>{formatDate(area.created_at)}</td>
                    <td>
                      <div style={{ display: 'flex', gap: 6, justifyContent: 'flex-end' }}>
                        <button
                          className="btn btn--sm btn--ghost"
                          onClick={() => setManagingArea(area)}
                        >
                          Teams
                        </button>
                        <button
                          className="btn btn--sm btn--ghost"
                          onClick={() => setPolicyArea(area)}
                        >
                          Policy
                        </button>
                        <button
                          className="btn btn--sm btn--ghost"
                          onClick={() => { setEditingArea(area); setShowModal(false); }}
                        >
                          Edit
                        </button>
                        <button
                          className="btn btn--sm btn--ghost"
                          style={{ color: 'var(--bad)' }}
                          onClick={() => setDeletingArea(area)}
                        >
                          Delete
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </section>
  );
}
