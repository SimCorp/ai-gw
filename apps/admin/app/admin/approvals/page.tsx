'use client';

import React, { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { LoadingState, ErrorState } from '../_components/PageStates';
import { apiFetch } from '../../../lib/apiClient';

interface AccessRequest {
  id: string;
  request_type: string;
  resource_id: string;
  justification: string | null;
  status: string;
  reviewed_by: string | null;
  reviewed_at: string | null;
  review_note: string | null;
  created_at: string;
  requester_email: string;
  requester_name: string | null;
}

const STATUS_COLORS: Record<string, string> = {
  pending: '#FB9B2A',
  approved: '#1D958E',
  rejected: '#EF3E4A',
};

export default function ApprovalsPage() {
  const qc = useQueryClient();
  const [filter, setFilter] = useState<string>('pending');
  const [reviewing, setReviewing] = useState<string | null>(null);
  const [note, setNote] = useState('');

  const { data: requests, isLoading, error } = useQuery<AccessRequest[]>({
    queryKey: ['access-requests', filter],
    queryFn: () => apiFetch(`/access-requests?status=${filter}`),
  });

  const decide = useMutation({
    mutationFn: ({ id, status }: { id: string; status: string }) =>
      apiFetch(`/access-requests/${id}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ status, review_note: note }),
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['access-requests'] });
      setReviewing(null);
      setNote('');
    },
  });

  if (isLoading) return <LoadingState rows={4} />;
  if (error) return <ErrorState error={new Error("Failed to load access requests")} />;

  return (
    <div>
      <div style={{ marginBottom: 24 }}>
        <h1 style={{ fontSize: 22, fontWeight: 700, color: 'var(--fg)', margin: 0 }}>Approvals</h1>
        <p style={{ fontSize: 13, color: 'var(--fg-3)', margin: '4px 0 0' }}>
          Review model access and budget increase requests from your teams.
        </p>
      </div>

      <div style={{ display: 'flex', gap: 8, marginBottom: 16 }}>
        {['pending', 'approved', 'rejected'].map(s => (
          <button key={s} onClick={() => setFilter(s)} style={{
            padding: '6px 14px', fontSize: 13, borderRadius: 6,
            border: `1px solid ${filter === s ? 'var(--sc-blue)' : 'var(--rule)'}`,
            background: filter === s ? 'var(--sc-blue)' : 'transparent',
            color: filter === s ? '#fff' : 'var(--fg)', cursor: 'pointer', textTransform: 'capitalize',
          }}>{s}</button>
        ))}
      </div>

      <div style={{ background: 'var(--surface)', border: '1px solid var(--rule)', borderRadius: 8, overflow: 'hidden' }}>
        <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
          <thead>
            <tr style={{ background: 'var(--surface-2)', borderBottom: '2px solid var(--rule)' }}>
              {['Requester', 'Type', 'Resource', 'Justification', 'Status', ''].map(h => (
                <th key={h} style={{ padding: '10px 14px', textAlign: 'left', fontWeight: 600, color: 'var(--fg-3)', fontSize: 11, textTransform: 'uppercase' }}>{h}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {(requests ?? []).length === 0 && (
              <tr><td colSpan={6} style={{ padding: 32, textAlign: 'center', color: 'var(--fg-3)' }}>No {filter} requests</td></tr>
            )}
            {(requests ?? []).map(r => (
              <React.Fragment key={r.id}>
                <tr style={{ borderBottom: '1px solid var(--rule)' }}>
                  <td style={{ padding: '10px 14px' }}>
                    <div style={{ fontWeight: 500 }}>{r.requester_name || r.requester_email}</div>
                    <div style={{ fontSize: 11, color: 'var(--fg-3)' }}>{r.requester_email}</div>
                  </td>
                  <td style={{ padding: '10px 14px', color: 'var(--fg-3)' }}>{r.request_type.replace('_', ' ')}</td>
                  <td style={{ padding: '10px 14px', fontFamily: 'monospace', fontSize: 12 }}>{r.resource_id}</td>
                  <td style={{ padding: '10px 14px', color: 'var(--fg-3)', maxWidth: 200 }}>{r.justification || '—'}</td>
                  <td style={{ padding: '10px 14px' }}>
                    <span style={{
                      display: 'inline-block', padding: '2px 8px', borderRadius: 10, fontSize: 11, fontWeight: 600,
                      background: (STATUS_COLORS[r.status] ?? '#888') + '22',
                      color: STATUS_COLORS[r.status] ?? '#888',
                      border: `1px solid ${(STATUS_COLORS[r.status] ?? '#888')}44`,
                    }}>
                      {r.status}
                    </span>
                  </td>
                  <td style={{ padding: '10px 14px', textAlign: 'right' }}>
                    {r.status === 'pending' && (
                      <button
                        onClick={() => setReviewing(r.id)}
                        style={{ padding: '4px 10px', fontSize: 12, background: 'var(--sc-blue)', color: '#fff', border: 'none', borderRadius: 4, cursor: 'pointer' }}
                      >
                        Review
                      </button>
                    )}
                  </td>
                </tr>
                {reviewing === r.id && (
                  <tr style={{ background: 'var(--surface-2)', borderBottom: '1px solid var(--rule)' }}>
                    <td colSpan={6} style={{ padding: 16 }}>
                      <div style={{ display: 'flex', flexDirection: 'column', gap: 10, maxWidth: 500 }}>
                        <textarea
                          value={note}
                          onChange={e => setNote(e.target.value)}
                          placeholder="Review note (optional)"
                          rows={2}
                          style={{ padding: '7px 10px', fontSize: 13, background: 'var(--surface)', border: '1px solid var(--rule)', borderRadius: 6, color: 'var(--fg)', resize: 'vertical' }}
                        />
                        <div style={{ display: 'flex', gap: 8 }}>
                          <button
                            onClick={() => decide.mutate({ id: r.id, status: 'approved' })}
                            disabled={decide.isPending}
                            style={{ padding: '6px 16px', background: '#1D958E', color: '#fff', border: 'none', borderRadius: 6, cursor: 'pointer', fontSize: 13, fontWeight: 600 }}
                          >
                            Approve
                          </button>
                          <button
                            onClick={() => decide.mutate({ id: r.id, status: 'rejected' })}
                            disabled={decide.isPending}
                            style={{ padding: '6px 16px', background: '#EF3E4A', color: '#fff', border: 'none', borderRadius: 6, cursor: 'pointer', fontSize: 13, fontWeight: 600 }}
                          >
                            Reject
                          </button>
                          <button
                            onClick={() => { setReviewing(null); setNote(''); }}
                            style={{ padding: '6px 14px', background: 'transparent', border: '1px solid var(--rule)', borderRadius: 6, color: 'var(--fg)', cursor: 'pointer', fontSize: 13 }}
                          >
                            Cancel
                          </button>
                        </div>
                      </div>
                    </td>
                  </tr>
                )}
              </React.Fragment>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
