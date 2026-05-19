'use client';

import React, { useState, useCallback } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { LoadingState, ErrorState } from '../_components/PageStates';
import { apiFetch } from '../../../lib/apiClient';

// ── Types ─────────────────────────────────────────────────────────────────────

interface Area {
  id: string;
  name: string;
  slug: string;
  color: string | null;
  description: string | null;
  team_count: number;
}

interface Unit {
  id: string;
  area_id: string;
  name: string;
  slug: string;
  color: string | null;
  parent_unit_id: string | null;
  team_count: number;
}

interface Team {
  id: string;
  name: string;
  slug: string;
  area_id: string | null;
  unit_id: string | null;
  area_color: string | null;
  monthly_budget_usd: number | null;
}

interface RoleEntry {
  role: string;
  scope_type: string;
  scope_id: string | null;
}

interface Member {
  id: string;
  email: string;
  display_name: string;
  roles: RoleEntry[];
}

interface TreeUnit extends Unit {
  children: TreeUnit[];
  teams: Team[];
}

interface TreeArea extends Area {
  units: TreeUnit[];
  directTeams: Team[];
}

// ── Data assembly ─────────────────────────────────────────────────────────────

function buildTree(areas: Area[], units: Unit[], teams: Team[]): TreeArea[] {
  const buildSubUnits = (parentId: string | null, areaId: string): TreeUnit[] =>
    units
      .filter(u => u.area_id === areaId && u.parent_unit_id === parentId)
      .map(u => ({
        ...u,
        children: buildSubUnits(u.id, areaId),
        teams: teams.filter(t => t.unit_id === u.id),
      }));

  return areas.map(a => ({
    ...a,
    units: buildSubUnits(null, a.id),
    directTeams: teams.filter(t => t.area_id === a.id && !t.unit_id),
  }));
}

// ── Colour helpers ────────────────────────────────────────────────────────────

const ROLE_COLORS: Record<string, string> = {
  platform_admin: '#EF3E4A',
  area_owner: '#FB9B2A',
  unit_lead: '#9D2E7B',
  team_admin: '#0A7BD7',
  developer: '#1D958E',
  viewer: '#4B17B6',
  service_account: '#888',
};

const ROLE_LABELS: Record<string, string> = {
  platform_admin: 'Platform Admin',
  area_owner: 'Area Owner',
  unit_lead: 'Unit Lead',
  team_admin: 'Team Admin',
  developer: 'Developer',
  viewer: 'Viewer',
  service_account: 'Service Account',
};

function RolePill({ role }: { role: string }) {
  return (
    <span style={{
      display: 'inline-block',
      padding: '2px 7px',
      borderRadius: 10,
      fontSize: 11,
      fontWeight: 600,
      background: (ROLE_COLORS[role] ?? '#888') + '22',
      color: ROLE_COLORS[role] ?? '#888',
      border: `1px solid ${(ROLE_COLORS[role] ?? '#888')}44`,
    }}>
      {ROLE_LABELS[role] ?? role}
    </span>
  );
}

function initials(name: string): string {
  return name.split(/\s+/).map(w => w[0]).join('').toUpperCase().slice(0, 2);
}

const AVATAR_COLORS = ['#083EA7','#1D958E','#4B17B6','#FB9B2A','#9D2E7B','#0A7BD7','#EF3E4A'];
function avatarColor(s: string) {
  let h = 0;
  for (const c of s) h = (h * 31 + c.charCodeAt(0)) >>> 0;
  return AVATAR_COLORS[h % AVATAR_COLORS.length];
}

// ── Chevron ───────────────────────────────────────────────────────────────────

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

// ── Member row ────────────────────────────────────────────────────────────────

function MemberRow({ member, teamId }: { member: Member; teamId: string }) {
  const teamRoles = member.roles.filter(
    r => r.scope_type === 'team' && r.scope_id === teamId,
  );
  const globalRoles = member.roles.filter(r => r.scope_type === 'global');
  const displayRoles = teamRoles.length > 0 ? teamRoles : globalRoles;

  return (
    <div style={{
      display: 'flex', alignItems: 'center', gap: 10,
      padding: '6px 0 6px 56px',
      borderBottom: '1px solid var(--rule)',
    }}>
      <div style={{
        width: 26, height: 26, borderRadius: '50%', flexShrink: 0,
        background: avatarColor(member.email),
        display: 'flex', alignItems: 'center', justifyContent: 'center',
        fontSize: 10, fontWeight: 700, color: '#fff',
      }}>
        {initials(member.display_name || member.email)}
      </div>
      <div style={{ flex: 1, minWidth: 0 }}>
        <div style={{ fontSize: 13, fontWeight: 500, color: 'var(--fg)' }}>
          {member.display_name || member.email}
        </div>
        <div style={{ fontSize: 11, color: 'var(--fg-3)' }}>{member.email}</div>
      </div>
      <div style={{ display: 'flex', gap: 4, flexWrap: 'wrap' }}>
        {displayRoles.map((r, i) => <RolePill key={i} role={r.role} />)}
      </div>
    </div>
  );
}

// ── Team node ─────────────────────────────────────────────────────────────────

function TeamNode({
  team, depth, color, expanded, onToggle,
}: {
  team: Team; depth: number; color: string; expanded: boolean; onToggle: () => void;
}) {
  const { data: members, isLoading } = useQuery<{ total: number; items: Member[] }>({
    queryKey: ['team-members', team.id],
    queryFn: () => apiFetch(`/admin/users?team_id=${team.id}&limit=100`),
    enabled: expanded,
    staleTime: 60_000,
  });

  const indent = depth * 20;

  return (
    <div>
      <div
        onClick={onToggle}
        style={{
          display: 'flex', alignItems: 'center', gap: 8,
          padding: `7px 16px 7px ${16 + indent}px`,
          cursor: 'pointer',
          borderBottom: '1px solid var(--rule)',
          userSelect: 'none',
        }}
        onMouseEnter={e => { (e.currentTarget as HTMLElement).style.background = 'var(--surface-2)'; }}
        onMouseLeave={e => { (e.currentTarget as HTMLElement).style.background = ''; }}
      >
        <Chevron open={expanded} />
        <span style={{ fontSize: 14 }}>👥</span>
        <span style={{ fontSize: 13, fontWeight: 500, color: 'var(--fg)', flex: 1 }}>
          {team.name}
        </span>
        <span style={{ fontSize: 11, color: 'var(--fg-3)', fontFamily: 'monospace' }}>
          {team.slug}
        </span>
        {team.monthly_budget_usd != null && (
          <span style={{ fontSize: 11, color: 'var(--fg-3)', marginLeft: 8 }}>
            ${team.monthly_budget_usd.toLocaleString()}/mo
          </span>
        )}
      </div>

      {expanded && (
        <div>
          {isLoading && (
            <div style={{ padding: '8px 16px 8px 56px', fontSize: 12, color: 'var(--fg-3)' }}>
              Loading members…
            </div>
          )}
          {members?.items.length === 0 && !isLoading && (
            <div style={{ padding: '8px 16px 8px 56px', fontSize: 12, color: 'var(--fg-3)' }}>
              No members
            </div>
          )}
          {members?.items.map(m => (
            <MemberRow key={m.id} member={m} teamId={team.id} />
          ))}
        </div>
      )}
    </div>
  );
}

// ── Unit node (recursive) ─────────────────────────────────────────────────────

function UnitNode({
  unit, depth, areaColor, expandedIds, onToggle,
}: {
  unit: TreeUnit; depth: number; areaColor: string;
  expandedIds: Set<string>; onToggle: (id: string) => void;
}) {
  const nodeId = `unit-${unit.id}`;
  const open = expandedIds.has(nodeId);
  const indent = depth * 20;
  const color = unit.color ?? areaColor;
  const hasChildren = unit.children.length > 0 || unit.teams.length > 0;

  return (
    <div>
      <div
        onClick={() => hasChildren && onToggle(nodeId)}
        style={{
          display: 'flex', alignItems: 'center', gap: 8,
          padding: `7px 16px 7px ${16 + indent}px`,
          cursor: hasChildren ? 'pointer' : 'default',
          borderBottom: '1px solid var(--rule)',
          userSelect: 'none',
        }}
        onMouseEnter={e => { if (hasChildren) (e.currentTarget as HTMLElement).style.background = 'var(--surface-2)'; }}
        onMouseLeave={e => { (e.currentTarget as HTMLElement).style.background = ''; }}
      >
        {hasChildren ? <Chevron open={open} /> : <span style={{ width: 14, display: 'inline-block' }} />}
        {depth > 0 && (
          <span style={{ color: 'var(--fg-3)', fontSize: 11, marginRight: -4 }}>↳</span>
        )}
        <span style={{
          display: 'inline-block', width: 10, height: 10,
          borderRadius: 3, background: color, flexShrink: 0,
        }} />
        <span style={{ fontSize: 13, fontWeight: 500, color: 'var(--fg)', flex: 1 }}>
          {unit.name}
        </span>
        <span style={{ fontSize: 11, color: 'var(--fg-3)', fontFamily: 'monospace' }}>
          {unit.slug}
        </span>
        {unit.team_count > 0 && (
          <span style={{
            fontSize: 11, color: 'var(--fg-3)',
            background: 'var(--surface-3)', borderRadius: 10,
            padding: '1px 7px', marginLeft: 8,
          }}>
            {unit.team_count} team{unit.team_count !== 1 ? 's' : ''}
          </span>
        )}
      </div>

      {open && (
        <div>
          {unit.children.map(child => (
            <UnitNode
              key={child.id}
              unit={child}
              depth={depth + 1}
              areaColor={areaColor}
              expandedIds={expandedIds}
              onToggle={onToggle}
            />
          ))}
          {unit.teams.map(team => (
            <TeamNode
              key={team.id}
              team={team}
              depth={depth + 1}
              color={color}
              expanded={expandedIds.has(`team-${team.id}`)}
              onToggle={() => onToggle(`team-${team.id}`)}
            />
          ))}
        </div>
      )}
    </div>
  );
}

// ── Area node ─────────────────────────────────────────────────────────────────

function AreaNode({
  area, expandedIds, onToggle,
}: {
  area: TreeArea; expandedIds: Set<string>; onToggle: (id: string) => void;
}) {
  const nodeId = `area-${area.id}`;
  const open = expandedIds.has(nodeId);
  const color = area.color ?? '#888';
  const totalChildren = area.units.length + area.directTeams.length;

  return (
    <div style={{ marginBottom: 2 }}>
      {/* Area header */}
      <div
        onClick={() => totalChildren > 0 && onToggle(nodeId)}
        style={{
          display: 'flex', alignItems: 'center', gap: 10,
          padding: '10px 16px',
          background: open ? `${color}12` : 'var(--surface)',
          borderLeft: `3px solid ${color}`,
          borderBottom: '1px solid var(--rule)',
          cursor: totalChildren > 0 ? 'pointer' : 'default',
          userSelect: 'none',
        }}
        onMouseEnter={e => { if (totalChildren > 0) (e.currentTarget as HTMLElement).style.background = `${color}1a`; }}
        onMouseLeave={e => { (e.currentTarget as HTMLElement).style.background = open ? `${color}12` : 'var(--surface)'; }}
      >
        {totalChildren > 0 ? <Chevron open={open} /> : <span style={{ width: 14 }} />}
        <span style={{
          display: 'inline-block', width: 12, height: 12,
          borderRadius: 3, background: color, flexShrink: 0,
        }} />
        <span style={{ fontSize: 14, fontWeight: 600, color: 'var(--fg)', flex: 1 }}>
          {area.name}
        </span>
        <span style={{ fontSize: 11, color: 'var(--fg-3)', fontFamily: 'monospace' }}>
          {area.slug}
        </span>
        {area.description && (
          <span style={{ fontSize: 11, color: 'var(--fg-3)', maxWidth: 260, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
            {area.description}
          </span>
        )}
        <span style={{
          fontSize: 11, color, background: `${color}22`,
          borderRadius: 10, padding: '2px 8px', marginLeft: 8, fontWeight: 600,
          border: `1px solid ${color}44`,
        }}>
          {area.team_count} team{area.team_count !== 1 ? 's' : ''}
        </span>
      </div>

      {open && (
        <div style={{ borderLeft: `3px solid ${color}44`, marginLeft: 0 }}>
          {area.units.map(unit => (
            <UnitNode
              key={unit.id}
              unit={unit}
              depth={1}
              areaColor={color}
              expandedIds={expandedIds}
              onToggle={onToggle}
            />
          ))}
          {area.directTeams.map(team => (
            <TeamNode
              key={team.id}
              team={team}
              depth={1}
              color={color}
              expanded={expandedIds.has(`team-${team.id}`)}
              onToggle={() => onToggle(`team-${team.id}`)}
            />
          ))}
        </div>
      )}
    </div>
  );
}

// ── Page ──────────────────────────────────────────────────────────────────────

export default function OrgTreePage() {
  const [expandedIds, setExpandedIds] = useState<Set<string>>(new Set());
  const [search, setSearch] = useState('');

  const toggle = useCallback((id: string) => {
    setExpandedIds(prev => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }, []);

  const { data: areas, isLoading: areasLoading, error: areasError } = useQuery<Area[]>({
    queryKey: ['areas'],
    queryFn: () => apiFetch('/areas'),
  });

  const { data: units, isLoading: unitsLoading } = useQuery<Unit[]>({
    queryKey: ['units'],
    queryFn: () => apiFetch('/units'),
  });

  const { data: teams, isLoading: teamsLoading } = useQuery<Team[]>({
    queryKey: ['teams'],
    queryFn: () => apiFetch('/teams'),
  });

  const isLoading = areasLoading || unitsLoading || teamsLoading;

  if (isLoading) return <LoadingState rows={6} />;
  if (areasError) return <ErrorState message="Failed to load org tree" />;

  const tree = buildTree(areas ?? [], units ?? [], teams ?? []);

  // Filter tree by search
  const q = search.toLowerCase();
  const filtered = q
    ? tree.filter(a =>
        a.name.toLowerCase().includes(q) ||
        a.units.some(u =>
          u.name.toLowerCase().includes(q) ||
          u.teams.some(t => t.name.toLowerCase().includes(q)),
        ) ||
        a.directTeams.some(t => t.name.toLowerCase().includes(q)),
      )
    : tree;

  function expandAll() {
    const ids = new Set<string>();
    tree.forEach(a => {
      ids.add(`area-${a.id}`);
      a.units.forEach(u => {
        ids.add(`unit-${u.id}`);
        u.children.forEach(c => ids.add(`unit-${c.id}`));
      });
    });
    setExpandedIds(ids);
  }

  function collapseAll() {
    setExpandedIds(new Set());
  }

  return (
    <div>
      {/* Header */}
      <div style={{ marginBottom: 24 }}>
        <h1 style={{ fontSize: 22, fontWeight: 700, color: 'var(--fg)', margin: 0 }}>
          Org Tree
        </h1>
        <p style={{ fontSize: 13, color: 'var(--fg-3)', margin: '4px 0 0' }}>
          Full hierarchy: Areas → Units → Teams → Members. Roles are inherited downward.
        </p>
      </div>

      {/* Toolbar */}
      <div style={{
        display: 'flex', alignItems: 'center', gap: 10,
        marginBottom: 16, flexWrap: 'wrap',
      }}>
        <input
          type="text"
          placeholder="Search areas, units, teams…"
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
        <div style={{ marginLeft: 'auto', fontSize: 12, color: 'var(--fg-3)' }}>
          {tree.length} areas · {(units ?? []).length} units · {(teams ?? []).length} teams
        </div>
      </div>

      {/* Legend */}
      <div style={{
        display: 'flex', gap: 16, marginBottom: 16,
        padding: '8px 14px', background: 'var(--surface-2)',
        borderRadius: 6, border: '1px solid var(--rule)', flexWrap: 'wrap',
      }}>
        <span style={{ fontSize: 11, color: 'var(--fg-3)', fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.06em' }}>
          Role inheritance:
        </span>
        {(['area_owner', 'unit_lead', 'team_admin', 'developer'] as const).map(r => (
          <div key={r} style={{ display: 'flex', alignItems: 'center', gap: 5 }}>
            <span style={{ width: 8, height: 8, borderRadius: 2, background: ROLE_COLORS[r], display: 'inline-block' }} />
            <span style={{ fontSize: 11, color: 'var(--fg-3)' }}>{ROLE_LABELS[r]}</span>
          </div>
        ))}
        <span style={{ fontSize: 11, color: 'var(--fg-3)' }}>
          · Area Owner inherits access to all units + teams below
        </span>
      </div>

      {/* Inheritance flow diagram (text) */}
      <div style={{
        marginBottom: 20, padding: '10px 16px',
        background: 'var(--surface-2)', borderRadius: 6,
        border: '1px solid var(--rule)',
        fontSize: 12, color: 'var(--fg-3)',
        fontFamily: 'monospace',
      }}>
        Area (area_owner) &nbsp;→&nbsp; Unit (unit_lead) &nbsp;→&nbsp; Team (team_admin) &nbsp;→&nbsp; Members (developer/viewer)
        &nbsp;&nbsp;|&nbsp;&nbsp;
        Azure RBAC: Subscription → Resource Group → Resource → IAM
      </div>

      {/* Tree */}
      <div style={{
        background: 'var(--surface)',
        border: '1px solid var(--rule)',
        borderRadius: 8,
        overflow: 'hidden',
      }}>
        {filtered.length === 0 && (
          <div style={{ padding: 32, textAlign: 'center', color: 'var(--fg-3)', fontSize: 13 }}>
            {search ? 'No results match your search.' : 'No areas yet.'}
          </div>
        )}
        {filtered.map((area, i) => (
          <AreaNode
            key={area.id}
            area={area}
            expandedIds={expandedIds}
            onToggle={toggle}
          />
        ))}
      </div>
    </div>
  );
}
