'use client';

import React, { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';

const BASE = process.env.NEXT_PUBLIC_ADMIN_API ?? 'http://localhost:8005';

interface Plugin {
  id: string;
  name: string;
  slug: string;
  description: string | null;
  version: string;
  author: string;
  category: 'tool' | 'integration' | 'data' | 'security' | 'workflow';
  scopes: string[];
  homepage_url: string | null;
  icon_url: string | null;
  enabled: boolean;
  override_count: number;
  created_at: string;
  updated_at: string;
}

interface PluginTeamOverride {
  plugin_id: string;
  team_id: string;
  team_name: string;
  enabled: boolean;
  created_at: string;
}

interface PluginDetail {
  plugin: Plugin;
  overrides: PluginTeamOverride[];
}

interface PluginSummary {
  total: number;
  enabled: number;
  disabled: number;
  categories: Record<string, number>;
  total_overrides: number;
}

interface Team {
  id: string;
  name: string;
}

type Category = Plugin['category'];

interface PluginForm {
  name: string;
  slug: string;
  description: string;
  version: string;
  author: string;
  category: Category;
  scopes: string;
  homepage_url: string;
  icon_url: string;
  enabled: boolean;
}

const FORM_DEFAULTS: PluginForm = {
  name: '',
  slug: '',
  description: '',
  version: '1.0.0',
  author: '',
  category: 'tool',
  scopes: '',
  homepage_url: '',
  icon_url: '',
  enabled: true,
};

function categoryBadge(cat: Category) {
  const styles: Record<Category, { bg: string; color: string }> = {
    tool: { bg: '#dbeafe', color: '#1d4ed8' },
    integration: { bg: '#ede9fe', color: '#6d28d9' },
    data: { bg: '#ffedd5', color: '#c2410c' },
    security: { bg: '#fee2e2', color: '#b91c1c' },
    workflow: { bg: '#dcfce7', color: '#15803d' },
  };
  const s = styles[cat] ?? styles.tool;
  return (
    <span
      style={{
        display: 'inline-block',
        padding: '2px 8px',
        borderRadius: 10,
        fontSize: 11,
        fontWeight: 600,
        background: s.bg,
        color: s.color,
        textTransform: 'capitalize',
        letterSpacing: '0.02em',
      }}
    >
      {cat}
    </span>
  );
}

function PluginModal({
  editPlugin,
  onClose,
  onSaved,
}: {
  editPlugin: Plugin | null;
  onClose: () => void;
  onSaved: () => void;
}) {
  const [form, setForm] = useState<PluginForm>(
    editPlugin
      ? {
          name: editPlugin.name,
          slug: editPlugin.slug,
          description: editPlugin.description ?? '',
          version: editPlugin.version,
          author: editPlugin.author,
          category: editPlugin.category,
          scopes: editPlugin.scopes.join(', '),
          homepage_url: editPlugin.homepage_url ?? '',
          icon_url: editPlugin.icon_url ?? '',
          enabled: editPlugin.enabled,
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
        slug: form.slug,
        description: form.description || null,
        version: form.version,
        author: form.author,
        category: form.category,
        scopes: form.scopes
          .split(',')
          .map(s => s.trim())
          .filter(Boolean),
        homepage_url: form.homepage_url || null,
        icon_url: form.icon_url || null,
        enabled: form.enabled,
      };
      const res = await fetch(
        editPlugin ? `${BASE}/plugins/${editPlugin.id}` : `${BASE}/plugins`,
        {
          method: editPlugin ? 'PUT' : 'POST',
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
      <div className="card" style={{ width: 520, maxWidth: '90vw' }} onClick={e => e.stopPropagation()}>
        <div className="card__head" style={{ display: 'flex', justifyContent: 'space-between' }}>
          <div className="card__title">{editPlugin ? 'Edit plugin' : 'Register plugin'}</div>
          <button className="icon-btn" onClick={onClose}>✕</button>
        </div>
        <div className="card__body">
          <form onSubmit={handleSubmit} style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10 }}>
              <div>
                <label style={{ fontSize: 12, color: 'var(--fg-2)', display: 'block', marginBottom: 4 }}>Name *</label>
                <input
                  className="input" style={{ width: '100%' }}
                  value={form.name}
                  onChange={e => setForm(f => ({ ...f, name: e.target.value }))}
                  required placeholder="My Plugin"
                />
              </div>
              <div>
                {editPlugin ? (
                  <>
                    <label style={{ fontSize: 12, color: 'var(--fg-2)', display: 'block', marginBottom: 4 }}>
                      Slug <span style={{ color: 'var(--fg-3)', fontStyle: 'italic' }}>(read-only)</span>
                    </label>
                    <input
                      className="input" style={{ width: '100%', opacity: 0.6 }}
                      value={form.slug}
                      readOnly
                    />
                  </>
                ) : (
                  <>
                    <label style={{ fontSize: 12, color: 'var(--fg-2)', display: 'block', marginBottom: 4 }}>Slug *</label>
                    <input
                      className="input" style={{ width: '100%' }}
                      value={form.slug}
                      onChange={e => setForm(f => ({ ...f, slug: e.target.value }))}
                      required placeholder="my-plugin"
                    />
                  </>
                )}
              </div>
            </div>
            <div>
              <label style={{ fontSize: 12, color: 'var(--fg-2)', display: 'block', marginBottom: 4 }}>Description</label>
              <textarea
                className="input" style={{ width: '100%', minHeight: 64, resize: 'vertical' }}
                value={form.description}
                onChange={e => setForm(f => ({ ...f, description: e.target.value }))}
                placeholder="Optional description"
              />
            </div>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: 10 }}>
              <div>
                <label style={{ fontSize: 12, color: 'var(--fg-2)', display: 'block', marginBottom: 4 }}>Version</label>
                <input
                  className="input" style={{ width: '100%' }}
                  value={form.version}
                  onChange={e => setForm(f => ({ ...f, version: e.target.value }))}
                  placeholder="1.0.0"
                />
              </div>
              <div>
                <label style={{ fontSize: 12, color: 'var(--fg-2)', display: 'block', marginBottom: 4 }}>Author</label>
                <input
                  className="input" style={{ width: '100%' }}
                  value={form.author}
                  onChange={e => setForm(f => ({ ...f, author: e.target.value }))}
                  placeholder="Acme Corp"
                />
              </div>
              <div>
                <label style={{ fontSize: 12, color: 'var(--fg-2)', display: 'block', marginBottom: 4 }}>Category</label>
                <select
                  className="input" style={{ width: '100%' }}
                  value={form.category}
                  onChange={e => setForm(f => ({ ...f, category: e.target.value as Category }))}
                >
                  <option value="tool">tool</option>
                  <option value="integration">integration</option>
                  <option value="data">data</option>
                  <option value="security">security</option>
                  <option value="workflow">workflow</option>
                </select>
              </div>
            </div>
            <div>
              <label style={{ fontSize: 12, color: 'var(--fg-2)', display: 'block', marginBottom: 4 }}>
                Scopes <span style={{ color: 'var(--fg-3)' }}>(comma-separated)</span>
              </label>
              <input
                className="input" style={{ width: '100%' }}
                value={form.scopes}
                onChange={e => setForm(f => ({ ...f, scopes: e.target.value }))}
                placeholder="read:data, write:data"
              />
            </div>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10 }}>
              <div>
                <label style={{ fontSize: 12, color: 'var(--fg-2)', display: 'block', marginBottom: 4 }}>Homepage URL</label>
                <input
                  className="input" style={{ width: '100%' }}
                  value={form.homepage_url}
                  onChange={e => setForm(f => ({ ...f, homepage_url: e.target.value }))}
                  placeholder="https://example.com"
                />
              </div>
              <div>
                <label style={{ fontSize: 12, color: 'var(--fg-2)', display: 'block', marginBottom: 4 }}>Icon URL</label>
                <input
                  className="input" style={{ width: '100%' }}
                  value={form.icon_url}
                  onChange={e => setForm(f => ({ ...f, icon_url: e.target.value }))}
                  placeholder="https://example.com/icon.png"
                />
              </div>
            </div>
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
                {saving ? 'Saving…' : editPlugin ? 'Save changes' : 'Register'}
              </button>
            </div>
          </form>
        </div>
      </div>
    </div>
  );
}

function ExpandedRow({
  pluginId,
  onClose,
}: {
  pluginId: string;
  onClose: () => void;
}) {
  const queryClient = useQueryClient();
  const [addTeamId, setAddTeamId] = useState('');
  const [addEnabled, setAddEnabled] = useState(true);
  const [adding, setAdding] = useState(false);
  const [addError, setAddError] = useState<string | null>(null);

  const detailQuery = useQuery<PluginDetail>({
    queryKey: ['plugin', pluginId],
    queryFn: () => fetch(`${BASE}/plugins/${pluginId}`).then(r => {
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

  async function handleAddOverride() {
    if (!addTeamId) return;
    setAdding(true);
    setAddError(null);
    try {
      const res = await fetch(`${BASE}/plugins/${pluginId}/teams`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ team_id: addTeamId, enabled: addEnabled }),
      });
      if (!res.ok) throw new Error(`${res.status}`);
      queryClient.invalidateQueries({ queryKey: ['plugin', pluginId] });
      queryClient.invalidateQueries({ queryKey: ['plugins'] });
      setAddTeamId('');
      setAddEnabled(true);
    } catch (err) {
      setAddError(String(err));
    } finally {
      setAdding(false);
    }
  }

  async function handleRemoveOverride(teamId: string) {
    await fetch(`${BASE}/plugins/${pluginId}/teams/${teamId}`, { method: 'DELETE' });
    queryClient.invalidateQueries({ queryKey: ['plugin', pluginId] });
    queryClient.invalidateQueries({ queryKey: ['plugins'] });
  }

  const detail = detailQuery.data;
  const overrideTeamIds = new Set((detail?.overrides ?? []).map(o => o.team_id));
  const availableTeams = (teamsQuery.data ?? []).filter(t => !overrideTeamIds.has(t.id));

  return (
    <tr>
      <td colSpan={8} style={{ padding: 0, background: 'var(--surface-soft)' }}>
        <div style={{ padding: '16px 20px' }}>
          {detailQuery.isLoading && (
            <div style={{ color: 'var(--fg-3)', fontSize: 13 }}>Loading…</div>
          )}
          {detailQuery.isError && (
            <div className="pill pill--bad" style={{ fontSize: 12 }}>
              Failed to load detail: {(detailQuery.error as Error).message}
            </div>
          )}
          {detail && (
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 20 }}>
              <div>
                <div style={{ fontWeight: 600, fontSize: 12, color: 'var(--fg-2)', marginBottom: 8, textTransform: 'uppercase', letterSpacing: '0.04em' }}>
                  Team overrides ({detail.overrides.length})
                </div>
                <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
                  {detail.overrides.length === 0 && (
                    <div style={{ fontSize: 13, color: 'var(--fg-3)' }}>No team overrides yet.</div>
                  )}
                  {detail.overrides.map(ov => (
                    <div
                      key={ov.team_id}
                      style={{
                        display: 'flex', alignItems: 'center', gap: 10,
                        padding: '8px 12px',
                        background: 'var(--surface)',
                        border: '1px solid var(--rule)',
                        borderRadius: 6,
                      }}
                    >
                      <div style={{ flex: 1, fontWeight: 500, fontSize: 13 }}>{ov.team_name}</div>
                      <span className={`pill ${ov.enabled ? 'pill--good' : 'pill--bad'}`}>
                        <span className="dot" />{ov.enabled ? 'enabled' : 'disabled'}
                      </span>
                      <button
                        className="btn btn--sm btn--ghost"
                        style={{ color: 'var(--bad)' }}
                        onClick={() => handleRemoveOverride(ov.team_id)}
                      >
                        Remove
                      </button>
                    </div>
                  ))}
                </div>
              </div>

              <div>
                <div style={{ fontWeight: 600, fontSize: 12, color: 'var(--fg-2)', marginBottom: 8, textTransform: 'uppercase', letterSpacing: '0.04em' }}>
                  Add team override
                </div>
                <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                  <select
                    className="input"
                    value={addTeamId}
                    onChange={e => setAddTeamId(e.target.value)}
                  >
                    <option value="">Select a team…</option>
                    {availableTeams.map(t => (
                      <option key={t.id} value={t.id}>{t.name}</option>
                    ))}
                  </select>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                    <label style={{ fontSize: 12, color: 'var(--fg-2)' }}>Enabled for team</label>
                    <input
                      type="checkbox"
                      checked={addEnabled}
                      onChange={e => setAddEnabled(e.target.checked)}
                    />
                  </div>
                  <button
                    className="btn btn--sm btn--primary"
                    onClick={handleAddOverride}
                    disabled={!addTeamId || adding}
                  >
                    {adding ? '…' : 'Add override'}
                  </button>
                  {addError && (
                    <div className="pill pill--bad" style={{ fontSize: 12 }}>{addError}</div>
                  )}
                </div>
              </div>
            </div>
          )}
          <div style={{ textAlign: 'right', marginTop: 12 }}>
            <button className="btn btn--sm btn--ghost" onClick={onClose}>Collapse ▲</button>
          </div>
        </div>
      </td>
    </tr>
  );
}

export default function PluginsPage() {
  const queryClient = useQueryClient();
  const [expandedId, setExpandedId] = useState<string | null>(null);
  const [showModal, setShowModal] = useState(false);
  const [editPlugin, setEditPlugin] = useState<Plugin | null>(null);

  const summaryQuery = useQuery<PluginSummary>({
    queryKey: ['plugins-summary'],
    queryFn: () => fetch(`${BASE}/plugins/summary`).then(r => {
      if (!r.ok) throw new Error(`Failed: ${r.status}`);
      return r.json();
    }),
  });

  const pluginsQuery = useQuery<Plugin[]>({
    queryKey: ['plugins'],
    queryFn: () => fetch(`${BASE}/plugins`).then(r => {
      if (!r.ok) throw new Error(`Failed: ${r.status}`);
      return r.json();
    }),
  });

  const toggleMutation = useMutation({
    mutationFn: ({ id, enabled }: { id: string; enabled: boolean }) =>
      fetch(`${BASE}/plugins/${id}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ enabled }),
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['plugins'] });
      queryClient.invalidateQueries({ queryKey: ['plugins-summary'] });
    },
  });

  const deleteMutation = useMutation({
    mutationFn: (id: string) => fetch(`${BASE}/plugins/${id}`, { method: 'DELETE' }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['plugins'] });
      queryClient.invalidateQueries({ queryKey: ['plugins-summary'] });
    },
  });

  function handleDelete(plugin: Plugin) {
    if (!window.confirm(`Delete plugin "${plugin.name}"?`)) return;
    deleteMutation.mutate(plugin.id);
  }

  function openEdit(plugin: Plugin) {
    setEditPlugin(plugin);
    setShowModal(true);
  }

  function openNew() {
    setEditPlugin(null);
    setShowModal(true);
  }

  function handleModalSaved() {
    queryClient.invalidateQueries({ queryKey: ['plugins'] });
    queryClient.invalidateQueries({ queryKey: ['plugins-summary'] });
    setShowModal(false);
    setEditPlugin(null);
  }

  const summary = summaryQuery.data;
  const plugins = pluginsQuery.data ?? [];

  return (
    <section className="page">
      <div className="page__head">
        <div>
          <h1 className="page__title">Plugins</h1>
          <p className="page__sub">
            {summary
              ? `${summary.total} plugins · ${summary.enabled} enabled · ${summary.total_overrides} team overrides`
              : 'Manage first-party and community plugins'}
          </p>
        </div>
        <div className="page__actions">
          <button className="btn btn--primary" onClick={openNew}>+ Register Plugin</button>
        </div>
      </div>

      <div className="kpi-grid" style={{ marginBottom: 18 }}>
        <div className="kpi">
          <div className="kpi__label">Total plugins</div>
          <div className="kpi__value">{summary?.total ?? '—'}</div>
          <div className="kpi__delta flat">registered</div>
        </div>
        <div className="kpi">
          <div className="kpi__label">Enabled</div>
          <div className="kpi__value">{summary?.enabled ?? '—'}</div>
          <div className="kpi__delta flat">org-wide</div>
        </div>
        <div className="kpi">
          <div className="kpi__label">Disabled</div>
          <div className="kpi__value">{summary?.disabled ?? '—'}</div>
          <div className="kpi__delta flat">org-wide</div>
        </div>
        <div className="kpi">
          <div className="kpi__label">Team overrides</div>
          <div className="kpi__value">{summary?.total_overrides ?? '—'}</div>
          <div className="kpi__delta flat">across all plugins</div>
        </div>
      </div>

      {pluginsQuery.isError && (
        <div className="pill pill--bad" style={{ marginBottom: 12 }}>
          Failed to load plugins: {(pluginsQuery.error as Error).message}
        </div>
      )}

      <div className="card">
        <div className="card__body" style={{ padding: 0 }}>
          {pluginsQuery.isLoading ? (
            <div style={{ padding: '32px 20px', color: 'var(--fg-3)', textAlign: 'center', fontSize: 13 }}>
              Loading plugins…
            </div>
          ) : plugins.length === 0 ? (
            <div style={{ padding: '40px 20px', color: 'var(--fg-2)', textAlign: 'center', fontSize: 13 }}>
              No plugins registered. Click &ldquo;+ Register Plugin&rdquo; to add one.
            </div>
          ) : (
            <table className="tbl">
              <thead>
                <tr>
                  <th>Name</th>
                  <th>Category</th>
                  <th>Version</th>
                  <th>Author</th>
                  <th>Scopes</th>
                  <th>Enabled</th>
                  <th className="num">Overrides</th>
                  <th></th>
                </tr>
              </thead>
              <tbody>
                {plugins.map(plugin => (
                  <React.Fragment key={plugin.id}>
                    <tr style={{ opacity: plugin.enabled ? 1 : 0.6 }}>
                      <td>
                        <div className="cell-2">
                          <span style={{ fontWeight: 500 }}>{plugin.name}</span>
                          <span className="lo mono" style={{ fontSize: 11 }}>{plugin.slug}</span>
                        </div>
                      </td>
                      <td>{categoryBadge(plugin.category)}</td>
                      <td>
                        <span className="mono" style={{ fontSize: 12 }}>{plugin.version}</span>
                      </td>
                      <td style={{ fontSize: 13 }}>{plugin.author}</td>
                      <td>
                        {plugin.scopes.length === 0 ? (
                          <span style={{ color: 'var(--fg-3)' }}>—</span>
                        ) : (
                          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 4 }}>
                            {plugin.scopes.map(scope => (
                              <span
                                key={scope}
                                style={{
                                  fontSize: 10,
                                  padding: '1px 6px',
                                  background: 'var(--surface-soft)',
                                  border: '1px solid var(--rule)',
                                  borderRadius: 4,
                                  color: 'var(--fg-2)',
                                }}
                              >
                                {scope}
                              </span>
                            ))}
                          </div>
                        )}
                      </td>
                      <td>
                        <button
                          style={{
                            background: 'none',
                            border: 'none',
                            cursor: 'pointer',
                            padding: 0,
                            display: 'flex',
                            alignItems: 'center',
                          }}
                          title={plugin.enabled ? 'Click to disable' : 'Click to enable'}
                          onClick={() => toggleMutation.mutate({ id: plugin.id, enabled: !plugin.enabled })}
                        >
                          <span className={`pill ${plugin.enabled ? 'pill--good' : 'pill--bad'}`}>
                            <span className="dot" />{plugin.enabled ? 'on' : 'off'}
                          </span>
                        </button>
                      </td>
                      <td className="num">
                        <button
                          className="btn btn--sm"
                          onClick={() => setExpandedId(id => id === plugin.id ? null : plugin.id)}
                          title={expandedId === plugin.id ? 'Collapse' : 'Show team overrides'}
                        >
                          {plugin.override_count > 0 ? (
                            <span>
                              {plugin.override_count} {expandedId === plugin.id ? '▼' : '▶'}
                            </span>
                          ) : (
                            <span style={{ color: 'var(--fg-3)' }}>
                              0 {expandedId === plugin.id ? '▼' : '▶'}
                            </span>
                          )}
                        </button>
                      </td>
                      <td>
                        <div style={{ display: 'flex', gap: 4, alignItems: 'center', justifyContent: 'flex-end' }}>
                          <button
                            className="btn btn--sm"
                            onClick={() => openEdit(plugin)}
                            title="Edit plugin"
                          >
                            Edit
                          </button>
                          <button
                            className="btn btn--sm btn--ghost"
                            style={{ color: 'var(--bad)' }}
                            onClick={() => handleDelete(plugin)}
                            title="Delete plugin"
                          >
                            ✕
                          </button>
                        </div>
                      </td>
                    </tr>
                    {expandedId === plugin.id && (
                      <ExpandedRow
                        pluginId={plugin.id}
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
        <PluginModal
          editPlugin={editPlugin}
          onClose={() => { setShowModal(false); setEditPlugin(null); }}
          onSaved={handleModalSaved}
        />
      )}
    </section>
  );
}
