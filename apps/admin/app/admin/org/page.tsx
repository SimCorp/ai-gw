'use client';

import React, { useState, useCallback } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { apiFetch } from '../../../lib/apiClient';
import { LoadingState, ErrorState } from '../_components/PageStates';
import { OrgTree, collectAllIds } from '../_components/OrgTree';
import { OrgNode } from '../_components/nodeTypes';

const NODE_TYPES = ['area', 'team', 'unit'] as const;

interface CreateNodeForm {
  name: string;
  type: typeof NODE_TYPES[number];
  parent_id: string;
  description: string;
  location: string;
}

function CreateNodeModal({
  rootId,
  preselectedParentId,
  preselectedParentName,
  onClose,
  onCreated,
}: {
  rootId: string;
  preselectedParentId?: string;
  preselectedParentName?: string;
  onClose: () => void;
  onCreated: () => void;
}) {
  const [form, setForm] = useState<CreateNodeForm>({
    name: '',
    type: 'area',
    parent_id: preselectedParentId ?? rootId,
    description: '',
    location: '',
  });
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!form.name.trim()) return;
    setSaving(true);
    setError('');
    try {
      await apiFetch('/nodes', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          name: form.name.trim(),
          type: form.type,
          parent_id: form.parent_id || rootId,
          description: form.description.trim() || null,
          location: form.location.trim() || null,
        }),
      });
      onCreated();
      onClose();
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Failed to create node');
    } finally {
      setSaving(false);
    }
  }

  const inputStyle: React.CSSProperties = {
    width: '100%', boxSizing: 'border-box',
    padding: '8px 10px', fontSize: 13,
    background: 'var(--surface-2)', border: '1px solid var(--rule)',
    borderRadius: 6, color: 'var(--fg)', outline: 'none',
  };
  const labelStyle: React.CSSProperties = {
    display: 'block', fontSize: 12, fontWeight: 500,
    color: 'var(--fg-2)', marginBottom: 5,
  };

  return (
    <div style={{
      position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.55)',
      zIndex: 500, display: 'flex', alignItems: 'center', justifyContent: 'center',
    }} onClick={onClose}>
      <div style={{
        background: 'var(--surface)', border: '1px solid var(--rule)',
        borderRadius: 12, padding: '24px 24px 20px', width: 420,
        boxShadow: '0 16px 48px rgba(0,0,0,0.4)',
      }} onClick={e => e.stopPropagation()}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 20 }}>
          <h2 style={{ margin: 0, fontSize: 16, fontWeight: 700, color: 'var(--fg)' }}>Add org node</h2>
          <button onClick={onClose} style={{ background: 'none', border: 'none', color: 'var(--fg-3)', cursor: 'pointer', fontSize: 18, lineHeight: 1 }}>✕</button>
        </div>

        {preselectedParentName && (
          <div style={{ marginBottom: 16, padding: '8px 12px', background: 'var(--surface-2)', borderRadius: 6, fontSize: 12, color: 'var(--fg-2)' }}>
            Adding child under: <strong style={{ color: 'var(--fg)' }}>{preselectedParentName}</strong>
          </div>
        )}

        <form onSubmit={handleSubmit} style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
          {error && (
            <div style={{ padding: '8px 12px', background: 'rgba(220,38,38,0.12)', border: '1px solid rgba(220,38,38,0.4)', borderRadius: 6, fontSize: 12, color: '#FCA5A5' }}>
              {error}
            </div>
          )}

          <div>
            <label style={labelStyle}>Name *</label>
            <input
              type="text"
              required
              autoFocus
              value={form.name}
              onChange={e => setForm(f => ({ ...f, name: e.target.value }))}
              placeholder="e.g. Engineering, Platform Team"
              style={inputStyle}
            />
          </div>

          <div>
            <label style={labelStyle}>Type</label>
            <select
              value={form.type}
              onChange={e => setForm(f => ({ ...f, type: e.target.value as typeof NODE_TYPES[number] }))}
              style={{ ...inputStyle, cursor: 'pointer' }}
            >
              {NODE_TYPES.map(t => (
                <option key={t} value={t}>{t.charAt(0).toUpperCase() + t.slice(1)}</option>
              ))}
            </select>
          </div>

          <div>
            <label style={labelStyle}>Description</label>
            <input
              type="text"
              value={form.description}
              onChange={e => setForm(f => ({ ...f, description: e.target.value }))}
              placeholder="Optional"
              style={inputStyle}
            />
          </div>

          <div>
            <label style={labelStyle}>Location</label>
            <input
              type="text"
              value={form.location}
              onChange={e => setForm(f => ({ ...f, location: e.target.value }))}
              placeholder="e.g. Copenhagen, Remote"
              style={inputStyle}
            />
          </div>

          <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end', marginTop: 4 }}>
            <button type="button" onClick={onClose} style={{
              padding: '8px 16px', fontSize: 13, background: 'var(--surface-2)',
              border: '1px solid var(--rule)', borderRadius: 6, color: 'var(--fg)', cursor: 'pointer',
            }}>Cancel</button>
            <button type="submit" disabled={saving || !form.name.trim()} style={{
              padding: '8px 16px', fontSize: 13, fontWeight: 600,
              background: 'var(--sc-blue, #083EA7)', color: '#fff',
              border: 'none', borderRadius: 6, cursor: saving ? 'not-allowed' : 'pointer',
              opacity: saving || !form.name.trim() ? 0.7 : 1,
            }}>{saving ? 'Creating…' : 'Create node'}</button>
          </div>
        </form>
      </div>
    </div>
  );
}

export default function OrgTreePage() {
  const queryClient = useQueryClient();
  const [search, setSearch] = useState('');
  const [expandedIds, setExpandedIds] = useState<Set<string>>(new Set());
  const [showCreate, setShowCreate] = useState(false);
  const [createParent, setCreateParent] = useState<{ id: string; name: string } | null>(null);

  const { data: tree, isLoading, error } = useQuery<OrgNode>({
    queryKey: ['node-tree'],
    queryFn: () => apiFetch<OrgNode[]>('/nodes/tree').then(arr => arr[0]),
    staleTime: 30_000,
  });

  const rootId = tree?.id ?? '';

  const toggle = useCallback((id: string) => {
    setExpandedIds(prev => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }, []);

  function expandAll() {
    if (!tree) return;
    setExpandedIds(new Set(collectAllIds(tree)));
  }

  function collapseAll() {
    setExpandedIds(new Set());
  }

  function openCreate(parent?: { id: string; name: string }) {
    setCreateParent(parent ?? null);
    setShowCreate(true);
  }

  function onCreated() {
    queryClient.invalidateQueries({ queryKey: ['node-tree'] });
    // Auto-expand the parent so the new child is visible
    if (createParent) {
      setExpandedIds(prev => new Set([...prev, createParent.id]));
    }
  }

  if (isLoading) return <LoadingState rows={6} />;
  if (error) return <ErrorState error={error as Error} />;

  return (
    <div>
      <div style={{ marginBottom: 24 }}>
        <h1 style={{ fontSize: 22, fontWeight: 700, color: 'var(--fg)', margin: 0 }}>
          Org Tree
        </h1>
        <p style={{ fontSize: 13, color: 'var(--fg-3)', margin: '4px 0 0' }}>
          Full hierarchy. Click any node to view its details. Roles are inherited downward.
        </p>
      </div>

      <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 16, flexWrap: 'wrap' }}>
        <input
          type="text"
          placeholder="Search nodes…"
          value={search}
          onChange={e => setSearch(e.target.value)}
          style={{
            flex: '1 1 240px', padding: '7px 12px', fontSize: 13,
            background: 'var(--surface-2)', border: '1px solid var(--rule)',
            borderRadius: 6, color: 'var(--fg)',
          }}
        />
        <button onClick={expandAll} style={{ padding: '7px 14px', fontSize: 12, background: 'var(--surface-2)', border: '1px solid var(--rule)', borderRadius: 6, color: 'var(--fg)', cursor: 'pointer' }}>
          Expand all
        </button>
        <button onClick={collapseAll} style={{ padding: '7px 14px', fontSize: 12, background: 'var(--surface-2)', border: '1px solid var(--rule)', borderRadius: 6, color: 'var(--fg)', cursor: 'pointer' }}>
          Collapse all
        </button>
        <button
          onClick={() => openCreate()}
          style={{
            padding: '7px 14px', fontSize: 12, fontWeight: 600,
            background: 'var(--sc-blue, #083EA7)', color: '#fff',
            border: 'none', borderRadius: 6, cursor: 'pointer',
          }}
        >
          + Add node
        </button>
      </div>

      <OrgTree
        expandedIds={expandedIds}
        onToggle={toggle}
        onAddChild={node => openCreate({ id: node.id, name: node.name })}
        searchQuery={search}
      />

      {showCreate && rootId && (
        <CreateNodeModal
          rootId={rootId}
          preselectedParentId={createParent?.id}
          preselectedParentName={createParent?.name}
          onClose={() => setShowCreate(false)}
          onCreated={onCreated}
        />
      )}
    </div>
  );
}
