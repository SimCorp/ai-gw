'use client';

import React, { useState } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
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

interface Area {
  id: string;
  name: string;
  slug: string;
  description: string | null;
  color: string;
  team_count: number;
  created_at?: string;
}

function formatDate(iso: string | null | undefined) {
  if (!iso) return '—';
  return new Date(iso).toLocaleDateString('en-GB', { day: 'numeric', month: 'short', year: 'numeric' });
}

function toSlug(name: string): string {
  return name.trim().toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '');
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
  const queryClient = useQueryClient();

  const areasQuery = useQuery<Area[]>({
    queryKey: ['areas'],
    queryFn: () => fetch(`${BASE}/areas`).then(r => {
      if (!r.ok) throw new Error(`Failed to fetch areas: ${r.status}`);
      return r.json();
    }),
  });

  const onSaved = () => queryClient.invalidateQueries({ queryKey: ['areas'] });

  if (areasQuery.isLoading) return <section className="page"><LoadingState rows={8} /></section>;
  if (areasQuery.isError) return <section className="page"><ErrorState error={areasQuery.error as Error} retry={() => areasQuery.refetch()} /></section>;

  const areas = areasQuery.data ?? [];

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
                      <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                        <span style={{
                          display: 'inline-block', width: 10, height: 10, borderRadius: 3,
                          background: area.color, flexShrink: 0,
                        }} />
                        <span style={{ fontWeight: 500 }}>{area.name}</span>
                      </div>
                    </td>
                    <td><span className="mono" style={{ fontSize: 12.5, color: 'var(--fg-2)' }}>{area.slug}</span></td>
                    <td style={{ maxWidth: 280 }}>
                      {area.description
                        ? <span style={{ color: 'var(--fg-2)', fontSize: 13 }}>{area.description}</span>
                        : <span className="muted">—</span>}
                    </td>
                    <td className="num mono">{area.team_count}</td>
                    <td style={{ fontSize: 12.5, color: 'var(--fg-3)' }}>{formatDate(area.created_at)}</td>
                    <td>
                      <div style={{ display: 'flex', gap: 6, justifyContent: 'flex-end' }}>
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
