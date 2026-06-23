'use client';

import React, { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { apiFetch } from '../../../../../lib/apiClient';
import { LoadingState, ErrorState } from '../../../_components/PageStates';

interface BudgetData {
  budget_usd: number | null;
  spend_mtd: number;
  spend_children_mtd: number;
  pct_used: number | null;
  parent_budget: number | null;
}

interface BudgetPanelProps {
  nodeId: string;
}

export function BudgetPanel({ nodeId }: BudgetPanelProps) {
  const queryClient = useQueryClient();
  const [showEditForm, setShowEditForm] = useState(false);
  const [budgetInput, setBudgetInput] = useState('');

  const { data, isLoading, error } = useQuery<BudgetData>({
    queryKey: ['node-budget', nodeId],
    queryFn: () => apiFetch(`/nodes/${nodeId}/budget`),
    staleTime: 30_000,
  });

  const saveMutation = useMutation({
    mutationFn: (monthly_budget_usd: number | null) =>
      apiFetch(`/nodes/${nodeId}/budget`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ monthly_budget_usd }),
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['node-budget', nodeId] });
      queryClient.invalidateQueries({ queryKey: ['node', nodeId] });
      setShowEditForm(false);
    },
  });

  if (isLoading) return <LoadingState rows={4} />;
  if (error) return <ErrorState error={error as Error} />;
  if (!data) return null;

  const pct = data.pct_used != null ? Math.min(data.pct_used * 100, 100) : null;
  const budgetSet = data.budget_usd != null;
  const barColor = pct == null ? 'var(--fg-3)' : pct >= 90 ? 'var(--bad)' : pct >= 70 ? 'var(--warn)' : 'var(--good)';

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 24 }}>
      {/* Budget bar */}
      {budgetSet && pct != null && (
        <div>
          <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 12, color: 'var(--fg-3)', marginBottom: 6 }}>
            <span>Spend this month</span>
            <span style={{ fontWeight: 600, color: barColor }}>{pct.toFixed(1)}% used</span>
          </div>
          <div style={{ height: 10, background: 'var(--surface-2)', borderRadius: 5, overflow: 'hidden', border: '1px solid var(--rule)' }}>
            <div style={{ height: '100%', width: `${pct}%`, background: barColor, borderRadius: 5, transition: 'width 0.4s' }} />
          </div>
        </div>
      )}

      {/* KPI cards */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(160px, 1fr))', gap: 12 }}>
        <KpiCard label="Spend MTD" value={`$${data.spend_mtd.toLocaleString()}`} />
        {budgetSet && <KpiCard label="Budget" value={`$${data.budget_usd!.toLocaleString()}`} />}
        {budgetSet && pct != null && (
          <KpiCard label="Remaining" value={`$${(data.budget_usd! - data.spend_mtd).toLocaleString()}`} accent={pct >= 90} />
        )}
        {data.parent_budget != null && (
          <KpiCard label="Parent budget" value={`$${data.parent_budget.toLocaleString()}`} muted />
        )}
      </div>

      {/* Edit budget */}
      <div>
        {showEditForm ? (
          <div style={{
            display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap',
            padding: '12px 14px', background: 'var(--surface-2)',
            border: '1px solid var(--rule)', borderRadius: 7,
          }}>
            <label style={{ fontSize: 12, color: 'var(--fg-3)', marginRight: 4 }}>Monthly budget (USD):</label>
            <input
              type="number"
              min={0}
              placeholder="e.g. 5000"
              value={budgetInput}
              onChange={e => setBudgetInput(e.target.value)}
              style={{ flex: '1 1 140px', padding: '6px 10px', fontSize: 12, background: 'var(--surface)', border: '1px solid var(--rule)', borderRadius: 5, color: 'var(--fg-1)' }}
            />
            <button
              onClick={() => saveMutation.mutate(budgetInput ? parseFloat(budgetInput) : null)}
              disabled={saveMutation.isPending}
              style={{ padding: '6px 12px', fontSize: 12, background: 'var(--accent)', color: '#fff', border: 'none', borderRadius: 5, cursor: 'pointer' }}
            >
              Save
            </button>
            <button
              onClick={() => { setShowEditForm(false); setBudgetInput(''); }}
              style={{ padding: '6px 12px', fontSize: 12, background: 'transparent', color: 'var(--fg-3)', border: '1px solid var(--rule)', borderRadius: 5, cursor: 'pointer' }}
            >
              Cancel
            </button>
            {data.parent_budget != null && (
              <span style={{ fontSize: 11, color: 'var(--fg-3)' }}>
                Parent budget: ${data.parent_budget.toLocaleString()}
              </span>
            )}
          </div>
        ) : (
          <button
            onClick={() => { setShowEditForm(true); setBudgetInput(data.budget_usd?.toString() ?? ''); }}
            style={{
              padding: '7px 14px', fontSize: 12,
              background: 'var(--surface-2)', border: '1px solid var(--rule)',
              borderRadius: 6, color: 'var(--fg-1)', cursor: 'pointer',
            }}
          >
            {budgetSet ? 'Edit budget' : 'Set budget'}
          </button>
        )}
        {saveMutation.isError && (
          <div style={{ marginTop: 8, fontSize: 12, color: 'var(--bad)' }}>
            {(saveMutation.error as Error).message}
          </div>
        )}
      </div>
    </div>
  );
}

function KpiCard({ label, value, accent, muted }: { label: string; value: string; accent?: boolean; muted?: boolean }) {
  return (
    <div style={{
      padding: '14px 16px',
      background: 'var(--surface)',
      border: `1px solid ${accent ? 'color-mix(in srgb, var(--bad) 27%, transparent)' : 'var(--rule)'}`,
      borderRadius: 8,
    }}>
      <div className="microlabel" style={{ marginBottom: 4 }}>
        {label}
      </div>
      <div style={{ fontSize: 20, fontWeight: 700, color: accent ? 'var(--bad)' : muted ? 'var(--fg-3)' : 'var(--fg-1)' }}>
        {value}
      </div>
    </div>
  );
}
