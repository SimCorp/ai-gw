'use client';

import React, { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { LoadingState, ErrorState, EmptyState } from '../_components/PageStates';
import { apiFetch } from '../../../lib/apiClient';

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
  color: string;
}

interface Unit {
  id: string;
  area_id: string;
  area_name: string | null;
  name: string;
  slug: string;
  description: string | null;
  color: string | null;
  team_count: number;
  created_at: string;
  parent_unit_id: string | null;
  parent_unit_name: string | null;
}

function toSlug(name: string): string {
  return name.trim().toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '');
}

function formatDate(iso: string | null | undefined) {
  if (!iso) return '—';
  return new Date(iso).toLocaleDateString('en-GB', { day: 'numeric', month: 'short', year: 'numeric' });
}

// ── Unit form modal ────────────────────────────────────────────────────────

interface UnitModalProps {
  unit?: Unit;
  areas: Area[];
  allUnits: Unit[];
  defaultAreaId?: string;
  onClose: () => void;
  onSaved: () => void;
}

function UnitModal({ unit, areas, allUnits, defaultAreaId, onClose, onSaved }: UnitModalProps) {
  const isEdit = !!unit;
  const [form, setForm] = useState({
    name: unit?.name ?? '',
    slug: unit?.slug ?? '',
    description: unit?.description ?? '',
    color: unit?.color ?? PRESET_COLORS[0].value,
    area_id: unit?.area_id ?? defaultAreaId ?? (areas[0]?.id ?? ''),
    parent_unit_id: unit?.parent_unit_id ?? '',
  });
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const siblingUnits = allUnits.filter(u =>
    u.area_id === form.area_id && u.id !== unit?.id && !u.parent_unit_id
  );

  const handleNameChange = (name: string) => {
    setForm(f => ({ ...f, name, slug: isEdit ? f.slug : toSlug(name) }));
  };

  const save = async () => {
    if (!form.name.trim()) { setError('Name is required'); return; }
    if (!form.area_id) { setError('Area is required'); return; }
    setSaving(true);
    setError(null);
    try {
      const path = isEdit ? `/units/${unit!.id}` : '/units';
      await apiFetch(path, {
        method: isEdit ? 'PUT' : 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          name: form.name.trim(),
          slug: form.slug.trim() || toSlug(form.name.trim()),
          description: form.description.trim() || null,
          color: form.color,
          area_id: form.area_id,
          parent_unit_id: form.parent_unit_id || null,
        }),
      });
      onSaved();
      onClose();
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setSaving(false);
    }
  };

  const inputStyle: React.CSSProperties = {
    width: '100%', padding: '7px 10px', fontSize: 13,
    background: 'var(--surface-2)', border: '1px solid var(--rule)',
    borderRadius: 6, color: 'var(--fg-1)', fontFamily: 'inherit',
  };

  const field = (label: string, children: React.ReactNode) => (
    <div style={{ marginBottom: 16 }}>
      <label style={{ display: 'block', fontSize: 12.5, color: 'var(--fg-2)', marginBottom: 5 }}>{label}</label>
      {children}
    </div>
  );

  return (
    <div
      style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.55)', zIndex: 300, display: 'flex', alignItems: 'center', justifyContent: 'center' }}
      onClick={e => { if (e.target === e.currentTarget) onClose(); }}
    >
      <div style={{
        background: 'var(--surface)', border: '1px solid var(--rule)',
        borderRadius: 12, padding: 28, width: 480, maxWidth: '95vw',
      }}>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 20 }}>
          <h3 style={{ margin: 0, fontSize: 15 }}>{isEdit ? 'Edit unit' : 'New unit'}</h3>
          <button onClick={onClose} style={{ background: 'none', border: 0, cursor: 'pointer', fontSize: 18, color: 'var(--fg-3)' }}>✕</button>
        </div>

        {field('Area', (
          <select
            style={inputStyle}
            value={form.area_id}
            onChange={e => setForm(f => ({ ...f, area_id: e.target.value, parent_unit_id: '' }))}
            disabled={isEdit}
          >
            {areas.map(a => <option key={a.id} value={a.id}>{a.name}</option>)}
          </select>
        ))}

        {field('Parent unit (optional)', (
          <select
            style={inputStyle}
            value={form.parent_unit_id}
            onChange={e => setForm(f => ({ ...f, parent_unit_id: e.target.value }))}
          >
            <option value="">— None (top-level unit) —</option>
            {siblingUnits.map(u => <option key={u.id} value={u.id}>{u.name}</option>)}
          </select>
        ))}

        {field('Unit name', (
          <input
            type="text" style={inputStyle} placeholder="e.g. Platform Engineering"
            value={form.name}
            onChange={e => handleNameChange(e.target.value)}
            autoFocus
          />
        ))}

        {field('Slug', (
          <input
            type="text" style={{ ...inputStyle, fontFamily: 'var(--font-mono, monospace)', fontSize: 12 }}
            value={form.slug}
            onChange={e => setForm(f => ({ ...f, slug: e.target.value }))}
          />
        ))}

        {field('Description (optional)', (
          <textarea
            style={{ ...inputStyle, resize: 'vertical', minHeight: 70 }}
            value={form.description}
            onChange={e => setForm(f => ({ ...f, description: e.target.value }))}
            placeholder="What does this unit do?"
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
                  width: 26, height: 26, borderRadius: 6, background: c.value, border: 'none',
                  cursor: 'pointer', outline: form.color === c.value ? `2px solid var(--fg-1)` : 'none',
                  outlineOffset: 2,
                }}
              />
            ))}
          </div>
        ))}

        {error && <p style={{ color: 'var(--bad)', fontSize: 12.5, margin: '0 0 12px' }}>{error}</p>}

        <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end', paddingTop: 8, borderTop: '1px solid var(--rule)' }}>
          <button className="btn btn--sm btn--ghost" onClick={onClose}>Cancel</button>
          <button className="btn btn--sm btn--primary" onClick={save} disabled={saving}>
            {saving ? 'Saving…' : isEdit ? 'Save changes' : 'Create unit'}
          </button>
        </div>
      </div>
    </div>
  );
}

// ── Main page ──────────────────────────────────────────────────────────────

export default function UnitsPage() {
  const [areaFilter, setAreaFilter] = useState<string>('all');
  const [modal, setModal] = useState<'create' | { unit: Unit } | null>(null);
  const queryClient = useQueryClient();

  const areasQuery = useQuery<Area[]>({
    queryKey: ['areas'],
    queryFn: () => apiFetch<Area[]>('/areas'),
    staleTime: 60_000,
  });

  const unitsQuery = useQuery<Unit[]>({
    queryKey: ['units', areaFilter],
    queryFn: () => {
      const path = areaFilter === 'all' ? '/units' : `/units?area_id=${areaFilter}`;
      return apiFetch<Unit[]>(path);
    },
  });

  const deleteMutation = useMutation({
    mutationFn: (unitId: string) => apiFetch(`/units/${unitId}`, { method: 'DELETE' }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['units'] }),
    onError: (err: Error) => window.alert(err.message),
  });

  const handleDelete = (unit: Unit) => {
    if (unit.team_count > 0) {
      window.alert(`Cannot delete "${unit.name}" — it has ${unit.team_count} team${unit.team_count > 1 ? 's' : ''}. Reassign or delete the teams first.`);
      return;
    }
    const childCount = units.filter(u => u.parent_unit_id === unit.id).length;
    if (childCount > 0) {
      window.alert(`Cannot delete "${unit.name}" — it has ${childCount} child unit${childCount > 1 ? 's' : ''}. Delete or reparent them first.`);
      return;
    }
    if (!window.confirm(`Delete unit "${unit.name}"? This cannot be undone.`)) return;
    deleteMutation.mutate(unit.id);
  };

  const onSaved = () => queryClient.invalidateQueries({ queryKey: ['units'] });

  const isLoading = unitsQuery.isLoading;
  const isError = unitsQuery.isError;

  const areas = areasQuery.data ?? [];
  const units = unitsQuery.data ?? [];

  const areaColorMap = new Map(areas.map(a => [a.id, a.color]));

  const grouped = areaFilter === 'all'
    ? units.reduce((acc, u) => {
        const key = u.area_id;
        if (!acc.has(key)) acc.set(key, []);
        acc.get(key)!.push(u);
        return acc;
      }, new Map<string, Unit[]>())
    : null;

  return (
    <section className="page">
      <div className="page__head">
        <div>
          <h1 className="page__title">Units</h1>
          <p className="page__sub">{units.length} unit{units.length !== 1 ? 's' : ''} across {areas.length} area{areas.length !== 1 ? 's' : ''}</p>
        </div>
        <div className="page__actions">
          <button className="btn btn--primary" onClick={() => setModal('create')}>+ New unit</button>
        </div>
      </div>

      <div className="filters">
        <select
          value={areaFilter}
          onChange={e => setAreaFilter(e.target.value)}
          style={{
            padding: '5px 10px', fontSize: 12.5,
            background: 'var(--surface-2)', border: '1px solid var(--rule)',
            borderRadius: 6, color: 'var(--fg-1)', cursor: 'pointer', fontFamily: 'inherit',
          }}
        >
          <option value="all">All areas</option>
          {areas.map(a => <option key={a.id} value={a.id}>{a.name}</option>)}
        </select>
      </div>

      {isLoading && <LoadingState rows={8} />}
      {isError && <ErrorState error={unitsQuery.error as Error} retry={() => unitsQuery.refetch()} />}

      {!isLoading && !isError && units.length === 0 && (
        <EmptyState message="No units found. Create your first unit to group teams within an area." />
      )}

      {!isLoading && !isError && units.length > 0 && (
        <div className="card">
          <div className="card__body" style={{ padding: 0 }}>
            <table className="tbl">
              <thead>
                <tr>
                  <th>Unit</th>
                  <th>Area</th>
                  <th>Parent</th>
                  <th>Description</th>
                  <th className="num">Teams</th>
                  <th>Created</th>
                  <th></th>
                </tr>
              </thead>
              <tbody>
                {(grouped
                  ? Array.from(grouped.entries()).flatMap(([, areaUnits]) =>
                      areaUnits.map((u, i) => ({ u, isFirst: i === 0 }))
                    )
                  : units.map(u => ({ u, isFirst: false }))
                ).map(({ u }) => {
                  const color = u.color ?? areaColorMap.get(u.area_id) ?? '#888';
                  const isSubUnit = !!u.parent_unit_id;
                  return (
                    <tr key={u.id}>
                      <td>
                        <div className="cell-2">
                          <div style={{ display: 'flex', alignItems: 'center', gap: 8, paddingLeft: isSubUnit ? 16 : 0 }}>
                            {isSubUnit && <span style={{ color: 'var(--fg-3)', fontSize: 11 }}>↳</span>}
                            <span style={{
                              display: 'inline-block', width: 10, height: 10,
                              borderRadius: 3, background: color, flexShrink: 0,
                            }} />
                            <span style={{ fontWeight: 500 }}>{u.name}</span>
                          </div>
                          <span className="lo mono" style={{ paddingLeft: isSubUnit ? 16 : 0 }}>{u.slug}</span>
                        </div>
                      </td>
                      <td>
                        {u.area_name ? (
                          <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                            <span style={{
                              display: 'inline-block', width: 8, height: 8, borderRadius: 2,
                              background: areaColorMap.get(u.area_id) ?? '#888', flexShrink: 0,
                            }} />
                            <span style={{ fontSize: 13 }}>{u.area_name}</span>
                          </div>
                        ) : <span className="muted">—</span>}
                      </td>
                      <td>
                        {u.parent_unit_name
                          ? <span style={{ fontSize: 12.5, color: 'var(--fg-2)' }}>{u.parent_unit_name}</span>
                          : <span className="muted">—</span>}
                      </td>
                      <td>
                        <span style={{ fontSize: 12.5, color: 'var(--fg-2)' }}>
                          {u.description ?? <span className="muted">—</span>}
                        </span>
                      </td>
                      <td className="num">
                        <span className="mono">{u.team_count}</span>
                      </td>
                      <td>
                        <span style={{ fontSize: 12.5, color: 'var(--fg-2)' }}>{formatDate(u.created_at)}</span>
                      </td>
                      <td>
                        <div style={{ display: 'flex', gap: 6, justifyContent: 'flex-end' }}>
                          <button
                            className="btn btn--sm btn--ghost"
                            onClick={() => setModal({ unit: u })}
                          >Edit</button>
                          <button
                            className="btn btn--sm btn--ghost"
                            style={{ color: 'var(--bad)' }}
                            onClick={() => handleDelete(u)}
                            disabled={deleteMutation.isPending}
                          >Delete</button>
                        </div>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {modal === 'create' && (
        <UnitModal
          areas={areas}
          allUnits={units}
          onClose={() => setModal(null)}
          onSaved={onSaved}
        />
      )}
      {modal !== null && modal !== 'create' && (
        <UnitModal
          unit={modal.unit}
          areas={areas}
          allUnits={units}
          onClose={() => setModal(null)}
          onSaved={onSaved}
        />
      )}
    </section>
  );
}
