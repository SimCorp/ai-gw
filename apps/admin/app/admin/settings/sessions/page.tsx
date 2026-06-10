'use client';

import React from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { LoadingState, ErrorState } from '../../_components/PageStates';
import { apiFetch } from '../../../../lib/apiClient';

interface Session {
  session_id: string;
  issued_at: number;
}

export default function SessionsPage() {
  const qc = useQueryClient();
  const { data: sessions, isLoading, error } = useQuery<Session[]>({
    queryKey: ['my-sessions'],
    queryFn: () => apiFetch('/auth/sessions'),
  });

  const revokeAll = useMutation({
    mutationFn: () => apiFetch('/auth/sessions', { method: 'DELETE' }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['my-sessions'] }),
  });

  const revoke = useMutation({
    mutationFn: (id: string) => apiFetch(`/auth/sessions/${id}`, { method: 'DELETE' }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['my-sessions'] }),
  });

  if (isLoading) return <LoadingState rows={3} />;
  if (error) return <ErrorState error={error as Error} />;

  return (
    <div>
      <div style={{ marginBottom: 24 }}>
        <h1 style={{ fontSize: 22, fontWeight: 700, color: 'var(--fg-1)', margin: 0 }}>
          Active Sessions
        </h1>
        <p style={{ fontSize: 13, color: 'var(--fg-3)', margin: '4px 0 0' }}>
          Your currently active sign-in sessions.
        </p>
      </div>

      <div style={{ marginBottom: 16 }}>
        <button
          onClick={() => revokeAll.mutate()}
          disabled={revokeAll.isPending}
          style={{
            padding: '8px 16px', fontSize: 13, fontWeight: 600,
            background: 'var(--bad-soft)', color: 'var(--bad)',
            border: '1px solid color-mix(in srgb, var(--bad) 27%, transparent)', borderRadius: 6, cursor: 'pointer',
          }}
        >
          Sign out all other sessions
        </button>
      </div>

      <div style={{ background: 'var(--surface)', border: '1px solid var(--rule)', borderRadius: 8, overflow: 'hidden' }}>
        <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
          <thead>
            <tr style={{ background: 'var(--surface-2)', borderBottom: '2px solid var(--rule)' }}>
              <th style={{ padding: '10px 14px', textAlign: 'left', fontWeight: 600, color: 'var(--fg-3)', fontSize: 11, textTransform: 'uppercase' }}>Session</th>
              <th style={{ padding: '10px 14px', textAlign: 'left', fontWeight: 600, color: 'var(--fg-3)', fontSize: 11, textTransform: 'uppercase' }}>Issued</th>
              <th style={{ padding: '10px 14px' }} />
            </tr>
          </thead>
          <tbody>
            {(sessions ?? []).length === 0 && (
              <tr><td colSpan={3} style={{ padding: 32, textAlign: 'center', color: 'var(--fg-3)' }}>No sessions found</td></tr>
            )}
            {(sessions ?? []).map(s => (
              <tr key={s.session_id} style={{ borderBottom: '1px solid var(--rule)' }}>
                <td style={{ padding: '10px 14px', fontFamily: 'monospace', fontSize: 12, color: 'var(--fg-3)' }}>{s.session_id}</td>
                <td style={{ padding: '10px 14px', color: 'var(--fg-3)' }}>
                  {new Date(s.issued_at * 1000).toLocaleString()}
                </td>
                <td style={{ padding: '10px 14px', textAlign: 'right' }}>
                  <button
                    onClick={() => revoke.mutate(s.session_id)}
                    disabled={revoke.isPending}
                    style={{ padding: '4px 10px', fontSize: 12, background: 'transparent', border: '1px solid var(--rule)', borderRadius: 4, color: 'var(--bad)', cursor: 'pointer' }}
                  >
                    Revoke
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
