'use client';

import React, { useState } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { LoadingState, ErrorState } from '../../_components/PageStates';

const LEAGUE = process.env.NEXT_PUBLIC_LEAGUE_API ?? 'http://localhost:8080/league';

type ItemType = 'badge' | 'card_border' | 'avatar_frame' | 'title';

interface StoreItem {
  id: string;
  name: string;
  type: ItemType;
  point_cost: number;
  asset_url: string;
  exclusive_season_id: string | null;
  exclusive_top_n: number | null;
  active?: boolean;
}

const TYPE_LABELS: Record<ItemType, string> = {
  badge: 'Badge',
  card_border: 'Card border',
  avatar_frame: 'Avatar frame',
  title: 'Title',
};

const TYPE_ICONS: Record<ItemType, string> = {
  badge: '🏅',
  card_border: '🖼️',
  avatar_frame: '✨',
  title: '🏷️',
};

interface CreateItemModalProps {
  onClose: () => void;
  onSaved: () => void;
}

function CreateItemModal({ onClose, onSaved }: CreateItemModalProps) {
  const [form, setForm] = useState({
    name: '',
    type: 'badge' as ItemType,
    point_cost: '500',
    asset_url: '',
  });
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');

  async function handleSave() {
    if (!form.name) { setError('Name is required'); return; }
    setSaving(true);
    setError('');
    try {
      const res = await fetch(`${LEAGUE}/store/items`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ ...form, point_cost: parseInt(form.point_cost) }),
      });
      if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(d.detail ?? 'Failed'); }
      onSaved();
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : 'Failed to create item');
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
        <h2 style={{ margin: '0 0 20px', fontSize: 17, fontWeight: 600 }}>New Store Item</h2>
        {error && (
          <div style={{ marginBottom: 14, padding: '9px 12px', borderRadius: 6, fontSize: 13,
            background: 'rgba(220,38,38,0.1)', border: '1px solid rgba(220,38,38,0.3)', color: '#FCA5A5' }}>
            {error}
          </div>
        )}
        <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
          <label style={{ fontSize: 12.5, fontWeight: 500, color: 'var(--fg-2)' }}>
            Item name
            <input value={form.name} onChange={e => setForm(f => ({ ...f, name: e.target.value }))}
              placeholder="e.g. Golden Shovel Badge" style={{ ...inputStyle, marginTop: 5 }} />
          </label>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10 }}>
            <label style={{ fontSize: 12.5, fontWeight: 500, color: 'var(--fg-2)' }}>
              Type
              <select value={form.type} onChange={e => setForm(f => ({ ...f, type: e.target.value as ItemType }))}
                style={{ ...inputStyle, marginTop: 5 }}>
                {(Object.keys(TYPE_LABELS) as ItemType[]).map(t => (
                  <option key={t} value={t}>{TYPE_LABELS[t]}</option>
                ))}
              </select>
            </label>
            <label style={{ fontSize: 12.5, fontWeight: 500, color: 'var(--fg-2)' }}>
              Point cost
              <input type="number" min="0" step="50" value={form.point_cost}
                onChange={e => setForm(f => ({ ...f, point_cost: e.target.value }))}
                style={{ ...inputStyle, marginTop: 5 }} />
            </label>
          </div>
          <label style={{ fontSize: 12.5, fontWeight: 500, color: 'var(--fg-2)' }}>
            Asset URL (optional)
            <input value={form.asset_url}
              onChange={e => setForm(f => ({ ...f, asset_url: e.target.value }))}
              placeholder="https://…" style={{ ...inputStyle, marginTop: 5 }} />
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
          }}>{saving ? 'Creating…' : 'Create item'}</button>
        </div>
      </div>
    </div>
  );
}

interface EditItemModalProps {
  item: StoreItem;
  onClose: () => void;
  onSaved: () => void;
}

function EditItemModal({ item, onClose, onSaved }: EditItemModalProps) {
  const [form, setForm] = useState({
    name: item.name,
    point_cost: String(item.point_cost),
    asset_url: item.asset_url ?? '',
    active: item.active !== false,
  });
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');

  async function handleSave() {
    setSaving(true);
    setError('');
    try {
      const res = await fetch(`${LEAGUE}/store/items/${item.id}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          name: form.name,
          point_cost: parseInt(form.point_cost),
          asset_url: form.asset_url,
          active: form.active,
        }),
      });
      if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(d.detail ?? 'Failed'); }
      onSaved();
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : 'Failed to update item');
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

  const isExclusive = !!item.exclusive_season_id;

  return (
    <div style={{
      position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.5)',
      display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 1000,
    }}>
      <div style={{
        background: 'var(--surface)', border: '1px solid var(--rule)',
        borderRadius: 12, padding: '24px', width: 440, boxShadow: '0 20px 60px rgba(0,0,0,0.4)',
      }}>
        <h2 style={{ margin: '0 0 4px', fontSize: 17, fontWeight: 600 }}>Edit Store Item</h2>
        <p style={{ margin: '0 0 20px', fontSize: 13, color: 'var(--fg-3)' }}>
          {TYPE_LABELS[item.type]}{isExclusive ? ' · Exclusive — not purchasable' : ''}
        </p>
        {error && (
          <div style={{ marginBottom: 14, padding: '9px 12px', borderRadius: 6, fontSize: 13,
            background: 'rgba(220,38,38,0.1)', border: '1px solid rgba(220,38,38,0.3)', color: '#FCA5A5' }}>
            {error}
          </div>
        )}
        <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
          <label style={{ fontSize: 12.5, fontWeight: 500, color: 'var(--fg-2)' }}>
            Name
            <input value={form.name} onChange={e => setForm(f => ({ ...f, name: e.target.value }))}
              style={{ ...inputStyle, marginTop: 5 }} />
          </label>
          <label style={{ fontSize: 12.5, fontWeight: 500, color: 'var(--fg-2)' }}>
            Point cost {isExclusive && <span style={{ color: 'var(--fg-3)' }}>(ignored for exclusive items)</span>}
            <input
              type="number" min="0" step="50"
              value={form.point_cost}
              disabled={isExclusive}
              onChange={e => setForm(f => ({ ...f, point_cost: e.target.value }))}
              style={{ ...inputStyle, marginTop: 5, opacity: isExclusive ? 0.6 : 1 }}
            />
          </label>
          <label style={{ fontSize: 12.5, fontWeight: 500, color: 'var(--fg-2)' }}>
            Asset URL
            <input value={form.asset_url}
              onChange={e => setForm(f => ({ ...f, asset_url: e.target.value }))}
              placeholder="https://…" style={{ ...inputStyle, marginTop: 5 }} />
          </label>
          <label style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: 13, color: 'var(--fg-1)', cursor: 'pointer' }}>
            <input
              type="checkbox"
              checked={form.active}
              onChange={e => setForm(f => ({ ...f, active: e.target.checked }))}
              style={{ cursor: 'pointer', accentColor: 'var(--sc-blue, #083EA7)' }}
            />
            Active — appears in the developer store
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
          }}>{saving ? 'Saving…' : 'Save changes'}</button>
        </div>
      </div>
    </div>
  );
}

export default function StoreEditorPage() {
  const qc = useQueryClient();
  const [showCreate, setShowCreate] = useState(false);
  const [editing, setEditing] = useState<StoreItem | null>(null);
  const [filterType, setFilterType] = useState<'all' | ItemType>('all');

  const { data, isLoading, error } = useQuery<StoreItem[] | { items?: StoreItem[] }>({
    queryKey: ['league-store'],
    queryFn: () => fetch(`${LEAGUE}/store/items?include_inactive=true`).then(r => r.json()),
  });

  const items = Array.isArray(data) ? data : data?.items ?? [];
  const filtered = filterType === 'all' ? items : items.filter(i => i.type === filterType);

  if (isLoading) return <LoadingState />;
  if (error) return <ErrorState error={new Error("Could not load store items")} />;

  return (
    <div className="page">
      <div className="page__header">
        <div>
          <h1 className="page__title">Store Editor</h1>
          <p className="page__sub">Manage cosmetic items engineers can purchase with points</p>
        </div>
        <div style={{ display: 'flex', gap: 10, alignItems: 'center' }}>
          <select
            value={filterType}
            onChange={e => setFilterType(e.target.value as 'all' | ItemType)}
            style={{
              padding: '7px 12px', borderRadius: 6, border: '1px solid var(--rule)',
              background: 'var(--surface)', color: 'var(--fg-1)', fontSize: 13,
            }}
          >
            <option value="all">All types</option>
            {(Object.entries(TYPE_LABELS) as [ItemType, string][]).map(([k, v]) => (
              <option key={k} value={k}>{v}</option>
            ))}
          </select>
          <button onClick={() => setShowCreate(true)} className="btn btn--primary">
            + New item
          </button>
        </div>
      </div>

      {/* Summary bar */}
      <div style={{ display: 'flex', gap: 10, marginBottom: 20 }}>
        {(Object.entries(TYPE_LABELS) as [ItemType, string][]).map(([type, label]) => {
          const count = items.filter(i => i.type === type).length;
          return (
            <div key={type} style={{
              flex: 1, background: 'var(--surface)', border: '1px solid var(--rule)',
              borderRadius: 8, padding: '12px 16px',
            }}>
              <div style={{ fontSize: 22, marginBottom: 4 }}>{TYPE_ICONS[type]}</div>
              <div style={{ fontSize: 22, fontWeight: 700, fontFamily: 'var(--font-mono)' }}>{count}</div>
              <div style={{ fontSize: 12, color: 'var(--fg-3)' }}>{label}s</div>
            </div>
          );
        })}
      </div>

      {filtered.length === 0 ? (
        <div style={{
          textAlign: 'center', padding: '60px 20px',
          border: '1px dashed var(--rule)', borderRadius: 10, color: 'var(--fg-3)',
        }}>
          <div style={{ fontSize: 36, marginBottom: 12 }}>🛒</div>
          <div style={{ fontWeight: 600, marginBottom: 6 }}>No items yet</div>
          <div style={{ fontSize: 13 }}>Add cosmetic rewards engineers can spend their points on</div>
        </div>
      ) : (
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(220px, 1fr))', gap: 12 }}>
          {filtered.map(item => {
            const isInactive = item.active === false;
            return (
            <div key={item.id} style={{
              background: 'var(--surface)',
              border: `1px solid ${isInactive ? 'var(--bad, #DC2626)' : 'var(--rule)'}`,
              borderRadius: 10, padding: '16px',
              display: 'flex', flexDirection: 'column', gap: 10,
              opacity: isInactive ? 0.65 : 1,
              position: 'relative',
            }}>
              {isInactive && (
                <div style={{
                  position: 'absolute', top: 8, right: 8,
                  fontSize: 10, fontWeight: 700, color: 'var(--bad, #DC2626)',
                  background: 'rgba(220,38,38,0.15)', padding: '2px 6px', borderRadius: 4,
                }}>INACTIVE</div>
              )}
              <div style={{ fontSize: 32, textAlign: 'center' }}>{TYPE_ICONS[item.type]}</div>
              <div style={{ textAlign: 'center' }}>
                <div style={{ fontWeight: 600, fontSize: 13, marginBottom: 3 }}>{item.name}</div>
                <div style={{ fontSize: 11.5, color: 'var(--fg-3)' }}>{TYPE_LABELS[item.type]}</div>
              </div>
              <div style={{
                display: 'flex', alignItems: 'center', justifyContent: 'space-between',
                paddingTop: 10, borderTop: '1px solid var(--rule)',
              }}>
                <span style={{ fontSize: 13, fontWeight: 700, color: 'var(--warn, #B45309)' }}>
                  ★ {item.point_cost.toLocaleString()}
                </span>
                {item.exclusive_season_id && (
                  <span style={{ fontSize: 11, color: 'var(--fg-3)', fontStyle: 'italic' }}>exclusive</span>
                )}
                <button
                  onClick={() => setEditing(item)}
                  style={{
                    padding: '4px 10px', borderRadius: 5, border: '1px solid var(--rule)',
                    background: 'transparent', color: 'var(--fg-2)', cursor: 'pointer', fontSize: 12,
                  }}
                >Edit</button>
              </div>
            </div>
            );
          })}
        </div>
      )}

      {showCreate && (
        <CreateItemModal
          onClose={() => setShowCreate(false)}
          onSaved={() => { setShowCreate(false); qc.invalidateQueries({ queryKey: ['league-store'] }); }}
        />
      )}

      {editing && (
        <EditItemModal
          item={editing}
          onClose={() => setEditing(null)}
          onSaved={() => { setEditing(null); qc.invalidateQueries({ queryKey: ['league-store'] }); }}
        />
      )}
    </div>
  );
}
