'use client';

import React, { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { apiFetch } from '../../../../../lib/apiClient';
import { LoadingState, ErrorState } from '../../../_components/PageStates';

interface PolicyRule {
  key: string;
  value: string;
}

interface InheritedRule {
  key: string;
  value: string;
  source_node_id: string;
  source_name: string;
}

interface PolicyData {
  explicit: Record<string, string>;
  inherited: InheritedRule[];
}

interface PolicyPanelProps {
  nodeId: string;
  nodeName: string;
}

export function PolicyPanel({ nodeId, nodeName }: PolicyPanelProps) {
  const queryClient = useQueryClient();
  const [showAddForm, setShowAddForm] = useState(false);
  const [addKey, setAddKey] = useState('');
  const [addValue, setAddValue] = useState('');
  const [editingKey, setEditingKey] = useState<string | null>(null);
  const [editValue, setEditValue] = useState('');

  const { data, isLoading, error } = useQuery<PolicyData>({
    queryKey: ['node-policy', nodeId],
    queryFn: () => apiFetch(`/nodes/${nodeId}/policy`),
    staleTime: 30_000,
  });

  const saveMutation = useMutation({
    mutationFn: (overrides: Record<string, string>) =>
      apiFetch<PolicyData>(`/nodes/${nodeId}/policy`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ explicit: overrides }),
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['node-policy', nodeId] });
    },
  });

  const handleAdd = () => {
    if (!addKey.trim() || !addValue.trim()) return;
    const updated = { ...(data?.explicit ?? {}), [addKey.trim()]: addValue.trim() };
    saveMutation.mutate(updated, {
      onSuccess: () => {
        setAddKey('');
        setAddValue('');
        setShowAddForm(false);
      },
    });
  };

  const handleRemove = (key: string) => {
    const updated = { ...(data?.explicit ?? {}) };
    delete updated[key];
    saveMutation.mutate(updated);
  };

  const handleSaveEdit = (key: string) => {
    const updated = { ...(data?.explicit ?? {}), [key]: editValue.trim() };
    saveMutation.mutate(updated, {
      onSuccess: () => setEditingKey(null),
    });
  };

  if (isLoading) return <LoadingState rows={4} />;
  if (error) return <ErrorState error={error as Error} />;

  const inherited = data?.inherited ?? [];
  const explicit = data?.explicit ?? {};

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 24 }}>
      {/* Inherited rules */}
      <section>
        <div style={{ fontSize: 13, fontWeight: 600, color: 'var(--fg-1)', marginBottom: 12, display: 'flex', alignItems: 'center', gap: 6 }}>
          <span>Inherited (read-only)</span>
          <span style={{ fontSize: 11, color: 'var(--fg-3)', fontWeight: 400 }}>{inherited.length} rules</span>
        </div>
        {inherited.length === 0 ? (
          <div style={{ fontSize: 12, color: 'var(--fg-3)', padding: '12px 0' }}>No inherited rules.</div>
        ) : (
          <div style={{ background: 'var(--surface)', border: '1px solid var(--rule)', borderRadius: 8, overflow: 'hidden' }}>
            {inherited.map((rule, i) => (
              <div key={`${rule.source_node_id}-${rule.key}`} style={{
                display: 'flex', alignItems: 'center', gap: 10,
                padding: '9px 14px',
                borderBottom: i < inherited.length - 1 ? '1px solid var(--rule)' : 'none',
                background: 'var(--surface-2)',
              }}>
                <span style={{ fontSize: 13, color: 'var(--fg-3)', flexShrink: 0 }}>&#x1F512;</span>
                <span style={{ fontSize: 12, fontFamily: 'monospace', color: 'var(--fg-1)', flex: 1 }}>
                  {rule.key} = <span style={{ color: 'var(--accent)' }}>{rule.value}</span>
                </span>
                <span style={{ fontSize: 11, color: 'var(--fg-3)', flexShrink: 0 }}>
                  from {rule.source_name}
                </span>
              </div>
            ))}
          </div>
        )}
      </section>

      {/* Explicit overrides */}
      <section>
        <div style={{ fontSize: 13, fontWeight: 600, color: 'var(--fg-1)', marginBottom: 12, display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
          <span>Overrides on <em style={{ fontStyle: 'italic', fontWeight: 500 }}>{nodeName}</em></span>
          <button
            onClick={() => setShowAddForm(v => !v)}
            style={{
              padding: '5px 12px', fontSize: 12,
              background: 'var(--accent)', color: '#fff',
              border: 'none', borderRadius: 5, cursor: 'pointer',
            }}
          >
            + Add override
          </button>
        </div>

        {showAddForm && (
          <div style={{
            display: 'flex', gap: 8, marginBottom: 12,
            padding: '12px 14px', background: 'var(--surface-2)',
            border: '1px solid var(--rule)', borderRadius: 7,
            flexWrap: 'wrap', alignItems: 'center',
          }}>
            <input
              placeholder="key"
              value={addKey}
              onChange={e => setAddKey(e.target.value)}
              style={{ flex: '1 1 140px', padding: '6px 10px', fontSize: 12, background: 'var(--surface)', border: '1px solid var(--rule)', borderRadius: 5, color: 'var(--fg-1)', fontFamily: 'monospace' }}
            />
            <input
              placeholder="value"
              value={addValue}
              onChange={e => setAddValue(e.target.value)}
              style={{ flex: '2 1 200px', padding: '6px 10px', fontSize: 12, background: 'var(--surface)', border: '1px solid var(--rule)', borderRadius: 5, color: 'var(--fg-1)', fontFamily: 'monospace' }}
            />
            <button
              onClick={handleAdd}
              disabled={saveMutation.isPending}
              style={{ padding: '6px 12px', fontSize: 12, background: 'var(--accent)', color: '#fff', border: 'none', borderRadius: 5, cursor: 'pointer' }}
            >
              Save
            </button>
            <button
              onClick={() => { setShowAddForm(false); setAddKey(''); setAddValue(''); }}
              style={{ padding: '6px 12px', fontSize: 12, background: 'transparent', color: 'var(--fg-3)', border: '1px solid var(--rule)', borderRadius: 5, cursor: 'pointer' }}
            >
              Cancel
            </button>
          </div>
        )}

        {Object.keys(explicit).length === 0 && !showAddForm ? (
          <div style={{ fontSize: 12, color: 'var(--fg-3)', padding: '12px 0' }}>No explicit overrides.</div>
        ) : (
          <div style={{ background: 'var(--surface)', border: '1px solid var(--rule)', borderRadius: 8, overflow: 'hidden' }}>
            {Object.entries(explicit).map(([key, value], i, arr) => (
              <div key={key} style={{
                display: 'flex', alignItems: 'center', gap: 10,
                padding: '9px 14px',
                borderBottom: i < arr.length - 1 ? '1px solid var(--rule)' : 'none',
              }}>
                {editingKey === key ? (
                  <>
                    <span style={{ fontSize: 12, fontFamily: 'monospace', color: 'var(--fg-1)', width: 160 }}>{key} =</span>
                    <input
                      value={editValue}
                      onChange={e => setEditValue(e.target.value)}
                      style={{ flex: 1, padding: '4px 8px', fontSize: 12, background: 'var(--surface-2)', border: '1px solid var(--rule)', borderRadius: 5, color: 'var(--fg-1)', fontFamily: 'monospace' }}
                    />
                    <button
                      onClick={() => handleSaveEdit(key)}
                      disabled={saveMutation.isPending}
                      style={{ padding: '4px 10px', fontSize: 11, background: 'var(--accent)', color: '#fff', border: 'none', borderRadius: 4, cursor: 'pointer' }}
                    >
                      Save
                    </button>
                    <button
                      onClick={() => setEditingKey(null)}
                      style={{ padding: '4px 10px', fontSize: 11, background: 'transparent', color: 'var(--fg-3)', border: '1px solid var(--rule)', borderRadius: 4, cursor: 'pointer' }}
                    >
                      Cancel
                    </button>
                  </>
                ) : (
                  <>
                    <span style={{ fontSize: 12, fontFamily: 'monospace', color: 'var(--fg-1)', flex: 1 }}>
                      {key} = <span style={{ color: 'var(--accent)' }}>{value}</span>
                    </span>
                    <button
                      onClick={() => { setEditingKey(key); setEditValue(value); }}
                      style={{ padding: '3px 9px', fontSize: 11, background: 'var(--surface-2)', border: '1px solid var(--rule)', borderRadius: 4, color: 'var(--fg-1)', cursor: 'pointer' }}
                    >
                      Edit
                    </button>
                    <button
                      onClick={() => handleRemove(key)}
                      disabled={saveMutation.isPending}
                      style={{ padding: '3px 9px', fontSize: 11, background: 'transparent', border: '1px solid var(--rule)', borderRadius: 4, color: 'var(--bad)', cursor: 'pointer' }}
                    >
                      Remove
                    </button>
                  </>
                )}
              </div>
            ))}
          </div>
        )}
      </section>
    </div>
  );
}
