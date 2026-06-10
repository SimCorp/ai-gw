'use client';

import React from 'react';
import Link from 'next/link';
import { useQuery } from '@tanstack/react-query';
import { apiFetch } from '../../../lib/apiClient';
import { OrgNode } from './nodeTypes';

interface BreadcrumbProps {
  nodeId: string;
}

export function Breadcrumb({ nodeId }: BreadcrumbProps) {
  const { data: ancestry } = useQuery<OrgNode[]>({
    queryKey: ['node-ancestry', nodeId],
    queryFn: () => apiFetch(`/nodes/${nodeId}/ancestry`),
    staleTime: 60_000,
  });

  if (!ancestry) return null;

  // Filter out root node from display
  const visible = ancestry.filter(n => n.type !== 'root');

  // Return null if nothing to show (at root or one below root)
  if (visible.length <= 1) return null;

  const ancestors = visible.slice(0, -1);
  const current = visible[visible.length - 1];

  return (
    <nav style={{
      display: 'flex',
      alignItems: 'center',
      gap: 4,
      fontSize: 12,
      color: 'var(--fg-3)',
      marginBottom: 12,
      flexWrap: 'wrap',
    }}>
      {ancestors.map((node, i) => (
        <React.Fragment key={node.id}>
          <Link
            href={`/admin/nodes/${node.id}`}
            style={{
              color: 'var(--accent-text)',
              textDecoration: 'none',
              fontWeight: 500,
            }}
            onMouseEnter={e => { (e.currentTarget as HTMLElement).style.textDecoration = 'underline'; }}
            onMouseLeave={e => { (e.currentTarget as HTMLElement).style.textDecoration = 'none'; }}
          >
            {node.name}
          </Link>
          <span style={{ color: 'var(--fg-3)', opacity: 0.6, padding: '0 2px' }}>›</span>
        </React.Fragment>
      ))}
      <span style={{ color: 'var(--fg)', fontWeight: 500 }}>{current.name}</span>
    </nav>
  );
}
