'use client';

import React from 'react';
import { OrgNode, TypeBadge, typeBadgeColor } from './nodeTypes';

export interface ResourceTableProps {
  nodes: OrgNode[];
  onNavigate: (node: OrgNode) => void;
}

export function ResourceTable({ nodes, onNavigate }: ResourceTableProps) {
  if (nodes.length === 0) {
    return (
      <div style={{
        padding: '24px 16px', textAlign: 'center',
        fontSize: 13, color: 'var(--fg-3)',
        background: 'var(--surface)', border: '1px solid var(--rule)', borderRadius: 8,
      }}>
        No child nodes yet.
      </div>
    );
  }

  return (
    <div style={{
      background: 'var(--surface)',
      border: '1px solid var(--rule)',
      borderRadius: 8,
      overflow: 'hidden',
    }}>
      {/* Header */}
      <div style={{
        display: 'grid',
        gridTemplateColumns: '1fr 140px 80px 100px 80px',
        padding: '8px 16px',
        borderBottom: '1px solid var(--rule)',
        fontSize: 11,
        fontWeight: 600,
        color: 'var(--fg-3)',
        textTransform: 'uppercase',
        letterSpacing: '0.05em',
        background: 'var(--surface-2)',
      }}>
        <span>Name</span>
        <span>Location</span>
        <span style={{ textAlign: 'right' }}>Members</span>
        <span style={{ textAlign: 'right' }}>Spend MTD</span>
        <span />
      </div>

      {nodes.map((node, i) => {
        const color = node.color ?? typeBadgeColor(node.type);
        return (
          <div
            key={node.id}
            style={{
              display: 'grid',
              gridTemplateColumns: '1fr 140px 80px 100px 80px',
              padding: '10px 16px',
              alignItems: 'center',
              borderBottom: i < nodes.length - 1 ? '1px solid var(--rule)' : 'none',
              cursor: 'default',
            }}
            onMouseEnter={e => { (e.currentTarget as HTMLElement).style.background = 'var(--surface-2)'; }}
            onMouseLeave={e => { (e.currentTarget as HTMLElement).style.background = ''; }}
          >
            {/* Name + type badge */}
            <div style={{ display: 'flex', alignItems: 'center', gap: 8, minWidth: 0 }}>
              <span style={{
                display: 'inline-block', width: 10, height: 10,
                borderRadius: 3, background: color, flexShrink: 0,
              }} />
              <span style={{
                fontSize: 13, fontWeight: 500, color: 'var(--fg)',
                overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
              }}>
                {node.name}
              </span>
              <TypeBadge type={node.type} />
            </div>

            {/* Location */}
            <span style={{ fontSize: 12, color: 'var(--fg-3)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
              {node.location ?? '—'}
            </span>

            {/* Members */}
            <span style={{ fontSize: 12, color: 'var(--fg-3)', textAlign: 'right' }}>
              {node.member_count ?? '—'}
            </span>

            {/* Spend MTD */}
            <span style={{ fontSize: 12, color: 'var(--fg-3)', textAlign: 'right' }}>
              {node.spend_mtd != null ? `$${node.spend_mtd.toLocaleString()}` : '—'}
            </span>

            {/* Actions */}
            <div style={{ textAlign: 'right' }}>
              <button
                onClick={() => onNavigate(node)}
                style={{
                  padding: '4px 10px', fontSize: 11,
                  background: 'var(--surface-2)',
                  border: '1px solid var(--rule)',
                  borderRadius: 5, color: 'var(--fg)',
                  cursor: 'pointer',
                }}
                onMouseEnter={e => { (e.currentTarget as HTMLElement).style.background = 'var(--sc-blue)'; (e.currentTarget as HTMLElement).style.color = '#fff'; (e.currentTarget as HTMLElement).style.borderColor = 'var(--sc-blue)'; }}
                onMouseLeave={e => { (e.currentTarget as HTMLElement).style.background = 'var(--surface-2)'; (e.currentTarget as HTMLElement).style.color = 'var(--fg)'; (e.currentTarget as HTMLElement).style.borderColor = 'var(--rule)'; }}
              >
                Open
              </button>
            </div>
          </div>
        );
      })}
    </div>
  );
}
