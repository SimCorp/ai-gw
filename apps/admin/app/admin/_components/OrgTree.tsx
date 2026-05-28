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
  node, depth, expandedIds, onToggle, onSelect,
}: {
  node: OrgNode;
  depth: number;
  expandedIds: Set<string>;
  onToggle: (id: string) => void;
  onSelect: (node: OrgNode) => void;
}) {
  const open = expandedIds.has(node.id);
  const hasChildren = (node.children?.length ?? 0) > 0;
  const color = node.color ?? typeBadgeColor(node.type);
  const indent = depth * 20;

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
          />
        ))}
      </>
    );
  }

  return (
    <div>
      <div
        onClick={() => {
          if (hasChildren) onToggle(node.id);
          onSelect(node);
        }}
        style={{
          display: 'flex', alignItems: 'center', gap: 8,
          padding: `9px 16px 9px ${16 + indent}px`,
          cursor: 'pointer',
          borderBottom: '1px solid var(--rule)',
          userSelect: 'none',
          background: depth === 0 ? `${color}0d` : undefined,
          borderLeft: depth === 0 ? `3px solid ${color}` : undefined,
        }}
        onMouseEnter={e => { (e.currentTarget as HTMLElement).style.background = depth === 0 ? `${color}1a` : 'var(--surface-2)'; }}
        onMouseLeave={e => { (e.currentTarget as HTMLElement).style.background = depth === 0 ? `${color}0d` : ''; }}
      >
        {hasChildren ? <Chevron open={open} /> : <span style={{ width: 14, display: 'inline-block' }} />}
        <span style={{
          display: 'inline-block', width: 10, height: 10,
          borderRadius: 3, background: color, flexShrink: 0,
        }} />
        <span style={{
          fontSize: 13, fontWeight: depth === 0 ? 600 : 500,
          color: 'var(--fg)', flex: 1,
        }}>
          {node.name}
        </span>
        <TypeBadge type={node.type} />
        {hasChildren && (
          <span style={{
            fontSize: 11, color: 'var(--fg-3)',
            background: 'var(--surface-3)',
            borderRadius: 10, padding: '1px 7px', marginLeft: 6,
          }}>
            {node.children!.length}
          </span>
        )}
        <span style={{ fontSize: 11, color: 'var(--fg-3)', fontFamily: 'monospace', marginLeft: 8 }}>
          {node.slug}
        </span>
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
            />
          ))}
        </div>
      )}
    </div>
  );
}

// ── OrgTree ───────────────────────────────────────────────────────────────────

export function OrgTree({ onSelect, expandedIds: extExpandedIds, onToggle: extOnToggle }: OrgTreeProps) {
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
    queryFn: () => apiFetch('/nodes/tree'),
    staleTime: 30_000,
  });

  const handleSelect = useCallback((node: OrgNode) => {
    if (onSelect) {
      onSelect(node);
    } else {
      router.push(`/admin/nodes/${node.id}`);
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
