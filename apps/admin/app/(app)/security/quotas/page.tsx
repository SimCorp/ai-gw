'use client';

import React, { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { getAdminToken } from '../../../../lib/adminAuth';

const ADMIN_API = process.env.NEXT_PUBLIC_ADMIN_API ?? 'http://localhost:8005';

function authHeaders(json = false): HeadersInit {
  const token = getAdminToken();
  const h: Record<string, string> = {};
  if (token) h.Authorization = `Bearer ${token}`;
  if (json) h['Content-Type'] = 'application/json';
  return h;
}

interface TeamQuota {
  id: string;
  name: string;
  scanner_quota: {
    daily_limit: number;
    allow_external_targets: boolean;
    max_tier: 'quick' | 'standard' | 'deep';
  };
}

export default function QuotasPage() {
  const qc = useQueryClient();
  const [killSwitchPending, setKillSwitchPending] = useState(false);

  const { data: teams = [] } = useQuery<TeamQuota[]>({
    queryKey: ['admin-scanner-quotas'],
    queryFn: () => fetch(`${ADMIN_API}/scanner/quotas`, { headers: authHeaders() }).then(r => r.json()),
  });

  const updateQuota = useMutation({
    mutationFn: ({ teamId, patch }: { teamId: string; patch: Partial<TeamQuota['scanner_quota']> }) =>
      fetch(`${ADMIN_API}/scanner/quotas/${teamId}`, {
        method: 'PATCH',
        headers: authHeaders(true),
        body: JSON.stringify(patch),
      }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['admin-scanner-quotas'] }),
  });

  const toggleKillSwitch = async (enable: boolean) => {
    setKillSwitchPending(true);
    await fetch(`${ADMIN_API}/scanner/kill-switch?enabled=${enable}`, { method: 'POST', headers: authHeaders() });
    setKillSwitchPending(false);
  };

  return (
    <div className="p-6">
      <div className="flex items-center justify-between mb-6">
        <h1 className="text-2xl font-semibold">Scanner — Team Quotas</h1>
        <div className="flex items-center gap-3">
          <span className="text-sm text-gray-600">Global kill switch:</span>
          <button
            disabled={killSwitchPending}
            onClick={() => toggleKillSwitch(true)}
            className="px-3 py-1 bg-red-600 text-white rounded text-sm disabled:opacity-50"
          >
            Disable scanning
          </button>
          <button
            disabled={killSwitchPending}
            onClick={() => toggleKillSwitch(false)}
            className="px-3 py-1 bg-green-600 text-white rounded text-sm disabled:opacity-50"
          >
            Enable scanning
          </button>
        </div>
      </div>
      <table className="w-full text-sm border-collapse">
        <thead>
          <tr className="text-left bg-gray-50">
            <th className="p-3 border">Team</th>
            <th className="p-3 border">Daily limit</th>
            <th className="p-3 border">Max tier</th>
            <th className="p-3 border">External targets</th>
          </tr>
        </thead>
        <tbody>
          {teams.map(t => (
            <tr key={t.id} className="border-b hover:bg-gray-50">
              <td className="p-3 border font-medium">{t.name}</td>
              <td className="p-3 border">
                <input
                  type="number"
                  min={1}
                  max={50}
                  defaultValue={t.scanner_quota.daily_limit}
                  className="w-16 border rounded px-2 py-1 text-sm"
                  onBlur={e => updateQuota.mutate({
                    teamId: t.id,
                    patch: { daily_limit: parseInt(e.target.value, 10) },
                  })}
                />
              </td>
              <td className="p-3 border">
                <select
                  defaultValue={t.scanner_quota.max_tier}
                  className="border rounded px-2 py-1 text-sm"
                  onChange={e => updateQuota.mutate({
                    teamId: t.id,
                    patch: { max_tier: e.target.value as 'quick' | 'standard' | 'deep' },
                  })}
                >
                  <option value="quick">quick</option>
                  <option value="standard">standard</option>
                  <option value="deep">deep</option>
                </select>
              </td>
              <td className="p-3 border">
                <input
                  type="checkbox"
                  defaultChecked={t.scanner_quota.allow_external_targets}
                  onChange={e => updateQuota.mutate({
                    teamId: t.id,
                    patch: { allow_external_targets: e.target.checked },
                  })}
                />
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
