'use client';

import React from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { getAdminToken } from '../../../../lib/adminAuth';

const SCANNER_API = process.env.NEXT_PUBLIC_SCANNER_API ?? 'http://localhost:8011';

function authHeaders(json = false): HeadersInit {
  const token = getAdminToken();
  const h: Record<string, string> = {};
  if (token) h.Authorization = `Bearer ${token}`;
  if (json) h['Content-Type'] = 'application/json';
  return h;
}

interface ScanJob {
  id: string;
  team_id: string;
  target_id: string;
  tier: string;
  status: string;
  trigger: string;
  queued_at: string;
  started_at: string | null;
  finished_at: string | null;
  partial_results: boolean;
}

const STATUS_COLOR: Record<string, string> = {
  queued: 'bg-gray-100 text-gray-700',
  running: 'bg-blue-100 text-blue-700',
  completed: 'bg-green-100 text-green-700',
  failed: 'bg-red-100 text-red-700',
  cancelled: 'bg-gray-200 text-gray-500',
};

function duration(job: ScanJob): string {
  if (!job.started_at) return '—';
  const end = job.finished_at ? new Date(job.finished_at) : new Date();
  const secs = Math.floor((end.getTime() - new Date(job.started_at).getTime()) / 1000);
  return secs < 60 ? `${secs}s` : `${Math.floor(secs / 60)}m ${secs % 60}s`;
}

export default function JobsPage() {
  const qc = useQueryClient();

  const { data: jobs = [], isLoading } = useQuery<ScanJob[]>({
    queryKey: ['admin-scanner-jobs'],
    queryFn: () => fetch(`${SCANNER_API}/jobs?limit=50`, { headers: authHeaders() }).then(r => r.json()),
    refetchInterval: 5_000,
  });

  const cancel = useMutation({
    mutationFn: (id: string) => fetch(`${SCANNER_API}/jobs/${id}`, { method: 'DELETE', headers: authHeaders() }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['admin-scanner-jobs'] }),
  });

  return (
    <div className="p-6">
      <h1 className="text-2xl font-semibold mb-4">Scanner — All Jobs</h1>
      {isLoading && <p className="text-gray-500">Loading...</p>}
      <table className="w-full text-sm border-collapse">
        <thead>
          <tr className="text-left bg-gray-50">
            <th className="p-3 border">Job ID</th>
            <th className="p-3 border">Team</th>
            <th className="p-3 border">Tier</th>
            <th className="p-3 border">Status</th>
            <th className="p-3 border">Trigger</th>
            <th className="p-3 border">Duration</th>
            <th className="p-3 border">Actions</th>
          </tr>
        </thead>
        <tbody>
          {jobs.map(j => (
            <tr key={j.id} className="border-b hover:bg-gray-50">
              <td className="p-3 border font-mono text-xs">{j.id.slice(0, 8)}...</td>
              <td className="p-3 border font-mono text-xs">{j.team_id.slice(0, 8)}...</td>
              <td className="p-3 border">{j.tier}</td>
              <td className="p-3 border">
                <span className={`px-2 py-0.5 rounded text-xs font-medium ${STATUS_COLOR[j.status] ?? 'bg-gray-100'}`}>
                  {j.status}{j.partial_results ? ' (partial)' : ''}
                </span>
              </td>
              <td className="p-3 border text-gray-600">{j.trigger}</td>
              <td className="p-3 border">{duration(j)}</td>
              <td className="p-3 border">
                {['queued', 'running'].includes(j.status) && (
                  <button
                    onClick={() => cancel.mutate(j.id)}
                    className="px-2 py-1 bg-red-600 text-white rounded text-xs"
                  >
                    Cancel
                  </button>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
