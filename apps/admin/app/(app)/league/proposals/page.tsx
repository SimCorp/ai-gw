'use client';

import React, { useState } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { LoadingState, ErrorState } from '../../_components/PageStates';

const LEAGUE = process.env.NEXT_PUBLIC_LEAGUE_API ?? 'http://localhost:8080/league';

type ProposalStatus = 'pending' | 'approved' | 'rejected';

interface Proposal {
  id: string;
  title: string;
  goal: string;
  status: ProposalStatus;
  proposed_by: string;
  proposer_name?: string;
  created_at: string;
  reviewer_notes?: string;
}

const STATUS_COLORS: Record<ProposalStatus, string> = {
  pending: 'var(--warn)',
  approved: 'var(--good)',
  rejected: 'var(--bad)',
};

function StatusPill({ status }: { status: ProposalStatus }) {
  return (
    <span style={{
      display: 'inline-flex', alignItems: 'center', gap: 5,
      padding: '2px 10px', borderRadius: 20, fontSize: 12, fontWeight: 600,
      background: `color-mix(in srgb, ${STATUS_COLORS[status]} 15%, transparent)`,
      color: STATUS_COLORS[status],
    }}>
      {status}
    </span>
  );
}

async function reviewProposal(id: string, action: 'approved' | 'rejected', notes: string) {
  const res = await fetch(`${LEAGUE}/proposals/${id}/review`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ status: action, reviewer_notes: notes }),
  });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(d.detail ?? 'Failed'); }
}

interface ReviewModalProps {
  proposal: Proposal;
  onClose: () => void;
  onSaved: () => void;
}

function ReviewModal({ proposal, onClose, onSaved }: ReviewModalProps) {
  const [notes, setNotes] = useState('');
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');

  async function handle(action: 'approved' | 'rejected') {
    setSaving(true);
    setError('');
    try {
      await reviewProposal(proposal.id, action, notes);
      onSaved();
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : 'Failed');
    } finally {
      setSaving(false);
    }
  }

  return (
    <div style={{
      position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.5)',
      display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 1000,
    }}>
      <div style={{
        background: 'var(--surface)', border: '1px solid var(--rule)',
        borderRadius: 12, padding: '24px', width: 500, boxShadow: 'var(--shadow-pop)',
      }}>
        <h2 style={{ margin: '0 0 4px', fontSize: 17, fontWeight: 600 }}>Review Proposal</h2>
        <p style={{ margin: '0 0 20px', fontSize: 13, color: 'var(--fg-3)' }}>from {proposal.proposer_name ?? proposal.proposed_by}</p>

        <div style={{
          background: 'var(--bg)', border: '1px solid var(--rule)', borderRadius: 8, padding: '14px',
          marginBottom: 16,
        }}>
          <div style={{ fontWeight: 600, marginBottom: 6 }}>{proposal.title}</div>
          <div style={{ fontSize: 13, color: 'var(--fg-2)', lineHeight: 1.5 }}>{proposal.goal}</div>
        </div>

        {error && (
          <div style={{ marginBottom: 14, padding: '9px 12px', borderRadius: 6, fontSize: 13,
            background: 'var(--bad-soft)', border: '1px solid var(--bad)', color: 'var(--bad)' }}>
            {error}
          </div>
        )}

        <label style={{ fontSize: 12.5, fontWeight: 500, color: 'var(--fg-2)', display: 'block', marginBottom: 16 }}>
          Reviewer notes (optional)
          <textarea
            value={notes}
            onChange={e => setNotes(e.target.value)}
            rows={3}
            placeholder="Feedback for the engineer…"
            style={{
              width: '100%', boxSizing: 'border-box', marginTop: 5,
              padding: '8px 10px', fontSize: 13,
              background: 'var(--bg)', border: '1px solid var(--rule)',
              borderRadius: 6, color: 'var(--fg-1)', resize: 'vertical',
            }}
          />
        </label>

        <div style={{ display: 'flex', gap: 10, justifyContent: 'flex-end' }}>
          <button onClick={onClose} style={{
            padding: '8px 16px', borderRadius: 6, border: '1px solid var(--rule)',
            background: 'transparent', color: 'var(--fg-2)', cursor: 'pointer', fontSize: 13,
          }}>Cancel</button>
          <button onClick={() => handle('rejected')} disabled={saving} style={{
            padding: '8px 16px', borderRadius: 6, border: 'none',
            background: 'var(--bad-soft)', color: 'var(--bad)',
            cursor: saving ? 'not-allowed' : 'pointer', fontSize: 13, fontWeight: 600,
          }}>Reject</button>
          <button onClick={() => handle('approved')} disabled={saving} style={{
            padding: '8px 18px', borderRadius: 6, border: 'none',
            background: 'var(--good)', color: '#fff',
            cursor: saving ? 'not-allowed' : 'pointer', fontSize: 13, fontWeight: 600,
          }}>Approve</button>
        </div>
      </div>
    </div>
  );
}

export default function ProposalsPage() {
  const qc = useQueryClient();
  const [reviewing, setReviewing] = useState<Proposal | null>(null);
  const [filter, setFilter] = useState<'all' | ProposalStatus>('pending');

  const { data, isLoading, error } = useQuery<Proposal[] | { proposals?: Proposal[] }>({
    queryKey: ['league-proposals', filter],
    queryFn: () => {
      const url = filter === 'all'
        ? `${LEAGUE}/proposals`
        : `${LEAGUE}/proposals?status=${filter}`;
      return fetch(url).then(r => r.json());
    },
  });

  const proposals = Array.isArray(data) ? data : data?.proposals ?? [];

  if (isLoading) return <LoadingState />;
  if (error) return <ErrorState error={new Error("Could not load proposals")} />;

  return (
    <div className="page">
      <div className="page__header">
        <div>
          <h1 className="page__title">Community Proposals</h1>
          <p className="page__sub">Review engineer-submitted challenge ideas</p>
        </div>
        <div style={{ display: 'flex', gap: 6 }}>
          {(['all', 'pending', 'approved', 'rejected'] as const).map(f => (
            <button
              key={f}
              onClick={() => setFilter(f)}
              style={{
                padding: '6px 14px', borderRadius: 6, fontSize: 12.5, fontWeight: 500,
                border: '1px solid var(--rule)', cursor: 'pointer',
                background: filter === f ? 'var(--accent)' : 'transparent',
                color: filter === f ? 'var(--accent-fg)' : 'var(--fg-2)',
              }}
            >
              {f.charAt(0).toUpperCase() + f.slice(1)}
            </button>
          ))}
        </div>
      </div>

      {proposals.length === 0 ? (
        <div style={{
          textAlign: 'center', padding: '60px 20px',
          border: '1px dashed var(--rule)', borderRadius: 10, color: 'var(--fg-3)',
        }}>
          <div style={{ fontSize: 36, marginBottom: 12 }}>💡</div>
          <div style={{ fontWeight: 600, marginBottom: 6 }}>No proposals</div>
          <div style={{ fontSize: 13 }}>Engineers can submit challenge ideas from the developer portal</div>
        </div>
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
          {proposals.map(p => (
            <div key={p.id} style={{
              background: 'var(--surface)', border: '1px solid var(--rule)',
              borderRadius: 10, padding: '18px 20px',
              display: 'flex', alignItems: 'flex-start', gap: 16,
            }}>
              <div style={{ flex: 1, minWidth: 0 }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 6 }}>
                  <span style={{ fontWeight: 600, fontSize: 14 }}>{p.title}</span>
                  <StatusPill status={p.status} />
                </div>
                <div style={{ fontSize: 12.5, color: 'var(--fg-3)', marginBottom: 6 }}>{p.goal}</div>
                <div style={{ fontSize: 11.5, color: 'var(--fg-3)' }}>
                  Submitted by {p.proposer_name ?? p.proposed_by} · {new Date(p.created_at).toLocaleDateString()}
                </div>
                {p.reviewer_notes && (
                  <div style={{ marginTop: 8, fontSize: 12.5, color: 'var(--fg-2)', fontStyle: 'italic' }}>
                    Notes: {p.reviewer_notes}
                  </div>
                )}
              </div>
              {p.status === 'pending' && (
                <button
                  onClick={() => setReviewing(p)}
                  style={{
                    padding: '6px 14px', borderRadius: 6, border: '1px solid var(--rule)',
                    background: 'transparent', color: 'var(--fg-2)', cursor: 'pointer', fontSize: 12.5, flexShrink: 0,
                  }}
                >Review</button>
              )}
            </div>
          ))}
        </div>
      )}

      {reviewing && (
        <ReviewModal
          proposal={reviewing}
          onClose={() => setReviewing(null)}
          onSaved={() => { setReviewing(null); qc.invalidateQueries({ queryKey: ['league-proposals'] }); }}
        />
      )}
    </div>
  );
}
