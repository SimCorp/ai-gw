'use client';

import React, { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';

const ADMIN_API = process.env.NEXT_PUBLIC_ADMIN_API ?? 'http://localhost:8005';

interface ScanTarget {
  id: string;
  url: string;
  label: string;
  status: 'pending_approval' | 'approved' | 'revoked';
  allowed_scan_types: string[];
  openapi_spec_url: string | null;
  created_at: string;
}

interface RegisterForm {
  url: string;
  label: string;
  openapi_spec_url: string;
  scan_types: string[];
}

export default function TargetsPage() {
  const qc = useQueryClient();
  const [showForm, setShowForm] = useState(false);
  const [form, setForm] = useState<RegisterForm>({
    url: '',
    label: '',
    openapi_spec_url: '',
    scan_types: ['ai', 'api', 'network'],
  });

  const TEAM_ID = process.env.NEXT_PUBLIC_TEAM_ID ?? '';
  const USER_ID = process.env.NEXT_PUBLIC_USER_ID ?? '';

  const { data: targets = [] } = useQuery<ScanTarget[]>({
    queryKey: ['portal-scanner-targets', TEAM_ID],
    queryFn: () =>
      fetch(`${ADMIN_API}/scanner/targets?team_id=${TEAM_ID}`).then(r => r.json()),
    refetchInterval: 15_000,
  });

  const register = useMutation({
    mutationFn: (body: RegisterForm & { team_id: string; created_by: string }) =>
      fetch(`${ADMIN_API}/scanner/targets`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          url: body.url,
          label: body.label,
          openapi_spec_url: body.openapi_spec_url || null,
          requested_scan_types: body.scan_types,
          team_id: body.team_id,
          created_by: body.created_by,
        }),
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['portal-scanner-targets'] });
      setShowForm(false);
      setForm({ url: '', label: '', openapi_spec_url: '', scan_types: ['ai', 'api', 'network'] });
    },
  });

  const STATUS_COLOR: Record<string, string> = {
    pending_approval: 'bg-yellow-100 text-yellow-800',
    approved: 'bg-green-100 text-green-800',
    revoked: 'bg-red-100 text-red-800',
  };

  return (
    <div className="p-6">
      <div className="flex items-center justify-between mb-4">
        <h1 className="text-2xl font-semibold">Security — Targets</h1>
        <button
          onClick={() => setShowForm(!showForm)}
          className="px-4 py-2 bg-blue-600 text-white rounded text-sm"
        >
          + Register target
        </button>
      </div>

      {showForm && (
        <div className="border rounded p-4 mb-4 bg-gray-50">
          <h2 className="font-medium mb-3">Register new target</h2>
          <div className="grid grid-cols-2 gap-3">
            <input
              placeholder="Label (e.g. My AI Service)"
              value={form.label}
              onChange={e => setForm(f => ({ ...f, label: e.target.value }))}
              className="border rounded px-3 py-2 text-sm"
            />
            <input
              placeholder="URL (e.g. https://myapp.simcorp.internal)"
              value={form.url}
              onChange={e => setForm(f => ({ ...f, url: e.target.value }))}
              className="border rounded px-3 py-2 text-sm"
            />
            <input
              placeholder="OpenAPI spec URL (optional — enables deep API scan)"
              value={form.openapi_spec_url}
              onChange={e => setForm(f => ({ ...f, openapi_spec_url: e.target.value }))}
              className="border rounded px-3 py-2 text-sm col-span-2"
            />
            <div className="col-span-2 flex gap-3">
              {['ai', 'api', 'network'].map(type => (
                <label key={type} className="flex items-center gap-1 text-sm">
                  <input
                    type="checkbox"
                    checked={form.scan_types.includes(type)}
                    onChange={e => setForm(f => ({
                      ...f,
                      scan_types: e.target.checked
                        ? [...f.scan_types, type]
                        : f.scan_types.filter(t => t !== type),
                    }))}
                  />
                  {type} scanning
                </label>
              ))}
            </div>
          </div>
          <div className="flex gap-2 mt-3">
            <button
              onClick={() => register.mutate({ ...form, team_id: TEAM_ID, created_by: USER_ID })}
              disabled={!form.url || !form.label}
              className="px-4 py-2 bg-blue-600 text-white rounded text-sm disabled:opacity-50"
            >
              Submit for approval
            </button>
            <button onClick={() => setShowForm(false)} className="px-4 py-2 bg-gray-200 rounded text-sm">
              Cancel
            </button>
          </div>
        </div>
      )}

      <div className="grid gap-3">
        {targets.map(t => (
          <div key={t.id} className="border rounded p-4 flex items-start justify-between">
            <div>
              <div className="font-medium">{t.label}</div>
              <div className="text-gray-500 text-sm">{t.url}</div>
              <div className="text-gray-400 text-xs mt-1">
                Types: {t.allowed_scan_types.join(', ')}
              </div>
            </div>
            <span className={`px-2 py-0.5 rounded text-xs font-medium ${STATUS_COLOR[t.status] ?? 'bg-gray-100 text-gray-700'}`}>
              {t.status}
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}
