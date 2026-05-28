'use client';

import React, { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { useRouter } from 'next/navigation';

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

const TEAM_ID = process.env.NEXT_PUBLIC_TEAM_ID ?? '';

const STATUS_COLOR: Record<string, string> = {
  queued: 'bg-gray-100 text-gray-700',
  running: 'bg-blue-100 text-blue-700',
  completed: 'bg-green-100 text-green-700',
  failed: 'bg-red-100 text-red-700',
  cancelled: 'bg-gray-200 text-gray-500',
};

export default function ScansPage() {
  const router = useRouter();
  const qc = useQueryClient();
  const [showForm, setShowForm] = useState(false);
  const [selectedTarget, setSelectedTarget] = useState('');
  const [selectedTier, setSelectedTier] = useState('quick');

  const { data: targets = [] } = useQuery<ScanTarget[]>({
    queryKey: ['portal-scanner-targets-approved', TEAM_ID],
    queryFn: () =>
      fetch(`${ADMIN_API}/scanner/targets?team_id=${TEAM_ID}&status=approved`).then(r => r.json()),
  });

  const { data: jobs = [] } = useQuery<ScanJob[]>({
    queryKey: ['portal-scanner-jobs'],
    queryFn: () => fetch(`${SCANNER_API}/jobs`).then(r => r.json()),
    refetchInterval: 3_000,
  });

  const submit = useMutation({
    mutationFn: () =>
      fetch(`${SCANNER_API}/jobs`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ target_id: selectedTarget, tier: selectedTier }),
      }).then(r => r.json()),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['portal-scanner-jobs'] });
      setShowForm(false);
    },
  });

  return (
    <div className="p-6">
      <div className="flex items-center justify-between mb-4">
        <h1 className="text-2xl font-semibold">Security — Scans</h1>
        <button
          onClick={() => setShowForm(!showForm)}
          className="px-4 py-2 bg-blue-600 text-white rounded text-sm"
        >
          + Run scan
        </button>
      </div>

      {showForm && (
        <div className="border rounded p-4 mb-4 bg-gray-50">
          <h2 className="font-medium mb-3">New scan</h2>
          <div className="flex gap-3 items-end">
            <div>
              <label className="block text-xs text-gray-500 mb-1">Target</label>
              <select
                value={selectedTarget}
                onChange={e => setSelectedTarget(e.target.value)}
                className="border rounded px-3 py-2 text-sm"
              >
                <option value="">Select target…</option>
                {targets.map(t => (
                  <option key={t.id} value={t.id}>{t.label}</option>
                ))}
              </select>
            </div>
            <div>
              <label className="block text-xs text-gray-500 mb-1">Tier</label>
              <select
                value={selectedTier}
                onChange={e => setSelectedTier(e.target.value)}
                className="border rounded px-3 py-2 text-sm"
              >
                <option value="quick">Quick (~5 min)</option>
                <option value="standard">Standard (~15 min)</option>
                <option value="deep">Deep (~45 min)</option>
              </select>
            </div>
            <button
              onClick={() => submit.mutate()}
              disabled={!selectedTarget}
              className="px-4 py-2 bg-blue-600 text-white rounded text-sm disabled:opacity-50"
            >
              Start scan
            </button>
            <button onClick={() => setShowForm(false)} className="px-4 py-2 bg-gray-200 rounded text-sm">
              Cancel
            </button>
          </div>
        </div>
      )}

      <div className="grid gap-3">
        {jobs.map(j => (
          <div
            key={j.id}
            onClick={() => j.status === 'completed' && router.push(`/portal/security/scans/${j.id}`)}
            className={`border rounded p-4 flex items-center justify-between ${j.status === 'completed' ? 'cursor-pointer hover:bg-gray-50' : ''}`}
          >
            <div>
              <div className="font-mono text-sm text-gray-600">{j.id.slice(0, 8)}…</div>
              <div className="text-xs text-gray-400 mt-0.5">
                {j.tier} · {new Date(j.queued_at).toLocaleString()}
              </div>
            </div>
            <span className={`px-2 py-0.5 rounded text-xs font-medium ${STATUS_COLOR[j.status] ?? 'bg-gray-100'}`}>
              {j.status}{j.partial_results ? ' (partial)' : ''}
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}
