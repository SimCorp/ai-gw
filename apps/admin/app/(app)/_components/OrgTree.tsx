'use client';

import React, { useState, useCallback } from 'react';
import { useRouter } from 'next/navigation';
import { useQuery } from '@tanstack/react-query';
import { apiFetch } from '../../../lib/apiClient';
import { LoadingState, ErrorState } from './PageStates';
import { OrgNode, TypeBadge, typeBadgeColor } from './nodeTypes';

// ── Props ─────────────────────────────────────────────────────────────────────

export interface OrgTreeProps {
  /** In picker mode, clicking a node calls this instead of navigating */
  onSelect?: (node: OrgNode) => void;
  /** Externally controlled expanded IDs (optional; tree manages its own state when not provided) */
  expandedIds?: Set<string>;
  onToggle?: (id: string) => void;
  /** Called when user clicks "+ child" on a node */
  onAddChild?: (node: OrgNode) => void;
  /** Highlight/filter nodes matching this string */
  searchQuery?: string;
  /** Currently selected node ID — drives selection highlight */
  selectedId?: string;
  /** Called when "+ member" is clicked on a team node */
  onAssignMember?: (node: OrgNode) => void;
}

// ── Helpers ───────────────────────────────────────────────────────────────────

function Chevron({ open }: { open: boolean }) {
  return (
    <span style={{
      display: 'inline-block', width: 14, flexShrink: 0,
      color: 'var(--fg-3)', fontSize: 10, lineHeight: 1,
      transform: open ? 'rotate(90deg)' : 'none',
      transition: 'transform 0.15s',
    }}>▶</span>
  );
}

// ── OrgTreeNode (recursive) ───────────────────────────────────────────────────

function OrgTreeNode({
  node, depth, expandedIds, onToggle, onSelect, onAddChild, onAssignMember, selectedId, searchQuery,
}: {
  node: OrgNode;
  depth: number;
  expandedIds: Set<string>;
  onToggle: (id: string) => void;
  onSelect: (node: OrgNode) => void;
  onAddChild?: (node: OrgNode) => void;
  onAssignMember?: (node: OrgNode) => void;
  selectedId?: string;
  searchQuery?: string;
}) {
  const open = expandedIds.has(node.id);
  const hasChildren = (node.children?.length ?? 0) > 0;
  const color = node.color ?? typeBadgeColor(node.type);
  const indent = depth * 20;
  const isSelected = node.id === selectedId;

  // Root node renders its children directly without its own row
  if (node.type === 'root') {
    return (
      <>
        {node.children?.map(child => (
          <OrgTreeNode
            key={child.id}
            node={child}
            depth={0}
            expandedIds={expandedIds}
            onToggle={onToggle}
            onSelect={onSelect}
            onAddChild={onAddChild}
            onAssignMember={onAssignMember}
            selectedId={selectedId}
            searchQuery={searchQuery}
          />
        ))}
      </>
    );
  }

  const matchesSearch = searchQuery
    ? node.name.toLowerCase().includes(searchQuery.toLowerCase())
    : true;

  const baseBg = isSelected ? `${color}22` : depth === 0 ? `${color}0d` : undefined;
  const borderLeft = isSelected || depth === 0 ? `3px solid ${color}` : undefined;
  const hoverBg = isSelected ? `${color}33` : depth === 0 ? `${color}1a` : 'var(--surface-2)';

  return (
    <div style={{ opacity: searchQuery && !matchesSearch ? 0.35 : 1 }}>
      <div
        style={{
          display: 'flex', alignItems: 'center', gap: 8,
          padding: `9px 16px 9px ${16 + indent}px`,
          borderBottom: '1px solid var(--rule)',
          userSelect: 'none',
          background: baseBg,
          borderLeft,
        }}
        onMouseEnter={e => {
          (e.currentTarget as HTMLElement).style.background = hoverBg;
          const btn = (e.currentTarget as HTMLElement).querySelector('.add-child-btn') as HTMLElement | null;
          if (btn) btn.style.opacity = '1';
          const assignBtn = (e.currentTarget as HTMLElement).querySelector('.assign-member-btn') as HTMLElement | null;
          if (assignBtn) assignBtn.style.opacity = '1';
        }}
        onMouseLeave={e => {
          (e.currentTarget as HTMLElement).style.background = baseBg ?? '';
          const btn = (e.currentTarget as HTMLElement).querySelector('.add-child-btn') as HTMLElement | null;
          if (btn) btn.style.opacity = '0';
          const assignBtn = (e.currentTarget as HTMLElement).querySelector('.assign-member-btn') as HTMLElement | null;
          if (assignBtn) assignBtn.style.opacity = '0';
        }}
      >
        {/* Chevron — toggles expand only, no selection */}
        <span
          onClick={e => { e.stopPropagation(); if (hasChildren) onToggle(node.id); }}
          style={{ display: 'flex', alignItems: 'center', cursor: hasChildren ? 'pointer' : 'default', flexShrink: 0 }}
        >
          {hasChildren ? <Chevron open={open} /> : <span style={{ width: 14, display: 'inline-block' }} />}
        </span>

        {/* Name + badge area — selects node */}
        <span
          onClick={() => onSelect(node)}
          style={{ display: 'flex', alignItems: 'center', gap: 8, flex: 1, cursor: 'pointer', minWidth: 0 }}
        >
          <span style={{ display: 'inline-block', width: 10, height: 10, borderRadius: 3, background: color, flexShrink: 0 }} />
          <span style={{ fontSize: 13, fontWeight: depth === 0 ? 600 : 500, color: 'var(--fg)', flex: 1, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
            {node.name}
          </span>
          <TypeBadge type={node.type} />
          {hasChildren && (
            <span style={{ fontSize: 11, color: 'var(--fg-3)', background: 'var(--surface-3)', borderRadius: 10, padding: '1px 7px', marginLeft: 4, flexShrink: 0 }}>
              {node.children!.length}
            </span>
          )}
          <span style={{ fontSize: 11, color: 'var(--fg-3)', fontFamily: 'monospace', marginLeft: 4, flexShrink: 0 }}>
            {node.slug}
          </span>
        </span>

        {/* + member button (teams only, when handler provided) */}
        {onAssignMember && node.type === 'team' && (
          <button
            className="assign-member-btn"
            onClick={e => { e.stopPropagation(); onAssignMember(node); }}
            title="Assign member"
            style={{
              opacity: 0, transition: 'opacity 0.1s',
              background: 'none', border: '1px solid var(--rule)',
              borderRadius: 4, padding: '2px 7px', fontSize: 11,
              color: 'var(--fg-2)', cursor: 'pointer', flexShrink: 0,
            }}
          >
            + member
          </button>
        )}

        {/* + child button */}
        {onAddChild && (
          <button
            className="add-child-btn"
            onClick={e => { e.stopPropagation(); onAddChild(node); }}
            title="Add child node"
            style={{
              opacity: 0, transition: 'opacity 0.1s',
              background: 'none', border: '1px solid var(--rule)',
              borderRadius: 4, padding: '2px 7px', fontSize: 11,
              color: 'var(--fg-2)', cursor: 'pointer', flexShrink: 0,
            }}
          >
            + child
          </button>
        )}
      </div>

      {open && hasChildren && (
        <div>
          {node.children!.map(child => (
            <OrgTreeNode
              key={child.id}
              node={child}
              depth={depth + 1}
              expandedIds={expandedIds}
              onToggle={onToggle}
              onSelect={onSelect}
              onAddChild={onAddChild}
              onAssignMember={onAssignMember}
              selectedId={selectedId}
              searchQuery={searchQuery}
            />
          ))}
        </div>
      )}
    </div>
  );
}

// ── OrgTree ───────────────────────────────────────────────────────────────────

export function OrgTree({ onSelect, expandedIds: extExpandedIds, onToggle: extOnToggle, onAddChild, onAssignMember, selectedId, searchQuery }: OrgTreeProps) {
  const router = useRouter();
  const [internalExpanded, setInternalExpanded] = useState<Set<string>>(new Set());

  const expandedIds = extExpandedIds ?? internalExpanded;

  const toggle = useCallback((id: string) => {
    if (extOnToggle) {
      extOnToggle(id);
    } else {
      setInternalExpanded(prev => {
        const next = new Set(prev);
        if (next.has(id)) next.delete(id);
        else next.add(id);
        return next;
      });
    }
  }, [extOnToggle]);

  const { data: tree, isLoading, error } = useQuery<OrgNode>({
    queryKey: ['node-tree'],
    queryFn: () => apiFetch<OrgNode[]>('/nodes/tree').then(arr => arr[0]),
    staleTime: 30_000,
  });

  const handleSelect = useCallback((node: OrgNode) => {
    if (onSelect) {
      onSelect(node);
    } else {
      router.push(`/nodes/${node.id}`);
    }
  }, [onSelect, router]);

  if (isLoading) return <LoadingState rows={6} />;
  if (error) return <ErrorState error={error as Error} />;
  if (!tree) return null;

  return (
    <div style={{
      background: 'var(--surface)',
      border: '1px solid var(--rule)',
      borderRadius: 8,
      overflow: 'hidden',
    }}>
      {(!tree.children || tree.children.length === 0) && (
        <div style={{ padding: 32, textAlign: 'center', color: 'var(--fg-3)', fontSize: 13 }}>
          No nodes yet.
        </div>
      )}
      <OrgTreeNode
        node={tree}
        depth={0}
        expandedIds={expandedIds}
        onToggle={toggle}
        onSelect={handleSelect}
        onAddChild={onAddChild}
        onAssignMember={onAssignMember}
        selectedId={selectedId}
        searchQuery={searchQuery}
      />
    </div>
  );
}

// ── Exported helpers for org/page.tsx expand-all ──────────────────────────────

/** Collect all non-root node IDs from the tree for expand-all */
export function collectAllIds(node: OrgNode): string[] {
  if (!node.children) return [];
  const ids: string[] = [];
  for (const child of node.children) {
    if (child.type !== 'root') ids.push(child.id);
    ids.push(...collectAllIds(child));
  }
  return ids;
}
