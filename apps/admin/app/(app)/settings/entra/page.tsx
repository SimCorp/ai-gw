'use client';

import React, { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { LoadingState, ErrorState } from '../../_components/PageStates';
import { apiFetch } from '../../../../lib/apiClient';

interface GroupMapping {
  id: string;
  entra_group_id: string;
  entra_group_name: string | null;
  role: string;
  scope_type: string;
  scope_id: string | null;
  scope_name: string | null;
  created_at: string;
  created_by_email: string | null;
}

interface OrgNode { id: string; name: string; type: string; }

const ROLE_OPTIONS = [
  { value: 'platform_admin', label: 'Platform Admin' },
  { value: 'area_owner',     label: 'Area Owner' },
  { value: 'unit_lead',      label: 'Unit Lead' },
  { value: 'team_admin',     label: 'Team Admin' },
  { value: 'developer',      label: 'Developer' },
  { value: 'viewer',         label: 'Viewer' },
];

const SCOPE_TYPE_LABELS: Record<string, string> = {
  global: 'Global',
  area:   'Area',
  unit:   'Unit',
  team:   'Team',
};

const ROLE_COLORS: Record<string, string> = {
  platform_admin: 'var(--cat-coral)', area_owner: 'var(--cat-orange)', unit_lead: 'var(--cat-magenta)',
  team_admin: 'var(--accent)', developer: 'var(--cat-teal)', viewer: 'var(--cat-purple)',
};

function RolePill({ role }: { role: string }) {
  const c = ROLE_COLORS[role] ?? 'var(--fg-3)';
  return (
    <span style={{
      display: 'inline-block', padding: '2px 8px', borderRadius: 10,
      fontSize: 11, fontWeight: 600, background: `color-mix(in srgb, ${c} 13%, transparent)`, color: c, border: `1px solid color-mix(in srgb, ${c} 27%, transparent)`,
    }}>
      {ROLE_OPTIONS.find(r => r.value === role)?.label ?? role}
    </span>
  );
}

export default function EntraSettingsPage() {
  const qc = useQueryClient();
  const [showAdd, setShowAdd] = useState(false);
  const [form, setForm] = useState({
    entra_group_id: '',
    entra_group_name: '',
    role: 'developer',
    scope_type: 'global',
    scope_id: '',
  });

  const { data: mappings, isLoading, error } = useQuery<GroupMapping[]>({
    queryKey: ['entra-mappings'],
    queryFn: () => apiFetch('/settings/entra'),
  });

  // Org tree replaced the separate areas/units/teams tables; derive scope
  // pickers from the unified /nodes list filtered by node type.
  const { data: nodes } = useQuery<OrgNode[]>({
    queryKey: ['org-nodes'],
    queryFn: () => apiFetch('/nodes'),
  });
  const areas = (nodes ?? []).filter(n => n.type === 'area');
  const units = (nodes ?? []).filter(n => n.type === 'unit');
  const teamsData = (nodes ?? []).filter(n => n.type === 'team');

  const addMutation = useMutation({
    mutationFn: (body: typeof form) => apiFetch('/settings/entra', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        ...body,
        scope_id: body.scope_id || null,
      }),
    }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['entra-mappings'] });
      setShowAdd(false);
      setForm({ entra_group_id: '', entra_group_name: '', role: 'developer', scope_type: 'global', scope_id: '' });
    },
  });

  const deleteMutation = useMutation({
    mutationFn: (id: string) => apiFetch(`/settings/entra/${id}`, { method: 'DELETE' }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['entra-mappings'] }),
  });

  const scopeOptions = form.scope_type === 'area'
    ? (areas ?? []).map(a => ({ value: a.id, label: a.name }))
    : form.scope_type === 'unit'
    ? (units ?? []).map(u => ({ value: u.id, label: u.name }))
    : form.scope_type === 'team'
    ? (teamsData ?? []).map(t => ({ value: t.id, label: t.name }))
    : [];

  if (isLoading) return <LoadingState rows={4} />;
  if (error) return <ErrorState error={new Error("Failed to load Entra group mappings")} />;

  return (
    <div>
      <div style={{ marginBottom: 24 }}>
        <h1 style={{ fontSize: 22, fontWeight: 700, color: 'var(--fg-1)', margin: 0 }}>
          Azure Entra ID Integration
        </h1>
        <p style={{ fontSize: 13, color: 'var(--fg-3)', margin: '4px 0 0' }}>
          Map Azure AD group Object IDs to gateway roles. Applied automatically on OIDC login when a user belongs to a mapped group.
        </p>
      </div>

      {/* How it works */}
      <div style={{
        marginBottom: 24, padding: '14px 16px',
        background: 'var(--accent-soft)', border: '1px solid color-mix(in srgb, var(--accent) 20%, transparent)', borderRadius: 8,
        fontSize: 13, color: 'var(--fg-1)',
      }}>
        <strong>How it works:</strong> When a user signs in via Entra ID, their JWT includes a{' '}
        <code style={{ fontFamily: 'monospace', fontSize: 12 }}>groups</code> claim containing
        Azure AD group Object IDs. Each mapped group automatically grants the corresponding gateway
        role — mirroring Azure RBAC inheritance: <strong>Subscription → Area (area_owner)</strong>,{' '}
        <strong>Resource Group → Unit (unit_lead)</strong>, <strong>Resource → Team (team_admin)</strong>.
      </div>

      <div style={{
        marginBottom: 16, padding: '8px 14px',
        background: 'var(--surface-2)', borderRadius: 6, border: '1px solid var(--rule)',
        fontSize: 12, color: 'var(--fg-3)', fontFamily: 'monospace',
      }}>
        Azure Entra group claim → role_assignments (scoped to org node) → session roles (on login)
      </div>

      {/* Add mapping */}
      <div style={{ marginBottom: 16 }}>
        {!showAdd ? (
          <button
            onClick={() => setShowAdd(true)}
            style={{
              padding: '8px 16px', fontSize: 13, fontWeight: 600,
              background: 'var(--accent)', color: '#fff',
              border: 'none', borderRadius: 6, cursor: 'pointer',
            }}
          >
            + Add mapping
          </button>
        ) : (
          <div style={{
            padding: 20, background: 'var(--surface-2)',
            border: '1px solid var(--rule)', borderRadius: 8, marginBottom: 16,
          }}>
            <h3 style={{ margin: '0 0 16px', fontSize: 14, fontWeight: 600, color: 'var(--fg-1)' }}>
              New group → role mapping
            </h3>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
              <label style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
                <span style={{ fontSize: 12, color: 'var(--fg-3)' }}>Entra Group Object ID *</span>
                <input
                  value={form.entra_group_id}
                  onChange={e => setForm(f => ({ ...f, entra_group_id: e.target.value }))}
                  placeholder="xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx"
                  style={{ padding: '7px 10px', fontSize: 13, background: 'var(--surface)', border: '1px solid var(--rule)', borderRadius: 6, color: 'var(--fg-1)' }}
                />
              </label>
              <label style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
                <span style={{ fontSize: 12, color: 'var(--fg-3)' }}>Display name (optional)</span>
                <input
                  value={form.entra_group_name}
                  onChange={e => setForm(f => ({ ...f, entra_group_name: e.target.value }))}
                  placeholder="e.g. sg-ai-gw-area-owners-investment"
                  style={{ padding: '7px 10px', fontSize: 13, background: 'var(--surface)', border: '1px solid var(--rule)', borderRadius: 6, color: 'var(--fg-1)' }}
                />
              </label>
              <label style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
                <span style={{ fontSize: 12, color: 'var(--fg-3)' }}>Gateway role *</span>
                <select
                  value={form.role}
                  onChange={e => setForm(f => ({ ...f, role: e.target.value }))}
                  style={{ padding: '7px 10px', fontSize: 13, background: 'var(--surface)', border: '1px solid var(--rule)', borderRadius: 6, color: 'var(--fg-1)' }}
                >
                  {ROLE_OPTIONS.map(r => <option key={r.value} value={r.value}>{r.label}</option>)}
                </select>
              </label>
              <label style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
                <span style={{ fontSize: 12, color: 'var(--fg-3)' }}>Scope type</span>
                <select
                  value={form.scope_type}
                  onChange={e => setForm(f => ({ ...f, scope_type: e.target.value, scope_id: '' }))}
                  style={{ padding: '7px 10px', fontSize: 13, background: 'var(--surface)', border: '1px solid var(--rule)', borderRadius: 6, color: 'var(--fg-1)' }}
                >
                  <option value="global">Global (all areas)</option>
                  <option value="area">Area</option>
                  <option value="unit">Unit</option>
                  <option value="team">Team</option>
                </select>
              </label>
              {scopeOptions.length > 0 && (
                <label style={{ display: 'flex', flexDirection: 'column', gap: 4, gridColumn: '1 / -1' }}>
                  <span style={{ fontSize: 12, color: 'var(--fg-3)' }}>
                    {SCOPE_TYPE_LABELS[form.scope_type]} *
                  </span>
                  <select
                    value={form.scope_id}
                    onChange={e => setForm(f => ({ ...f, scope_id: e.target.value }))}
                    style={{ padding: '7px 10px', fontSize: 13, background: 'var(--surface)', border: '1px solid var(--rule)', borderRadius: 6, color: 'var(--fg-1)' }}
                  >
                    <option value="">— select —</option>
                    {scopeOptions.map(o => <option key={o.value} value={o.value}>{o.label}</option>)}
                  </select>
                </label>
              )}
            </div>
            <div style={{ display: 'flex', gap: 10, marginTop: 16 }}>
              <button
                onClick={() => addMutation.mutate(form)}
                disabled={!form.entra_group_id || addMutation.isPending}
                style={{
                  padding: '8px 20px', fontSize: 13, fontWeight: 600,
                  background: 'var(--accent)', color: '#fff',
                  border: 'none', borderRadius: 6, cursor: 'pointer',
                  opacity: addMutation.isPending ? 0.6 : 1,
                }}
              >
                {addMutation.isPending ? 'Saving…' : 'Save mapping'}
              </button>
              <button
                onClick={() => setShowAdd(false)}
                style={{ padding: '8px 16px', fontSize: 13, background: 'transparent', border: '1px solid var(--rule)', borderRadius: 6, color: 'var(--fg-1)', cursor: 'pointer' }}
              >
                Cancel
              </button>
            </div>
            {addMutation.isError && (
              <p style={{ color: 'var(--bad)', fontSize: 12, marginTop: 8 }}>
                Failed to save. Check Group ID and try again.
              </p>
            )}
          </div>
        )}
      </div>

      {/* Mappings table */}
      <div style={{ background: 'var(--surface)', border: '1px solid var(--rule)', borderRadius: 8, overflow: 'hidden' }}>
        <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
          <thead>
            <tr style={{ background: 'var(--surface-2)', borderBottom: '2px solid var(--rule)' }}>
              <th className="microlabel" style={{ padding: '10px 14px', textAlign: 'left' }}>Group</th>
              <th className="microlabel" style={{ padding: '10px 14px', textAlign: 'left' }}>Role</th>
              <th className="microlabel" style={{ padding: '10px 14px', textAlign: 'left' }}>Scope</th>
              <th className="microlabel" style={{ padding: '10px 14px', textAlign: 'left' }}>Created by</th>
              <th style={{ padding: '10px 14px' }} />
            </tr>
          </thead>
          <tbody>
            {(mappings ?? []).length === 0 && (
              <tr>
                <td colSpan={5} style={{ padding: 32, textAlign: 'center', color: 'var(--fg-3)' }}>
                  No group mappings yet. Add one above.
                </td>
              </tr>
            )}
            {(mappings ?? []).map(m => (
              <tr key={m.id} style={{ borderBottom: '1px solid var(--rule)' }}>
                <td style={{ padding: '10px 14px' }}>
                  <div style={{ fontWeight: 500, color: 'var(--fg-1)' }}>
                    {m.entra_group_name ?? '—'}
                  </div>
                  <div style={{ fontSize: 11, color: 'var(--fg-3)', fontFamily: 'monospace' }}>
                    {m.entra_group_id}
                  </div>
                </td>
                <td style={{ padding: '10px 14px' }}>
                  <RolePill role={m.role} />
                </td>
                <td style={{ padding: '10px 14px', color: 'var(--fg-3)', fontSize: 12 }}>
                  {m.scope_name ? (
                    <span>
                      <span style={{ textTransform: 'capitalize' }}>{m.scope_type}</span>: {m.scope_name}
                    </span>
                  ) : (
                    <span>Global</span>
                  )}
                </td>
                <td style={{ padding: '10px 14px', color: 'var(--fg-3)', fontSize: 12 }}>
                  {m.created_by_email ?? '—'}
                </td>
                <td style={{ padding: '10px 14px', textAlign: 'right' }}>
                  <button
                    onClick={() => deleteMutation.mutate(m.id)}
                    disabled={deleteMutation.isPending}
                    style={{
                      padding: '4px 10px', fontSize: 12,
                      background: 'transparent', border: '1px solid var(--rule)',
                      borderRadius: 4, color: 'var(--bad)', cursor: 'pointer',
                    }}
                  >
                    Remove
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
