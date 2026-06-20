'use client';

import React, { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { apiFetch } from '../../../lib/apiClient';

interface Tool {
  tool_id: string;
  label: string;
  category: string;
  enabled: boolean;
  updated_at: string;
}

export default function ToolsAdminPage() {
  const qc = useQueryClient();
  const [search, setSearch] = useState('');
  const [activeCategory, setActiveCategory] = useState('All');

  const { data: tools = [], isLoading } = useQuery<Tool[]>({
    queryKey: ['tools'],
    queryFn: () => apiFetch('/tools'),
  });

  const toggleMutation = useMutation({
    mutationFn: ({ tool_id, enabled }: { tool_id: string; enabled: boolean }) =>
      apiFetch<Tool>(`/tools/${tool_id}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ enabled }),
      }),
    onMutate: async ({ tool_id, enabled }) => {
      await qc.cancelQueries({ queryKey: ['tools'] });
      const prev = qc.getQueryData<Tool[]>(['tools']);
      qc.setQueryData<Tool[]>(['tools'], old =>
        old?.map(t => t.tool_id === tool_id ? { ...t, enabled } : t) ?? []
      );
      return { prev };
    },
    onError: (_err, _vars, ctx) => {
      if (ctx?.prev) qc.setQueryData(['tools'], ctx.prev);
    },
  });

  const filtered = tools.filter(t => {
    const q = search.toLowerCase();
    const matchesSearch = !q || t.label.toLowerCase().includes(q) || t.category.toLowerCase().includes(q);
    const matchesCategory = activeCategory === 'All' || t.category === activeCategory;
    return matchesSearch && matchesCategory;
  });

  const enabledCount = tools.filter(t => t.enabled).length;
  const categories = ['All', ...Array.from(new Set(tools.map(t => t.category))).sort()];

  return (
    <div style={{ padding: '32px 40px', maxWidth: 900 }}>
      <div style={{ marginBottom: 28 }}>
        <h1 style={{ fontSize: 22, fontWeight: 700, margin: 0 }}>Developer Tools</h1>
        <p style={{ color: 'var(--panel-fg-mute)', marginTop: 4, fontSize: 14 }}>
          Manage which tools are available in the developer portal
        </p>
      </div>

      <div style={{ display: 'flex', gap: 16, marginBottom: 24 }}>
        <div style={{ background: 'var(--surface)', border: '1px solid var(--rule)', borderRadius: 8, padding: '12px 20px', minWidth: 120 }}>
          <div style={{ fontSize: 24, fontWeight: 700 }}>{tools.length}</div>
          <div style={{ fontSize: 12, color: 'var(--panel-fg-mute)', marginTop: 2 }}>Total tools</div>
        </div>
        <div style={{ background: 'var(--surface)', border: '1px solid var(--rule)', borderRadius: 8, padding: '12px 20px', minWidth: 120 }}>
          <div style={{ fontSize: 24, fontWeight: 700, color: 'var(--good)' }}>{enabledCount}</div>
          <div style={{ fontSize: 12, color: 'var(--panel-fg-mute)', marginTop: 2 }}>Enabled</div>
        </div>
        <div style={{ background: 'var(--surface)', border: '1px solid var(--rule)', borderRadius: 8, padding: '12px 20px', minWidth: 120 }}>
          <div style={{ fontSize: 24, fontWeight: 700, color: 'var(--bad)' }}>{tools.length - enabledCount}</div>
          <div style={{ fontSize: 12, color: 'var(--panel-fg-mute)', marginTop: 2 }}>Disabled</div>
        </div>
      </div>

      <div style={{ display: 'flex', gap: 12, marginBottom: 16, flexWrap: 'wrap' }}>
        <input
          type="search"
          placeholder="Search tools…"
          value={search}
          onChange={e => setSearch(e.target.value)}
          style={{
            flex: '1 1 200px', maxWidth: 300, padding: '7px 12px',
            background: 'var(--surface)', border: '1px solid var(--rule)',
            borderRadius: 6, color: 'var(--fg-1)', fontSize: 13,
          }}
        />
      </div>

      <div style={{ display: 'flex', gap: 6, marginBottom: 20, flexWrap: 'wrap' }}>
        {categories.map(cat => (
          <button
            key={cat}
            onClick={() => setActiveCategory(cat)}
            style={{
              padding: '4px 10px', borderRadius: 16, fontSize: 12, cursor: 'pointer',
              border: '1px solid var(--rule)', fontFamily: 'inherit',
              background: activeCategory === cat ? 'var(--accent)' : 'var(--surface)',
              color: activeCategory === cat ? 'var(--accent-fg)' : 'var(--panel-fg-mute)',
            }}
          >
            {cat}
          </button>
        ))}
      </div>

      {isLoading && <p style={{ color: 'var(--panel-fg-mute)' }}>Loading…</p>}

      <div style={{ display: 'flex', flexDirection: 'column', gap: 1 }}>
        {filtered.map(tool => (
          <div
            key={tool.tool_id}
            style={{
              display: 'flex', alignItems: 'center', gap: 16,
              padding: '12px 16px', borderRadius: 6,
              background: 'var(--surface)', border: '1px solid var(--rule)',
            }}
          >
            <div style={{ flex: 1 }}>
              <div style={{ fontWeight: 600, fontSize: 14 }}>{tool.label}</div>
              <div style={{ fontSize: 12, color: 'var(--panel-fg-mute)', marginTop: 2 }}>{tool.category}</div>
            </div>
            <label style={{ display: 'flex', alignItems: 'center', gap: 8, cursor: 'pointer' }}>
              <span style={{ fontSize: 12, color: tool.enabled ? 'var(--good)' : 'var(--bad)' }}>
                {tool.enabled ? 'Enabled' : 'Disabled'}
              </span>
              <div
                onClick={() => toggleMutation.mutate({ tool_id: tool.tool_id, enabled: !tool.enabled })}
                style={{
                  width: 36, height: 20, borderRadius: 10, cursor: 'pointer',
                  background: tool.enabled ? 'var(--good)' : 'var(--rule)',
                  position: 'relative', transition: 'background 0.2s',
                }}
              >
                <div style={{
                  position: 'absolute', top: 3, left: tool.enabled ? 19 : 3,
                  width: 14, height: 14, borderRadius: '50%',
                  background: '#fff', transition: 'left 0.2s',
                }} />
              </div>
            </label>
          </div>
        ))}
      </div>

      {!isLoading && filtered.length === 0 && (
        <p style={{ color: 'var(--panel-fg-mute)', padding: '24px 0' }}>No tools match your filter.</p>
      )}
    </div>
  );
}
