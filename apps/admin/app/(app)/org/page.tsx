'use client';

import React, { useState, useCallback } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { apiFetch } from '../../../lib/apiClient';
import { LoadingState, ErrorState } from '../_components/PageStates';
import { OrgTree, collectAllIds } from '../_components/OrgTree';
import { OrgNode, typeBadgeColor } from '../_components/nodeTypes';
import { NodePanel, PanelTab } from './_components/NodePanel';

const NODE_TYPES = ['area', 'unit', 'team'] as const;

const NODE_TYPE_META: Record<string, { label: string; description: string }> = {
  area:  { label: 'Area',  description: 'Top-level division (e.g. Engineering, Data). An area_owner here has access to everything below it.' },
  unit:  { label: 'Unit',  description: 'Group of related teams within an area (e.g. Platform, Mobile). Has a unit_lead role.' },
  team:  { label: 'Team',  description: 'Leaf node where engineers are members. Inherits policies and budgets from nodes above it.' },
};

const CHILD_TYPE: Record<string, typeof NODE_TYPES[number]> = {
  area: 'unit',
  unit: 'team',
  team: 'team',
};

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
  initialType,
  onClose,
  onCreated,
}: {
  rootId: string;
  preselectedParentId?: string;
  preselectedParentName?: string;
  initialType?: typeof NODE_TYPES[number];
  onClose: () => void;
  onCreated: () => void;
}) {
  const [form, setForm] = useState<CreateNodeForm>({
    name: '',
    type: initialType ?? 'area',
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
    borderRadius: 6, color: 'var(--fg-1)', outline: 'none',
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
        boxShadow: 'var(--shadow-pop)',
      }} onClick={e => e.stopPropagation()}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 20 }}>
          <h2 style={{ margin: 0, fontSize: 16, fontWeight: 700, color: 'var(--fg-1)' }}>Add org node</h2>
          <button onClick={onClose} style={{ background: 'none', border: 'none', color: 'var(--fg-3)', cursor: 'pointer', fontSize: 18, lineHeight: 1 }}>✕</button>
        </div>

        {preselectedParentName && (
          <div style={{ marginBottom: 16, padding: '8px 12px', background: 'var(--surface-2)', borderRadius: 6, fontSize: 12, color: 'var(--fg-2)' }}>
            Adding child under: <strong style={{ color: 'var(--fg-1)' }}>{preselectedParentName}</strong>
          </div>
        )}

        <form onSubmit={handleSubmit} style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
          {error && (
            <div style={{ padding: '8px 12px', background: 'var(--bad-soft)', border: '1px solid var(--bad)', borderRadius: 6, fontSize: 12, color: 'var(--bad)' }}>
              {error}
            </div>
          )}

          <div>
            <label style={labelStyle}>Name *</label>
            <input
              type="text"
              required
              autoFocus
              autoComplete="off"
              value={form.name}
              onChange={e => setForm(f => ({ ...f, name: e.target.value }))}
              placeholder="e.g. Engineering, Platform Team"
              style={inputStyle}
            />
          </div>

          <div>
            <label style={labelStyle}>Type</label>
            <div style={{ display: 'flex', gap: 6 }}>
              {NODE_TYPES.map(t => {
                const selected = form.type === t;
                return (
                  <button
                    key={t}
                    type="button"
                    onClick={() => setForm(f => ({ ...f, type: t }))}
                    style={{
                      flex: 1, padding: '7px 0', fontSize: 12.5, fontWeight: selected ? 600 : 400,
                      background: selected ? 'var(--accent)' : 'var(--surface-2)',
                      color: selected ? '#fff' : 'var(--fg-2)',
                      border: `1px solid ${selected ? 'var(--accent)' : 'var(--rule)'}`,
                      borderRadius: 6, cursor: 'pointer', transition: 'all 0.1s',
                    }}
                  >
                    {NODE_TYPE_META[t].label}
                  </button>
                );
              })}
            </div>
            <p style={{ margin: '6px 0 0', fontSize: 11.5, color: 'var(--fg-3)', lineHeight: 1.4 }}>
              {NODE_TYPE_META[form.type].description}
            </p>
          </div>

          <div>
            <label style={labelStyle}>Description</label>
            <input
              type="text"
              value={form.description}
              onChange={e => setForm(f => ({ ...f, description: e.target.value }))}
              autoComplete="off"
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
              autoComplete="off"
              placeholder="e.g. Copenhagen, Remote"
              style={inputStyle}
            />
          </div>

          <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end', marginTop: 4 }}>
            <button type="button" onClick={onClose} style={{
              padding: '8px 16px', fontSize: 13, background: 'var(--surface-2)',
              border: '1px solid var(--rule)', borderRadius: 6, color: 'var(--fg-1)', cursor: 'pointer',
            }}>Cancel</button>
            <button type="submit" disabled={saving || !form.name.trim()} style={{
              padding: '8px 16px', fontSize: 13, fontWeight: 600,
              background: 'var(--accent)', color: '#fff',
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
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState<PanelTab>('overview');
  const [showCreate, setShowCreate] = useState(false);
  const [createParent, setCreateParent] = useState<{ id: string; name: string; type: string } | null>(null);

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

  function handleSelect(node: OrgNode) {
    setSelectedId(node.id);
    setActiveTab('overview');
    if ((node.children?.length ?? 0) > 0) {
      setExpandedIds(prev => new Set([...prev, node.id]));
    }
  }

  function handleAssignMember(node: OrgNode) {
    setSelectedId(node.id);
    setActiveTab('members');
    setExpandedIds(prev => new Set([...prev, node.id]));
  }

  function handleSelectById(nodeId: string) {
    setSelectedId(nodeId);
    setActiveTab('overview');
    setExpandedIds(prev => new Set([...prev, nodeId]));
  }

  function openCreate(parent?: { id: string; name: string; type: string }) {
    setCreateParent(parent ?? null);
    setShowCreate(true);
  }

  function onCreated() {
    queryClient.invalidateQueries({ queryKey: ['node-tree'] });
    if (createParent) {
      setExpandedIds(prev => new Set([...prev, createParent.id]));
    }
  }

  if (isLoading) return <LoadingState rows={6} />;
  if (error) return <ErrorState error={error as Error} />;

  return (
    <div>
      {/* Page header */}
      <div style={{ marginBottom: 16 }}>
        <h1 style={{ fontSize: 22, fontWeight: 700, color: 'var(--fg-1)', margin: 0 }}>
          Org Tree
        </h1>
        <p style={{ fontSize: 13, color: 'var(--fg-3)', margin: '4px 0 0' }}>
          Full hierarchy. Click any node to view its details. Roles and budgets inherit downward.
        </p>
      </div>

      {/* Type legend */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 16, flexWrap: 'wrap' }}>
        {NODE_TYPES.map((t, i) => {
          const color = typeBadgeColor(t);
          return (
            <React.Fragment key={t}>
              <span
                title={NODE_TYPE_META[t].description}
                style={{
                  display: 'inline-flex', alignItems: 'center', gap: 5,
                  padding: '3px 8px 3px 6px', borderRadius: 5,
                  background: `${color}1a`, border: `1px solid ${color}44`,
                  fontSize: 12, color, fontWeight: 500, cursor: 'default',
                }}
              >
                <span style={{ width: 8, height: 8, borderRadius: 2, background: color, display: 'inline-block' }} />
                {NODE_TYPE_META[t].label}
              </span>
              {i < NODE_TYPES.length - 1 && (
                <span style={{ fontSize: 12, color: 'var(--fg-3)' }}>→</span>
              )}
            </React.Fragment>
          );
        })}
        <span style={{ fontSize: 11, color: 'var(--fg-3)', marginLeft: 4 }}>
          Hover legend items for description
        </span>
      </div>

      {/* Search + controls */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 16, flexWrap: 'wrap' }}>
        <input
          type="text"
          placeholder="Search nodes…"
          value={search}
          onChange={e => setSearch(e.target.value)}
          style={{
            flex: '1 1 200px', padding: '7px 12px', fontSize: 13,
            background: 'var(--surface-2)', border: '1px solid var(--rule)',
            borderRadius: 6, color: 'var(--fg-1)',
          }}
        />
        <button onClick={expandAll} style={{ padding: '7px 14px', fontSize: 12, background: 'var(--surface-2)', border: '1px solid var(--rule)', borderRadius: 6, color: 'var(--fg-1)', cursor: 'pointer' }}>
          Expand all
        </button>
        <button onClick={collapseAll} style={{ padding: '7px 14px', fontSize: 12, background: 'var(--surface-2)', border: '1px solid var(--rule)', borderRadius: 6, color: 'var(--fg-1)', cursor: 'pointer' }}>
          Collapse all
        </button>
        <button
          onClick={() => openCreate()}
          style={{
            padding: '7px 14px', fontSize: 12, fontWeight: 600,
            background: 'var(--accent)', color: '#fff',
            border: 'none', borderRadius: 6, cursor: 'pointer',
          }}
        >
          + Add node
        </button>
      </div>

      {/* Split-pane */}
      <div style={{ display: 'flex', gap: 0, flexWrap: 'wrap', alignItems: 'flex-start' }}>
        {/* Left: tree */}
        <div style={{
          flex: '1 1 320px', minWidth: 260,
          borderRight: selectedId ? '1px solid var(--rule)' : 'none',
          paddingRight: selectedId ? 0 : 0,
        }}>
          <OrgTree
            expandedIds={expandedIds}
            onToggle={toggle}
            onSelect={handleSelect}
            onAddChild={node => openCreate({ id: node.id, name: node.name, type: node.type })}
            onAssignMember={handleAssignMember}
            selectedId={selectedId ?? undefined}
            searchQuery={search}
          />
        </div>

        {/* Right: detail panel */}
        {selectedId && (
          <div style={{
            flex: '2 1 440px', minWidth: 0,
            background: 'var(--surface)', border: '1px solid var(--rule)',
            borderLeft: 'none', borderRadius: '0 8px 8px 0',
            overflow: 'hidden',
            minHeight: 480,
          }}>
            <NodePanel
              nodeId={selectedId}
              activeTab={activeTab}
              onTabChange={setActiveTab}
              onSelectNode={handleSelectById}
              onAddChild={node => openCreate({ id: node.id, name: node.name, type: node.type })}
              onClose={() => setSelectedId(null)}
            />
          </div>
        )}
      </div>

      {/* Create modal */}
      {showCreate && rootId && (
        <CreateNodeModal
          rootId={rootId}
          preselectedParentId={createParent?.id}
          preselectedParentName={createParent?.name}
          initialType={createParent?.type ? CHILD_TYPE[createParent.type] : 'area'}
          onClose={() => setShowCreate(false)}
          onCreated={onCreated}
        />
      )}
    </div>
  );
}
