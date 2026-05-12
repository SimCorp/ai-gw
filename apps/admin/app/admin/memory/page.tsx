'use client';

import React, { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';

const BASE = process.env.NEXT_PUBLIC_ADMIN_API ?? 'http://localhost:8005';

interface AggStats {
  total_developers: number;
  total_drawers: number;
  total_kg_nodes: number;
  total_kg_edges: number;
  total_diary_entries: number;
  total_tunnels: number;
}

interface DevRow {
  developer_id: string;
  email: string;
  display_name: string | null;
  drawers: number;
  kg_nodes: number;
  kg_edges: number;
  diary_entries: number;
  tunnels: number;
  last_activity: string | null;
}

interface Taxonomy {
  developer_id: string;
  taxonomy: Record<string, Record<string, number>>;
}

function relativeTime(iso: string | null): string {
  if (!iso) return '—';
  const diff = Date.now() - new Date(iso).getTime();
  const mins = Math.floor(diff / 60_000);
  if (mins < 1) return 'just now';
  if (mins < 60) return `${mins}m ago`;
  const hrs = Math.floor(mins / 60);
  if (hrs < 24) return `${hrs}h ago`;
  return `${Math.floor(hrs / 24)}d ago`;
}

function TaxonomyPanel({ devId, onClose }: { devId: string; onClose: () => void }) {
  const q = useQuery<Taxonomy>({
    queryKey: ['memory-taxonomy', devId],
    queryFn: () =>
      fetch(`${BASE}/memory-admin/developers/${devId}/taxonomy`).then(r => {
        if (!r.ok) throw new Error(`HTTP ${r.status}`);
        return r.json();
      }),
  });

  return (
    <tr>
      <td colSpan={8} style={{ padding: 0, background: 'var(--surface-soft)' }}>
        <div style={{ padding: '14px 20px' }}>
          {q.isLoading && <div style={{ color: 'var(--fg-3)', fontSize: 13 }}>Loading…</div>}
          {q.isError && (
            <span className="pill pill--bad" style={{ fontSize: 12 }}>
              Failed: {(q.error as Error).message}
            </span>
          )}
          {q.data && (
            <div>
              <div style={{ fontWeight: 600, fontSize: 12, color: 'var(--fg-2)', marginBottom: 8, textTransform: 'uppercase', letterSpacing: '0.04em' }}>
                Memory taxonomy — wings & rooms
              </div>
              {Object.keys(q.data.taxonomy).length === 0 ? (
                <div style={{ fontSize: 13, color: 'var(--fg-3)' }}>No drawers found.</div>
              ) : (
                <div style={{ display: 'flex', flexWrap: 'wrap', gap: 10 }}>
                  {Object.entries(q.data.taxonomy).map(([wing, rooms]) => (
                    <div
                      key={wing}
                      style={{
                        border: '1px solid var(--rule)',
                        borderRadius: 8,
                        background: 'var(--surface)',
                        padding: '10px 14px',
                        minWidth: 160,
                      }}
                    >
                      <div style={{ fontWeight: 600, fontSize: 13, marginBottom: 6, display: 'flex', alignItems: 'center', gap: 6 }}>
                        <span style={{ fontSize: 15 }}>🏛</span> {wing}
                        <span className="pill" style={{ fontSize: 10.5, padding: '1px 5px' }}>
                          {Object.values(rooms).reduce((a, b) => a + b, 0)}
                        </span>
                      </div>
                      {Object.entries(rooms).map(([room, count]) => (
                        <div key={room} style={{ display: 'flex', justifyContent: 'space-between', fontSize: 12, color: 'var(--fg-2)', padding: '2px 0', borderTop: '1px solid var(--rule)' }}>
                          <span>{room}</span>
                          <span className="mono" style={{ color: 'var(--fg-3)' }}>{count}</span>
                        </div>
                      ))}
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}
          <div style={{ marginTop: 10, textAlign: 'right' }}>
            <button className="btn btn--sm btn--ghost" onClick={onClose}>Collapse ▲</button>
          </div>
        </div>
      </td>
    </tr>
  );
}

export default function MemoryAdminPage() {
  const queryClient = useQueryClient();
  const [expandedId, setExpandedId] = useState<string | null>(null);

  const statsQ = useQuery<AggStats>({
    queryKey: ['memory-admin-stats'],
    queryFn: () =>
      fetch(`${BASE}/memory-admin/stats`).then(r => {
        if (!r.ok) throw new Error(`HTTP ${r.status}`);
        return r.json();
      }),
  });

  const devsQ = useQuery<DevRow[]>({
    queryKey: ['memory-admin-devs'],
    queryFn: () =>
      fetch(`${BASE}/memory-admin/developers`).then(r => {
        if (!r.ok) throw new Error(`HTTP ${r.status}`);
        return r.json();
      }),
  });

  const purgeMut = useMutation({
    mutationFn: (devId: string) =>
      fetch(`${BASE}/memory-admin/developers/${devId}`, { method: 'DELETE' }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['memory-admin-stats'] });
      queryClient.invalidateQueries({ queryKey: ['memory-admin-devs'] });
      setExpandedId(null);
    },
  });

  function handlePurge(dev: DevRow) {
    const name = dev.display_name ?? dev.email;
    if (!confirm(`Permanently delete all memory data for "${name}"?\n\nThis removes all drawers, KG nodes/edges, diary entries and tunnels. This cannot be undone.`)) return;
    purgeMut.mutate(dev.developer_id);
  }

  const stats = statsQ.data;
  const devs = devsQ.data ?? [];

  return (
    <section className="page">
      <div className="page__head">
        <div>
          <h1 className="page__title">Memory Palace</h1>
          <p className="page__sub">
            {stats
              ? `${stats.total_developers} developers · ${stats.total_drawers} drawers · ${stats.total_kg_nodes} KG nodes · ${stats.total_diary_entries} diary entries`
              : 'Per-developer isolated memory usage across the platform'}
          </p>
        </div>
      </div>

      {/* KPI strip */}
      <div className="kpi-grid" style={{ marginBottom: 18 }}>
        <div className="kpi">
          <div className="kpi__label">Developers</div>
          <div className="kpi__value">{stats?.total_developers ?? '—'}</div>
          <div className="kpi__delta flat">with any memory</div>
        </div>
        <div className="kpi">
          <div className="kpi__label">Drawers</div>
          <div className="kpi__value">{stats?.total_drawers ?? '—'}</div>
          <div className="kpi__delta flat">semantic memories</div>
        </div>
        <div className="kpi">
          <div className="kpi__label">KG nodes</div>
          <div className="kpi__value">{stats?.total_kg_nodes ?? '—'}</div>
          <div className="kpi__delta flat">{stats ? `${stats.total_kg_edges} edges` : ''}</div>
        </div>
        <div className="kpi">
          <div className="kpi__label">Diary entries</div>
          <div className="kpi__value">{stats?.total_diary_entries ?? '—'}</div>
          <div className="kpi__delta flat">{stats ? `${stats.total_tunnels} tunnels` : ''}</div>
        </div>
      </div>

      {devsQ.isError && (
        <div className="pill pill--bad" style={{ marginBottom: 12 }}>
          Failed to load: {(devsQ.error as Error).message}
        </div>
      )}
      {purgeMut.isError && (
        <div className="pill pill--bad" style={{ marginBottom: 12 }}>
          Purge failed: {(purgeMut.error as Error).message}
        </div>
      )}

      <div className="card">
        <div className="card__body" style={{ padding: 0 }}>
          {devsQ.isLoading ? (
            <div style={{ padding: '32px 20px', color: 'var(--fg-3)', textAlign: 'center', fontSize: 13 }}>
              Loading…
            </div>
          ) : devs.length === 0 ? (
            <div style={{ padding: '40px 20px', color: 'var(--fg-2)', textAlign: 'center', fontSize: 13 }}>
              No developers have used Memory Palace yet.
            </div>
          ) : (
            <table className="tbl">
              <thead>
                <tr>
                  <th>Developer</th>
                  <th className="num">Drawers</th>
                  <th className="num">KG nodes</th>
                  <th className="num">KG edges</th>
                  <th className="num">Diary</th>
                  <th className="num">Tunnels</th>
                  <th>Last active</th>
                  <th></th>
                </tr>
              </thead>
              <tbody>
                {devs.map(dev => (
                  <React.Fragment key={dev.developer_id}>
                    <tr>
                      <td>
                        <div className="cell-2">
                          <span style={{ fontWeight: 500 }}>{dev.display_name ?? dev.email}</span>
                          {dev.display_name && (
                            <span className="lo mono" style={{ fontSize: 11.5 }}>{dev.email}</span>
                          )}
                        </div>
                      </td>
                      <td className="num mono">{dev.drawers}</td>
                      <td className="num mono">{dev.kg_nodes}</td>
                      <td className="num mono">{dev.kg_edges}</td>
                      <td className="num mono">{dev.diary_entries}</td>
                      <td className="num mono">{dev.tunnels}</td>
                      <td style={{ fontSize: 12, color: 'var(--fg-3)' }}>
                        {relativeTime(dev.last_activity)}
                      </td>
                      <td>
                        <div style={{ display: 'flex', gap: 4, justifyContent: 'flex-end' }}>
                          <button
                            className="btn btn--sm"
                            onClick={() => setExpandedId(id => id === dev.developer_id ? null : dev.developer_id)}
                            title="Browse taxonomy"
                          >
                            {expandedId === dev.developer_id ? '▼' : '▶'}
                          </button>
                          <button
                            className="btn btn--sm btn--ghost"
                            style={{ color: 'var(--bad)' }}
                            onClick={() => handlePurge(dev)}
                            disabled={purgeMut.isPending}
                            title="Purge all memory for this developer"
                          >
                            Purge
                          </button>
                        </div>
                      </td>
                    </tr>
                    {expandedId === dev.developer_id && (
                      <TaxonomyPanel
                        devId={dev.developer_id}
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
    </section>
  );
}
