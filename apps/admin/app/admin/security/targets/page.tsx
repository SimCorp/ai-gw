'use client';

import React, { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';

const ADMIN_API = process.env.NEXT_PUBLIC_ADMIN_API ?? 'http://localhost:8005';
const ALL_SCAN_TYPES = ['ai', 'api', 'network'];

interface ScanTarget {
  id: string;
  team_id: string;
  url: string;
  label: string;
  status: 'pending_approval' | 'approved' | 'revoked';
  allowed_scan_types: string[];
  openapi_spec_url: string | null;
  created_at: string;
  notes: string | null;
}

export default function TargetsPage() {
  const qc = useQueryClient();
  const [selectedTypes, setSelectedTypes] = useState<Record<string, string[]>>({});
  const [filter, setFilter] = useState<'pending_approval' | 'approved' | 'revoked' | ''>('pending_approval');

  const { data: targets = [], isLoading } = useQuery<ScanTarget[]>({
    queryKey: ['admin-scanner-targets', filter],
    queryFn: () =>
      fetch(`${ADMIN_API}/scanner/targets${filter ? `?status=${filter}` : ''}`).then(r => r.json()),
    refetchInterval: 10_000,
  });

  const approve = useMutation({
    mutationFn: ({ id, types }: { id: string; types: string[] }) =>
      fetch(`${ADMIN_API}/scanner/targets/${id}/approve`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ allowed_scan_types: types }),
      }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['admin-scanner-targets'] }),
  });

  const revoke = useMutation({
    mutationFn: (id: string) =>
      fetch(`${ADMIN_API}/scanner/targets/${id}/revoke`, { method: 'POST' }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['admin-scanner-targets'] }),
  });

  const getTypes = (id: string, defaults: string[]) => selectedTypes[id] ?? defaults;

  const toggleType = (id: string, defaults: string[], type: string) => {
    const current = getTypes(id, defaults);
    setSelectedTypes(prev => ({
      ...prev,
      [id]: current.includes(type) ? current.filter(t => t !== type) : [...current, type],
    }));
  };

  return (
    <div className="p-6">
      <h1 className="text-2xl font-semibold mb-4">Scanner — Targets</h1>
      <div className="flex gap-2 mb-4">
        {(['pending_approval', 'approved', 'revoked', ''] as const).map(s => (
          <button
            key={s || 'all'}
            onClick={() => setFilter(s)}
            className={`px-3 py-1 rounded text-sm ${filter === s ? 'bg-blue-600 text-white' : 'bg-gray-100 text-gray-700'}`}
          >
            {s || 'All'}
          </button>
        ))}
      </div>
      {isLoading && <p className="text-gray-500">Loading...</p>}
      <table className="w-full text-sm border-collapse">
        <thead>
          <tr className="text-left bg-gray-50">
            <th className="p-3 border">Label / URL</th>
            <th className="p-3 border">Team</th>
            <th className="p-3 border">Status</th>
            <th className="p-3 border">Scan Types</th>
            <th className="p-3 border">Actions</th>
          </tr>
        </thead>
        <tbody>
          {targets.map(t => (
            <tr key={t.id} className="border-b hover:bg-gray-50">
              <td className="p-3 border">
                <div className="font-medium">{t.label}</div>
                <div className="text-gray-500 truncate max-w-xs">{t.url}</div>
              </td>
              <td className="p-3 border text-gray-600 font-mono text-xs">{t.team_id}</td>
              <td className="p-3 border">
                <span className={`px-2 py-0.5 rounded text-xs font-medium ${
                  t.status === 'approved' ? 'bg-green-100 text-green-800' :
                  t.status === 'pending_approval' ? 'bg-yellow-100 text-yellow-800' :
                  'bg-red-100 text-red-800'
                }`}>
                  {t.status}
                </span>
              </td>
              <td className="p-3 border">
                <div className="flex gap-2">
                  {ALL_SCAN_TYPES.map(type => (
                    <label key={type} className="flex items-center gap-1 text-xs">
                      <input
                        type="checkbox"
                        checked={getTypes(t.id, t.allowed_scan_types).includes(type)}
                        onChange={() => toggleType(t.id, t.allowed_scan_types, type)}
                      />
                      {type}
                    </label>
                  ))}
                </div>
              </td>
              <td className="p-3 border">
                <div className="flex gap-2">
                  {t.status !== 'approved' && (
                    <button
                      onClick={() => approve.mutate({ id: t.id, types: getTypes(t.id, t.allowed_scan_types) })}
                      className="px-2 py-1 bg-green-600 text-white rounded text-xs"
                    >
                      Approve
                    </button>
                  )}
                  {t.status === 'approved' && (
                    <button
                      onClick={() => revoke.mutate(t.id)}
                      className="px-2 py-1 bg-red-600 text-white rounded text-xs"
                    >
                      Revoke
                    </button>
                  )}
                </div>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
