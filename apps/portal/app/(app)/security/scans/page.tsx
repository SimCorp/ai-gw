'use client';

import React, { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { useRouter } from 'next/navigation';
import { useAuth } from '../../_lib/authContext';
import { useTeam } from '../../_lib/teamContext';

const ADMIN_API = process.env.NEXT_PUBLIC_ADMIN_API ?? 'http://localhost:8005';
const SCANNER_API = process.env.NEXT_PUBLIC_SCANNER_API ?? 'http://localhost:8011';

interface ScanTarget {
  id: string;
  label: string;
  url: string;
  status: string;
}

interface ScanJob {
  id: string;
  target_id: string;
  tier: string;
  status: string;
  queued_at: string;
  finished_at: string | null;
  partial_results: boolean;
}

const STATUS_PILL: Record<string, string> = {
  queued: 'pill',
  running: 'pill pill--info',
  completed: 'pill pill--good',
  failed: 'pill pill--bad',
  cancelled: 'pill',
};

export default function ScansPage() {
  const { token } = useAuth();
  const { teamId } = useTeam();
  const router = useRouter();
  const qc = useQueryClient();
  const [showForm, setShowForm] = useState(false);
  const [selectedTarget, setSelectedTarget] = useState('');
  const [selectedTier, setSelectedTier] = useState('quick');

  const { data: targets = [] } = useQuery<ScanTarget[]>({
    queryKey: ['portal-scanner-targets-approved', teamId, token],
    queryFn: () =>
      fetch(`${ADMIN_API}/scanner/targets?team_id=${teamId}&status=approved`, {
        headers: { Authorization: `Bearer ${token}` },
      }).then(r => r.json()),
    enabled: !!token && !!teamId,
  });

  const { data: jobs = [] } = useQuery<ScanJob[]>({
    queryKey: ['portal-scanner-jobs', token],
    queryFn: () => fetch(`${SCANNER_API}/jobs`, {
      headers: { Authorization: `Bearer ${token}` },
    }).then(r => r.json()),
    enabled: !!token,
    refetchInterval: 3_000,
  });

  const submit = useMutation({
    mutationFn: () =>
      fetch(`${SCANNER_API}/jobs`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
        body: JSON.stringify({ target_id: selectedTarget, tier: selectedTier }),
      }).then(r => r.json()),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['portal-scanner-jobs'] });
      setShowForm(false);
    },
  });

  return (
    <div className="page">
      <div className="page__head">
        <div>
          <h1 className="page__title">Security — Scans</h1>
          <p className="page__sub">Run security scans against your approved targets</p>
        </div>
        <div className="page__actions">
          <button onClick={() => setShowForm(!showForm)} className="btn btn--primary">
            + Run scan
          </button>
        </div>
      </div>

      {showForm && (
        <div className="card" style={{ padding: 16, marginBottom: 16 }}>
          <div style={{ fontWeight: 600, fontSize: 13.5, marginBottom: 12 }}>New scan</div>
          <div style={{ display: 'flex', gap: 12, alignItems: 'flex-end', flexWrap: 'wrap' }}>
            <div>
              <label className="microlabel" style={{ display: 'block', marginBottom: 5 }}>Target</label>
              <select
                value={selectedTarget}
                onChange={e => setSelectedTarget(e.target.value)}
                className="input"
              >
                <option value="">Select target…</option>
                {targets.map(t => (
                  <option key={t.id} value={t.id}>{t.label}</option>
                ))}
              </select>
            </div>
            <div>
              <label className="microlabel" style={{ display: 'block', marginBottom: 5 }}>Tier</label>
              <select
                value={selectedTier}
                onChange={e => setSelectedTier(e.target.value)}
                className="input"
              >
                <option value="quick">Quick (~5 min)</option>
                <option value="standard">Standard (~15 min)</option>
                <option value="deep">Deep (~45 min)</option>
              </select>
            </div>
            <button
              onClick={() => submit.mutate()}
              disabled={!selectedTarget}
              className="btn btn--primary"
            >
              Start scan
            </button>
            <button onClick={() => setShowForm(false)} className="btn">
              Cancel
            </button>
          </div>
        </div>
      )}

      <div style={{ display: 'grid', gap: 10 }}>
        {jobs.map(j => (
          <div
            key={j.id}
            onClick={() => j.status === 'completed' && router.push(`/security/scans/${j.id}`)}
            className="card"
            style={{
              padding: 16,
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'space-between',
              cursor: j.status === 'completed' ? 'pointer' : 'default',
            }}
          >
            <div>
              <div className="mono" style={{ fontSize: 13, color: 'var(--fg-2)' }}>{j.id.slice(0, 8)}…</div>
              <div style={{ fontSize: 12, color: 'var(--fg-3)', marginTop: 2 }}>
                {j.tier} · {new Date(j.queued_at).toLocaleString()}
              </div>
            </div>
            <span className={STATUS_PILL[j.status] ?? 'pill'}>
              {j.status}{j.partial_results ? ' (partial)' : ''}
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}
