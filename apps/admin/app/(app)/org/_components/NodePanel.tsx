'use client';

import React, { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { apiFetch } from '../../../../lib/apiClient';
import { LoadingState, ErrorState } from '../../_components/PageStates';
import { OrgNode, TypeBadge, typeBadgeColor } from '../../_components/nodeTypes';
import { PolicyPanel } from '../../nodes/[id]/_components/PolicyPanel';
import { BudgetPanel } from '../../nodes/[id]/_components/BudgetPanel';
import { MembersTab } from './MembersTab';
import { AccessTab } from './AccessTab';

export type PanelTab = 'overview' | 'members' | 'policy' | 'budget' | 'access';

interface NodeDetail extends OrgNode {
  member_count: number;
  spend_mtd: number;
  children: OrgNode[];
}

export interface NodePanelProps {
  nodeId: string;
  activeTab: PanelTab;
  onTabChange: (tab: PanelTab) => void;
  onSelectNode: (nodeId: string) => void;
  onAddChild: (node: OrgNode) => void;
  onClose: () => void;
}

const TABS: { id: PanelTab; label: string }[] = [
  { id: 'overview', label: 'Overview' },
  { id: 'members', label: 'Members' },
  { id: 'policy', label: 'Policy' },
  { id: 'budget', label: 'Budget' },
  { id: 'access', label: 'Access' },
];

function KpiCard({ label, value, muted }: { label: string; value: string; muted?: boolean }) {
  return (
    <div style={{
      padding: '14px 16px',
      background: 'var(--surface)',
      border: '1px solid var(--rule)',
      borderRadius: 8,
    }}>
      <div style={{ fontSize: 11, fontWeight: 500, color: 'var(--fg-3)', marginBottom: 4, textTransform: 'uppercase', letterSpacing: '0.06em' }}>
        {label}
      </div>
      <div style={{ fontSize: 18, fontWeight: 700, color: muted ? 'var(--fg-3)' : 'var(--fg-1)' }}>
        {value}
      </div>
    </div>
  );
}

export function NodePanel({ nodeId, activeTab, onTabChange, onSelectNode, onAddChild, onClose }: NodePanelProps) {
  const queryClient = useQueryClient();
  const [editMode, setEditMode] = useState(false);
  const [editName, setEditName] = useState('');
  const [editDesc, setEditDesc] = useState('');
  const [editLoc, setEditLoc] = useState('');

  const { data: node, isLoading, error } = useQuery<NodeDetail>({
    queryKey: ['node', nodeId],
    queryFn: () => apiFetch(`/nodes/${nodeId}`),
    staleTime: 30_000,
  });

  const updateMutation = useMutation({
    mutationFn: (body: { name: string; description: string | null; location: string | null }) =>
      apiFetch(`/nodes/${nodeId}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['node', nodeId] });
      queryClient.invalidateQueries({ queryKey: ['node-tree'] });
      setEditMode(false);
    },
  });

  const deleteMutation = useMutation({
    mutationFn: () => apiFetch(`/nodes/${nodeId}`, { method: 'DELETE' }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['node-tree'] });
      onClose();
    },
  });

  if (isLoading) return <div style={{ padding: 24 }}><LoadingState rows={6} /></div>;
  if (error) return <div style={{ padding: 24 }}><ErrorState error={error as Error} /></div>;
  if (!node) return null;

  const color = node.color ?? typeBadgeColor(node.type);
  const typeIcon = node.type === 'area' ? '🏢' : node.type === 'unit' ? '🔷' : '👥';

  function startEdit() {
    setEditName(node!.name);
    setEditDesc(node!.description ?? '');
    setEditLoc(node!.location ?? '');
    setEditMode(true);
  }

  function handleSave() {
    updateMutation.mutate({
      name: editName.trim(),
      description: editDesc.trim() || null,
      location: editLoc.trim() || null,
    });
  }

  function handleDelete() {
    if (confirm(`Delete "${node!.name}"? This cannot be undone.`)) {
      deleteMutation.mutate();
    }
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%', minHeight: 0 }}>
      {/* Header */}
      <div style={{
        padding: '16px 20px 0',
        background: `${color}0d`,
        borderBottom: '1px solid var(--rule)',
        flexShrink: 0,
      }}>
        <div style={{ display: 'flex', alignItems: 'flex-start', gap: 10, marginBottom: 10 }}>
          <span style={{
            width: 36, height: 36, borderRadius: 8, background: color,
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            fontSize: 16, flexShrink: 0,
          }}>
            {typeIcon}
          </span>
          <div style={{ flex: 1, minWidth: 0 }}>
            {editMode ? (
              <input
                value={editName}
                onChange={e => setEditName(e.target.value)}
                style={{
                  fontSize: 15, fontWeight: 700, color: 'var(--fg-1)',
                  background: 'var(--surface-2)', border: '1px solid var(--rule)',
                  borderRadius: 5, padding: '3px 8px', width: '100%', boxSizing: 'border-box',
                }}
              />
            ) : (
              <div style={{ fontSize: 15, fontWeight: 700, color: 'var(--fg-1)', lineHeight: 1.3, wordBreak: 'break-word' }}>
                {node.name}
              </div>
            )}
            <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginTop: 4, flexWrap: 'wrap' }}>
              <TypeBadge type={node.type} />
              <span style={{ fontSize: 11, color: 'var(--fg-3)', fontFamily: 'monospace' }}>{node.slug}</span>
            </div>
          </div>
          {!editMode ? (
            <div style={{ display: 'flex', gap: 4, flexShrink: 0 }}>
              <button
                onClick={startEdit}
                style={{ padding: '4px 10px', fontSize: 11, background: 'var(--surface-2)', border: '1px solid var(--rule)', borderRadius: 5, color: 'var(--fg-1)', cursor: 'pointer' }}
              >
                Edit
              </button>
              <button
                onClick={onClose}
                style={{ padding: '4px 8px', fontSize: 14, lineHeight: 1, background: 'none', border: '1px solid var(--rule)', borderRadius: 5, color: 'var(--fg-3)', cursor: 'pointer' }}
              >
                ✕
              </button>
            </div>
          ) : (
            <div style={{ display: 'flex', gap: 4, flexShrink: 0 }}>
              <button
                onClick={handleSave}
                disabled={updateMutation.isPending || !editName.trim()}
                style={{ padding: '4px 10px', fontSize: 11, background: 'var(--accent)', color: '#fff', border: 'none', borderRadius: 5, cursor: 'pointer' }}
              >
                Save
              </button>
              <button
                onClick={() => setEditMode(false)}
                style={{ padding: '4px 10px', fontSize: 11, background: 'var(--surface-2)', border: '1px solid var(--rule)', borderRadius: 5, color: 'var(--fg-1)', cursor: 'pointer' }}
              >
                Cancel
              </button>
            </div>
          )}
        </div>

        {editMode ? (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 6, paddingBottom: 12 }}>
            <input
              value={editDesc}
              onChange={e => setEditDesc(e.target.value)}
              placeholder="Description (optional)"
              style={{ fontSize: 12, background: 'var(--surface-2)', border: '1px solid var(--rule)', borderRadius: 5, padding: '5px 8px', color: 'var(--fg-1)', width: '100%', boxSizing: 'border-box' }}
            />
            <input
              value={editLoc}
              onChange={e => setEditLoc(e.target.value)}
              placeholder="Location (optional)"
              style={{ fontSize: 12, background: 'var(--surface-2)', border: '1px solid var(--rule)', borderRadius: 5, padding: '5px 8px', color: 'var(--fg-1)', width: '100%', boxSizing: 'border-box' }}
            />
            <div style={{ textAlign: 'right', marginTop: 2 }}>
              <button
                onClick={handleDelete}
                disabled={deleteMutation.isPending}
                style={{ padding: '4px 10px', fontSize: 11, background: 'transparent', border: '1px solid var(--bad)', borderRadius: 5, color: 'var(--bad)', cursor: 'pointer' }}
              >
                Delete node
              </button>
            </div>
          </div>
        ) : node.description ? (
          <div style={{ fontSize: 12, color: 'var(--fg-3)', marginBottom: 12, lineHeight: 1.5 }}>{node.description}</div>
        ) : null}

        {/* Tabs */}
        <div style={{ display: 'flex', gap: 0, overflowX: 'auto' }}>
          {TABS.map(t => (
            <button
              key={t.id}
              onClick={() => onTabChange(t.id)}
              style={{
                padding: '8px 14px', fontSize: 12, fontWeight: activeTab === t.id ? 600 : 400,
                background: 'none', border: 'none',
                borderBottom: `2px solid ${activeTab === t.id ? color : 'transparent'}`,
                color: activeTab === t.id ? 'var(--fg-1)' : 'var(--fg-3)',
                cursor: 'pointer', transition: 'all 0.1s', whiteSpace: 'nowrap', flexShrink: 0,
              }}
            >
              {t.label}
              {t.id === 'members' ? ` (${node.member_count ?? 0})` : ''}
            </button>
          ))}
        </div>
      </div>

      {/* Tab body */}
      <div style={{ flex: 1, overflowY: 'auto', padding: '20px' }}>
        {activeTab === 'overview' && (
          <OverviewTab node={node} onSelectNode={onSelectNode} onAddChild={onAddChild} onShowMembers={() => onTabChange('members')} />
        )}
        {activeTab === 'members' && <MembersTab nodeId={nodeId} />}
        {activeTab === 'policy' && <PolicyPanel nodeId={nodeId} nodeName={node.name} />}
        {activeTab === 'budget' && <BudgetPanel nodeId={nodeId} />}
        {activeTab === 'access' && <AccessTab nodeId={nodeId} />}
      </div>
    </div>
  );
}

function avatarColor(s: string): string {
  const colors = ['#6366f1', '#8b5cf6', '#ec4899', '#06b6d4', '#10b981', '#f59e0b', '#ef4444'];
  let h = 0;
  for (let i = 0; i < s.length; i++) h = (h * 31 + s.charCodeAt(i)) % colors.length;
  return colors[h];
}

function adminInitials(displayName: string, email: string): string {
  const src = displayName || email;
  const parts = src.split(/[\s@.]+/).filter(Boolean);
  return parts.length >= 2 ? (parts[0][0] + parts[1][0]).toUpperCase() : src.slice(0, 2).toUpperCase();
}

const ROLE_LABELS: Record<string, string> = {
  gateway_admin: 'Gateway Admin', platform_admin: 'Gateway Admin',
  area_owner: 'Area Owner', unit_lead: 'Unit Lead', team_admin: 'Team Admin',
  engineer: 'Engineer', developer: 'Engineer', reporter: 'Reporter', viewer: 'Reporter',
};
const ROLE_COLORS: Record<string, string> = {
  gateway_admin: '#F97316', platform_admin: '#F97316',
  area_owner: '#F59E0B', unit_lead: '#D946EF', team_admin: '#6366F1',
  engineer: '#0EA5E9', developer: '#0EA5E9', reporter: '#8B5CF6', viewer: '#8B5CF6',
};

function OverviewTab({ node, onSelectNode, onAddChild, onShowMembers }: {
  node: NodeDetail;
  onSelectNode: (id: string) => void;
  onAddChild: (node: OrgNode) => void;
  onShowMembers: () => void;
}) {
  const directAdmins = node.direct_admins ?? [];
  const parentAdmins = node.parent_direct_admins ?? [];
  const adminsToShow = directAdmins.length > 0 ? directAdmins : parentAdmins;
  const isInherited = directAdmins.length === 0 && parentAdmins.length > 0;

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 20 }}>
      {adminsToShow.length > 0 && (
        <div>
          <div style={{ fontSize: 12, fontWeight: 600, color: isInherited ? 'var(--fg-3)' : 'var(--fg-1)', marginBottom: 8, display: 'flex', alignItems: 'center', gap: 6 }}>
            Admins
            {isInherited && <span style={{ fontSize: 10, fontWeight: 400, color: 'var(--fg-3)' }}> — inherited from {parentAdmins[0]?.source_node_name}</span>}
          </div>
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8 }}>
            {adminsToShow.map(a => {
              const color = avatarColor(a.email);
              const roleColor = ROLE_COLORS[a.role] ?? '#999';
              const roleLabel = ROLE_LABELS[a.role] ?? a.role;
              return (
                <div key={a.id} style={{
                  display: 'flex', alignItems: 'center', gap: 7,
                  padding: '6px 10px 6px 6px',
                  background: 'var(--surface)', border: '1px solid var(--rule)',
                  borderRadius: 20, opacity: isInherited ? 0.65 : 1,
                }}>
                  <div style={{ width: 24, height: 24, borderRadius: '50%', background: color, color: '#fff', fontSize: 9, fontWeight: 700, display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0 }}>
                    {adminInitials(a.display_name, a.email)}
                  </div>
                  <div style={{ minWidth: 0 }}>
                    <div style={{ fontSize: 11, fontWeight: 600, color: 'var(--fg-1)', lineHeight: 1.2, whiteSpace: 'nowrap' }}>{a.display_name || a.email}</div>
                    <div style={{ fontSize: 9, color: roleColor, fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.04em' }}>{roleLabel}</div>
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      )}

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(140px, 1fr))', gap: 10 }}>
        <div title={node.type === 'team' ? undefined : 'Direct members only. Sub-team members counted in their team.'}>
          <KpiCard label={node.type === 'team' ? 'Members' : 'Direct members'} value={String(node.member_count ?? 0)} />
        </div>
        <KpiCard label="Children" value={String(node.children?.length ?? 0)} />
        <KpiCard label="Spend MTD" value={node.spend_mtd ? `$${node.spend_mtd.toLocaleString()}` : '$0'} muted={!node.spend_mtd} />
        {node.location && <KpiCard label="Location" value={node.location} muted />}
      </div>

      {(node.member_count ?? 0) > 0 && (
        <div>
          <button
            onClick={onShowMembers}
            style={{ fontSize: 12, color: 'var(--accent)', background: 'none', border: 'none', cursor: 'pointer', padding: 0, textDecoration: 'underline' }}
          >
            View all {node.member_count} member{node.member_count !== 1 ? 's' : ''} →
          </button>
        </div>
      )}

      {(node.children?.length ?? 0) > 0 ? (
        <div>
          <div style={{ fontSize: 13, fontWeight: 600, color: 'var(--fg-1)', marginBottom: 10 }}>Children</div>
          <div style={{ background: 'var(--surface)', border: '1px solid var(--rule)', borderRadius: 8, overflow: 'hidden' }}>
            {node.children!.map((child, i) => {
              const childColor = child.color ?? typeBadgeColor(child.type);
              return (
                <div
                  key={child.id}
                  onClick={() => onSelectNode(child.id)}
                  style={{
                    display: 'flex', alignItems: 'center', gap: 10,
                    padding: '12px 14px',
                    borderBottom: i < node.children!.length - 1 ? '1px solid var(--rule)' : 'none',
                    cursor: 'pointer',
                  }}
                  onMouseEnter={e => (e.currentTarget as HTMLElement).style.background = 'var(--surface-2)'}
                  onMouseLeave={e => (e.currentTarget as HTMLElement).style.background = ''}
                >
                  <span style={{ width: 10, height: 10, borderRadius: 3, background: childColor, flexShrink: 0, display: 'inline-block' }} />
                  <span style={{ flex: 1, fontSize: 13, fontWeight: 500, color: 'var(--fg-1)' }}>{child.name}</span>
                  <TypeBadge type={child.type} />
                  <span style={{ fontSize: 11, color: 'var(--fg-3)' }}>→</span>
                </div>
              );
            })}
          </div>
          <button
            onClick={() => onAddChild(node)}
            style={{
              marginTop: 8, padding: '6px 12px', fontSize: 12,
              background: 'var(--surface-2)', border: '1px solid var(--rule)',
              borderRadius: 5, color: 'var(--fg-2)', cursor: 'pointer',
            }}
          >
            + Add child node
          </button>
        </div>
      ) : (
        <div style={{ textAlign: 'center', padding: '20px 0' }}>
          <div style={{ fontSize: 12, color: 'var(--fg-3)', marginBottom: 10 }}>No child nodes yet.</div>
          <button
            onClick={() => onAddChild(node)}
            style={{
              padding: '7px 14px', fontSize: 12, fontWeight: 600,
              background: 'var(--accent)', color: '#fff',
              border: 'none', borderRadius: 6, cursor: 'pointer',
            }}
          >
            + Add child node
          </button>
        </div>
      )}
    </div>
  );
}
