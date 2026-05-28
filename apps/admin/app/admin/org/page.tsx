'use client';

import React, { useState, useCallback } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { apiFetch } from '../../../lib/apiClient';
import { LoadingState, ErrorState } from '../_components/PageStates';
import { OrgTree, collectAllIds } from '../_components/OrgTree';
import { OrgNode } from '../_components/nodeTypes';

export default function OrgTreePage() {
  const [search, setSearch] = useState('');
  const [expandedIds, setExpandedIds] = useState<Set<string>>(new Set());

  const { data: tree, isLoading, error } = useQuery<OrgNode>({
    queryKey: ['node-tree'],
    queryFn: () => apiFetch('/nodes/tree'),
    staleTime: 30_000,
  });

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

  if (isLoading) return <LoadingState rows={6} />;
  if (error) return <ErrorState error={error as Error} />;

  return (
    <div>
      {/* Header */}
      <div style={{ marginBottom: 24 }}>
        <h1 style={{ fontSize: 22, fontWeight: 700, color: 'var(--fg)', margin: 0 }}>
          Org Tree
        </h1>
        <p style={{ fontSize: 13, color: 'var(--fg-3)', margin: '4px 0 0' }}>
          Full hierarchy. Click any node to view its details. Roles are inherited downward.
        </p>
      </div>

      {/* Toolbar */}
      <div style={{
        display: 'flex', alignItems: 'center', gap: 10,
        marginBottom: 16, flexWrap: 'wrap',
      }}>
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
        <button
          onClick={expandAll}
          style={{
            padding: '7px 14px', fontSize: 12, background: 'var(--surface-2)',
            border: '1px solid var(--rule)', borderRadius: 6,
            color: 'var(--fg)', cursor: 'pointer',
          }}
        >
          Expand all
        </button>
        <button
          onClick={collapseAll}
          style={{
            padding: '7px 14px', fontSize: 12, background: 'var(--surface-2)',
            border: '1px solid var(--rule)', borderRadius: 6,
            color: 'var(--fg)', cursor: 'pointer',
          }}
        >
          Collapse all
        </button>
      </div>

      {/* Tree */}
      <OrgTree expandedIds={expandedIds} onToggle={toggle} />
    </div>
  );
}
