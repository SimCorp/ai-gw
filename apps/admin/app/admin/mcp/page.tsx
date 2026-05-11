'use client';

import React, { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';

const BASE = process.env.NEXT_PUBLIC_ADMIN_API ?? 'http://localhost:8005';

interface McpServer {
  id: string;
  name: string;
  description: string | null;
  url: string;
  auth_type: 'none' | 'bearer' | 'api_key';
  auth_header: string | null;
  status: 'pending' | 'active' | 'error' | 'disabled';
  enabled: boolean;
  tool_count: number;
  last_ping_at: string | null;
  last_ping_ms: number | null;
  last_error: string | null;
  created_at: string;
}

interface McpTool {
  id: string;
  name: string;
  description: string | null;
  input_schema: Record<string, unknown>;
  enabled: boolean;
}

interface McpAccess {
  server_id: string;
  team_id: string;
  team_name: string;
  granted_at: string;
}

interface McpSummary {
  server_count: number;
  active_count: number;
  error_count: number;
  pending_count: number;
  disabled_count: number;
  total_tools: number;
  enabled_tools: number;
  teams_with_access: number;
}

interface McpDetail {
  server: McpServer;
  tools: McpTool[];
  access: McpAccess[];
}

interface Team {
  id: string;
  name: string;
}

type AuthType = 'none' | 'bearer' | 'api_key';

interface ServerForm {
  name: string;
  description: string;
  url: string;
  auth_type: AuthType;
  auth_header: string;
  auth_secret: string;
  enabled: boolean;
}

const FORM_DEFAULTS: ServerForm = {
  name: '',
  description: '',
  url: '',
  auth_type: 'none',
  auth_header: 'X-API-Key',
  auth_secret: '',
  enabled: true,
};

function statusPill(status: string) {
  const cls: Record<string, string> = {
    active: 'pill--good',
    error: 'pill--bad',
    pending: 'pill--warn',
    disabled: 'pill--info',
  };
  return (
    <span className={`pill ${cls[status] ?? 'pill--info'}`}>
      <span className="dot" />{status}
    </span>
  );
}

function relativeTime(iso: string): string {
  const diff = Date.now() - new Date(iso).getTime();
  const mins = Math.floor(diff / 60_000);
  if (mins < 1) return 'just now';
  if (mins < 60) return `${mins}m ago`;
  const hrs = Math.floor(mins / 60);
  if (hrs < 24) return `${hrs}h ago`;
  return `${Math.floor(hrs / 24)}d ago`;
}

function ServerModal({
  editServer,
  onClose,
  onSaved,
}: {
  editServer: McpServer | null;
  onClose: () => void;
  onSaved: () => void;
}) {
  const [form, setForm] = useState<ServerForm>(
    editServer
      ? {
          name: editServer.name,
          description: editServer.description ?? '',
          url: editServer.url,
          auth_type: editServer.auth_type,
          auth_header: editServer.auth_header ?? 'X-API-Key',
          auth_secret: '',
          enabled: editServer.enabled,
        }
      : FORM_DEFAULTS
  );
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setSaving(true);
    setError(null);
    try {
      const body: Record<string, unknown> = {
        name: form.name,
        description: form.description || null,
        url: form.url,
        auth_type: form.auth_type,
        enabled: form.enabled,
      };
      if (form.auth_type === 'api_key') {
        body.auth_header = form.auth_header;
      }
      if (form.auth_type !== 'none' && form.auth_secret) {
        body.auth_secret = form.auth_secret;
      }

      const res = await fetch(
        editServer ? `${BASE}/mcp/servers/${editServer.id}` : `${BASE}/mcp/servers`,
        {
          method: editServer ? 'PUT' : 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(body),
        }
      );
      if (!res.ok) {
        const text = await res.text();
        throw new Error(`${res.status}: ${text}`);
      }
      onSaved();
    } catch (err) {
      setError(String(err));
    } finally {
      setSaving(false);
    }
  }

  return (
    <div
      style={{
        position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.6)',
        display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 100,
      }}
      onClick={onClose}
    >
      <div className="card" style={{ width: 500, maxWidth: '90vw' }} onClick={e => e.stopPropagation()}>
        <div className="card__head" style={{ display: 'flex', justifyContent: 'space-between' }}>
          <div className="card__title">{editServer ? 'Edit server' : 'Register MCP server'}</div>
          <button className="icon-btn" onClick={onClose}>✕</button>
        </div>
        <div className="card__body">
          <form onSubmit={handleSubmit} style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
            <div>
              <label style={{ fontSize: 12, color: 'var(--fg-2)', display: 'block', marginBottom: 4 }}>Name *</label>
              <input
                className="input" style={{ width: '100%' }}
                value={form.name}
                onChange={e => setForm(f => ({ ...f, name: e.target.value }))}
                required placeholder="GitHub MCP"
              />
            </div>
            <div>
              <label style={{ fontSize: 12, color: 'var(--fg-2)', display: 'block', marginBottom: 4 }}>Description</label>
              <input
                className="input" style={{ width: '100%' }}
                value={form.description}
                onChange={e => setForm(f => ({ ...f, description: e.target.value }))}
                placeholder="Optional description"
              />
            </div>
            <div>
              <label style={{ fontSize: 12, color: 'var(--fg-2)', display: 'block', marginBottom: 4 }}>URL *</label>
              <input
                className="input" style={{ width: '100%' }}
                value={form.url}
                onChange={e => setForm(f => ({ ...f, url: e.target.value }))}
                required placeholder="https://mcp.example.com"
              />
            </div>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10 }}>
              <div>
                <label style={{ fontSize: 12, color: 'var(--fg-2)', display: 'block', marginBottom: 4 }}>Auth type</label>
                <select
                  className="input" style={{ width: '100%' }}
                  value={form.auth_type}
                  onChange={e => setForm(f => ({ ...f, auth_type: e.target.value as AuthType }))}
                >
                  <option value="none">none</option>
                  <option value="bearer">bearer</option>
                  <option value="api_key">api_key</option>
                </select>
              </div>
              {form.auth_type === 'api_key' && (
                <div>
                  <label style={{ fontSize: 12, color: 'var(--fg-2)', display: 'block', marginBottom: 4 }}>Auth header</label>
                  <input
                    className="input" style={{ width: '100%' }}
                    value={form.auth_header}
                    onChange={e => setForm(f => ({ ...f, auth_header: e.target.value }))}
                    placeholder="X-API-Key"
                  />
                </div>
              )}
            </div>
            {form.auth_type !== 'none' && (
              <div>
                <label style={{ fontSize: 12, color: 'var(--fg-2)', display: 'block', marginBottom: 4 }}>
                  Auth secret {editServer ? '(leave blank to keep existing)' : '*'}
                </label>
                <input
                  className="input" style={{ width: '100%' }}
                  type="password"
                  value={form.auth_secret}
                  onChange={e => setForm(f => ({ ...f, auth_secret: e.target.value }))}
                  placeholder={editServer ? '••••••••' : 'Secret token / API key'}
                  required={!editServer}
                />
              </div>
            )}
            <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
              <label style={{ fontSize: 12, color: 'var(--fg-2)' }}>Enabled</label>
              <input
                type="checkbox"
                checked={form.enabled}
                onChange={e => setForm(f => ({ ...f, enabled: e.target.checked }))}
              />
            </div>
            {error && (
              <div className="pill pill--bad" style={{ fontSize: 12 }}>{error}</div>
            )}
            <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end', marginTop: 4 }}>
              <button type="button" className="btn" onClick={onClose}>Cancel</button>
              <button type="submit" className="btn btn--primary" disabled={saving}>
                {saving ? 'Saving…' : editServer ? 'Save changes' : 'Register'}
              </button>
            </div>
          </form>
        </div>
      </div>
    </div>
  );
}

function ExpandedRow({
  serverId,
  onClose,
}: {
  serverId: string;
  onClose: () => void;
}) {
  const queryClient = useQueryClient();
  const [grantTeamId, setGrantTeamId] = useState('');
  const [granting, setGranting] = useState(false);
  const [grantError, setGrantError] = useState<string | null>(null);

  const detailQuery = useQuery<McpDetail>({
    queryKey: ['mcp-server', serverId],
    queryFn: () => fetch(`${BASE}/mcp/servers/${serverId}`).then(r => {
      if (!r.ok) throw new Error(`Failed: ${r.status}`);
      return r.json();
    }),
  });

  const teamsQuery = useQuery<Team[]>({
    queryKey: ['teams'],
    queryFn: () => fetch(`${BASE}/teams`).then(r => {
      if (!r.ok) throw new Error(`Failed: ${r.status}`);
      return r.json();
    }),
  });

  async function toggleTool(toolName: string, enabled: boolean) {
    await fetch(`${BASE}/mcp/servers/${serverId}/tools/${toolName}`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ enabled }),
    });
    queryClient.invalidateQueries({ queryKey: ['mcp-server', serverId] });
    queryClient.invalidateQueries({ queryKey: ['mcp-servers'] });
  }

  async function handleGrant() {
    if (!grantTeamId) return;
    setGranting(true);
    setGrantError(null);
    try {
      const res = await fetch(`${BASE}/mcp/servers/${serverId}/access`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ team_id: grantTeamId }),
      });
      if (!res.ok) throw new Error(`${res.status}`);
      queryClient.invalidateQueries({ queryKey: ['mcp-server', serverId] });
      setGrantTeamId('');
    } catch (err) {
      setGrantError(String(err));
    } finally {
      setGranting(false);
    }
  }

  async function handleRevoke(teamId: string) {
    await fetch(`${BASE}/mcp/servers/${serverId}/access/${teamId}`, { method: 'DELETE' });
    queryClient.invalidateQueries({ queryKey: ['mcp-server', serverId] });
  }

  const detail = detailQuery.data;
  const grantedTeamIds = new Set((detail?.access ?? []).map(a => a.team_id));
  const availableTeams = (teamsQuery.data ?? []).filter(t => !grantedTeamIds.has(t.id));

  return (
    <tr>
      <td colSpan={7} style={{ padding: 0, background: 'var(--surface-soft)' }}>
        <div style={{ padding: '16px 20px', display: 'flex', flexDirection: 'column', gap: 16 }}>
          {detailQuery.isLoading && (
            <div style={{ color: 'var(--fg-3)', fontSize: 13 }}>Loading…</div>
          )}
          {detailQuery.isError && (
            <div className="pill pill--bad" style={{ fontSize: 12 }}>
              Failed to load detail: {(detailQuery.error as Error).message}
            </div>
          )}
          {detail && (
            <>
              <div>
                <div style={{ fontWeight: 600, fontSize: 12, color: 'var(--fg-2)', marginBottom: 8, textTransform: 'uppercase', letterSpacing: '0.04em' }}>
                  Tools ({detail.tools.length})
                </div>
                {detail.tools.length === 0 ? (
                  <div style={{ fontSize: 13, color: 'var(--fg-3)' }}>No tools discovered. Try pinging the server.</div>
                ) : (
                  <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
                    {detail.tools.map(tool => (
                      <div
                        key={tool.id}
                        style={{
                          display: 'flex', alignItems: 'center', gap: 12,
                          padding: '8px 12px',
                          background: 'var(--surface)',
                          border: '1px solid var(--rule)',
                          borderRadius: 6,
                        }}
                      >
                        <div style={{ flex: 1, minWidth: 0 }}>
                          <span className="mono" style={{ fontWeight: 500, fontSize: 13 }}>{tool.name}</span>
                          {tool.description && (
                            <span style={{ color: 'var(--fg-2)', fontSize: 12, marginLeft: 10 }}>{tool.description}</span>
                          )}
                        </div>
                        <button
                          className={`pill ${tool.enabled ? 'pill--good' : ''}`}
                          style={{ cursor: 'pointer', border: 'none', background: 'none', padding: 0 }}
                          onClick={() => toggleTool(tool.name, !tool.enabled)}
                          title={tool.enabled ? 'Click to disable' : 'Click to enable'}
                        >
                          <span className="dot" />{tool.enabled ? 'enabled' : 'disabled'}
                        </button>
                      </div>
                    ))}
                  </div>
                )}
              </div>

              <div>
                <div style={{ fontWeight: 600, fontSize: 12, color: 'var(--fg-2)', marginBottom: 8, textTransform: 'uppercase', letterSpacing: '0.04em' }}>
                  Team access ({detail.access.length})
                </div>
                <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
                  {detail.access.map(acc => (
                    <div
                      key={acc.team_id}
                      style={{
                        display: 'flex', alignItems: 'center', gap: 12,
                        padding: '8px 12px',
                        background: 'var(--surface)',
                        border: '1px solid var(--rule)',
                        borderRadius: 6,
                      }}
                    >
                      <div style={{ flex: 1, fontWeight: 500, fontSize: 13 }}>{acc.team_name}</div>
                      <div style={{ fontSize: 12, color: 'var(--fg-3)' }}>granted {relativeTime(acc.granted_at)}</div>
                      <button
                        className="btn btn--sm btn--ghost"
                        style={{ color: 'var(--bad)' }}
                        onClick={() => handleRevoke(acc.team_id)}
                      >
                        Revoke
                      </button>
                    </div>
                  ))}
                  <div
                    style={{
                      display: 'flex', alignItems: 'center', gap: 8,
                      padding: '8px 12px',
                      border: '1px dashed var(--rule)',
                      borderRadius: 6,
                    }}
                  >
                    <select
                      className="input"
                      style={{ flex: 1 }}
                      value={grantTeamId}
                      onChange={e => setGrantTeamId(e.target.value)}
                    >
                      <option value="">+ Grant access to team…</option>
                      {availableTeams.map(t => (
                        <option key={t.id} value={t.id}>{t.name}</option>
                      ))}
                    </select>
                    <button
                      className="btn btn--sm btn--primary"
                      onClick={handleGrant}
                      disabled={!grantTeamId || granting}
                    >
                      {granting ? '…' : 'Grant'}
                    </button>
                  </div>
                  {grantError && (
                    <div className="pill pill--bad" style={{ fontSize: 12 }}>{grantError}</div>
                  )}
                </div>
              </div>
            </>
          )}
          <div style={{ textAlign: 'right' }}>
            <button className="btn btn--sm btn--ghost" onClick={onClose}>Collapse ▲</button>
          </div>
        </div>
      </td>
    </tr>
  );
}

export default function McpPage() {
  const queryClient = useQueryClient();
  const [expandedId, setExpandedId] = useState<string | null>(null);
  const [showModal, setShowModal] = useState(false);
  const [editServer, setEditServer] = useState<McpServer | null>(null);
  const [pingingIds, setPingingIds] = useState<Set<string>>(new Set());
  const [pingErrors, setPingErrors] = useState<Record<string, string>>({});

  const summaryQuery = useQuery<McpSummary>({
    queryKey: ['mcp-summary'],
    queryFn: () => fetch(`${BASE}/mcp/summary`).then(r => {
      if (!r.ok) throw new Error(`Failed: ${r.status}`);
      return r.json();
    }),
  });

  const serversQuery = useQuery<McpServer[]>({
    queryKey: ['mcp-servers'],
    queryFn: () => fetch(`${BASE}/mcp/servers`).then(r => {
      if (!r.ok) throw new Error(`Failed: ${r.status}`);
      return r.json();
    }),
  });

  const deleteMutation = useMutation({
    mutationFn: (id: string) => fetch(`${BASE}/mcp/servers/${id}`, { method: 'DELETE' }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['mcp-servers'] });
      queryClient.invalidateQueries({ queryKey: ['mcp-summary'] });
    },
  });

  async function handleDelete(server: McpServer) {
    if (!confirm(`Delete server "${server.name}"?`)) return;
    deleteMutation.mutate(server.id);
  }

  async function handlePing(server: McpServer) {
    setPingingIds(s => new Set(s).add(server.id));
    setPingErrors(e => { const n = { ...e }; delete n[server.id]; return n; });
    try {
      const res = await fetch(`${BASE}/mcp/servers/${server.id}/ping`, { method: 'POST' });
      if (!res.ok) {
        const text = await res.text();
        throw new Error(`${res.status}: ${text}`);
      }
      queryClient.invalidateQueries({ queryKey: ['mcp-servers'] });
      queryClient.invalidateQueries({ queryKey: ['mcp-summary'] });
    } catch (err) {
      setPingErrors(e => ({ ...e, [server.id]: String(err) }));
    } finally {
      setPingingIds(s => { const n = new Set(s); n.delete(server.id); return n; });
    }
  }

  function openEdit(server: McpServer) {
    setEditServer(server);
    setShowModal(true);
  }

  function openNew() {
    setEditServer(null);
    setShowModal(true);
  }

  function handleModalSaved() {
    queryClient.invalidateQueries({ queryKey: ['mcp-servers'] });
    queryClient.invalidateQueries({ queryKey: ['mcp-summary'] });
    setShowModal(false);
    setEditServer(null);
  }

  const summary = summaryQuery.data;
  const servers = serversQuery.data ?? [];

  return (
    <section className="page">
      <div className="page__head">
        <div>
          <h1 className="page__title">MCP Servers</h1>
          <p className="page__sub">
            {summary
              ? `${summary.server_count} servers · ${summary.active_count} active · ${summary.total_tools} tools · ${summary.teams_with_access} teams`
              : 'Model Context Protocol server registry'}
          </p>
        </div>
        <div className="page__actions">
          <button className="btn btn--primary" onClick={openNew}>+ Register Server</button>
        </div>
      </div>

      <div className="kpi-grid" style={{ marginBottom: 18 }}>
        <div className="kpi">
          <div className="kpi__label">Servers</div>
          <div className="kpi__value">{summary?.server_count ?? '—'}</div>
          <div className="kpi__delta flat">{summary ? `${summary.disabled_count ?? 0} disabled` : ''}</div>
        </div>
        <div className="kpi">
          <div className="kpi__label">Active</div>
          <div className="kpi__value">{summary?.active_count ?? '—'}</div>
          <div className="kpi__delta flat">{summary ? `${summary.error_count} error · ${summary.pending_count} pending` : ''}</div>
        </div>
        <div className="kpi">
          <div className="kpi__label">Tools</div>
          <div className="kpi__value">{summary?.total_tools ?? '—'}</div>
          <div className="kpi__delta flat">{summary ? `${summary.enabled_tools} enabled` : ''}</div>
        </div>
        <div className="kpi">
          <div className="kpi__label">Teams with access</div>
          <div className="kpi__value">{summary?.teams_with_access ?? '—'}</div>
          <div className="kpi__delta flat">across all servers</div>
        </div>
      </div>

      {serversQuery.isError && (
        <div className="pill pill--bad" style={{ marginBottom: 12 }}>
          Failed to load servers: {(serversQuery.error as Error).message}
        </div>
      )}

      <div className="card">
        <div className="card__body" style={{ padding: 0 }}>
          {serversQuery.isLoading ? (
            <div style={{ padding: '32px 20px', color: 'var(--fg-3)', textAlign: 'center', fontSize: 13 }}>
              Loading servers…
            </div>
          ) : servers.length === 0 ? (
            <div style={{ padding: '40px 20px', color: 'var(--fg-2)', textAlign: 'center', fontSize: 13 }}>
              No MCP servers registered. Click &ldquo;+ Register Server&rdquo; to add one.
            </div>
          ) : (
            <table className="tbl">
              <thead>
                <tr>
                  <th>Name</th>
                  <th>URL</th>
                  <th>Auth</th>
                  <th>Status</th>
                  <th className="num">Tools</th>
                  <th>Last ping</th>
                  <th></th>
                </tr>
              </thead>
              <tbody>
                {servers.map(server => (
                  <React.Fragment key={server.id}>
                    <tr style={{ opacity: server.enabled ? 1 : 0.55 }}>
                      <td>
                        <div className="cell-2">
                          <span style={{ fontWeight: 500 }}>{server.name}</span>
                          {server.description && (
                            <span className="lo">{server.description}</span>
                          )}
                        </div>
                      </td>
                      <td>
                        <span className="mono lo" style={{ fontSize: 11.5, wordBreak: 'break-all' }}>
                          {server.url}
                        </span>
                      </td>
                      <td>
                        <span className="pill">{server.auth_type}</span>
                      </td>
                      <td>
                        <div style={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
                          {statusPill(server.status)}
                          {pingErrors[server.id] && (
                            <span style={{ fontSize: 11, color: 'var(--bad)' }}>
                              {pingErrors[server.id]}
                            </span>
                          )}
                          {server.last_error && !pingErrors[server.id] && (
                            <span style={{ fontSize: 11, color: 'var(--bad)' }} title={server.last_error}>
                              {server.last_error.slice(0, 40)}{server.last_error.length > 40 ? '…' : ''}
                            </span>
                          )}
                        </div>
                      </td>
                      <td className="num mono">
                        {server.tool_count > 0
                          ? server.tool_count
                          : <span className="muted">0</span>}
                      </td>
                      <td style={{ fontSize: 12, color: 'var(--fg-3)' }}>
                        {server.last_ping_at ? (
                          <span title={server.last_ping_at}>
                            {relativeTime(server.last_ping_at)}
                            {server.last_ping_ms != null && (
                              <span className="muted"> · {server.last_ping_ms}ms</span>
                            )}
                          </span>
                        ) : (
                          <span className="muted">never</span>
                        )}
                      </td>
                      <td>
                        <div style={{ display: 'flex', gap: 4, alignItems: 'center', justifyContent: 'flex-end' }}>
                          <button
                            className="btn btn--sm"
                            onClick={() => handlePing(server)}
                            disabled={pingingIds.has(server.id)}
                            title="Ping server"
                          >
                            {pingingIds.has(server.id) ? '…' : 'Ping'}
                          </button>
                          <button
                            className="btn btn--sm"
                            onClick={() => openEdit(server)}
                            title="Edit server"
                          >
                            Edit
                          </button>
                          <button
                            className="btn btn--sm"
                            onClick={() => setExpandedId(id => id === server.id ? null : server.id)}
                            title={expandedId === server.id ? 'Collapse' : 'Expand'}
                          >
                            {expandedId === server.id ? '▼' : '▶'}
                          </button>
                          <button
                            className="btn btn--sm btn--ghost"
                            style={{ color: 'var(--bad)' }}
                            onClick={() => handleDelete(server)}
                            title="Delete server"
                          >
                            ✕
                          </button>
                        </div>
                      </td>
                    </tr>
                    {expandedId === server.id && (
                      <ExpandedRow
                        serverId={server.id}
                        onClose={() => setExpandedId(null)}
                      />
                    )}
                  </React.Fragment>
                ))}
              </tbody>
            </table>
          )}
        </div>
      </div>

      {showModal && (
        <ServerModal
          editServer={editServer}
          onClose={() => { setShowModal(false); setEditServer(null); }}
          onSaved={handleModalSaved}
        />
      )}
    </section>
  );
}
