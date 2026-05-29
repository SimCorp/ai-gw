'use client';

import React from 'react';
import { useQuery } from '@tanstack/react-query';
import { useParams } from 'next/navigation';
import { useAuth } from '../../../_lib/authContext';

const SCANNER_API = process.env.NEXT_PUBLIC_SCANNER_API ?? 'http://localhost:8011';

interface Finding {
  id: string;
  scanner: string;
  severity: 'critical' | 'high' | 'medium' | 'low' | 'info';
  category: string;
  title: string;
  description: string;
  evidence: Record<string, unknown> | null;
  remediation: string | null;
}

interface ResultsResponse {
  total: number;
  findings: Finding[];
}

const SEVERITY_COLOR: Record<string, string> = {
  critical: 'bg-red-100 text-red-900 border-red-300',
  high: 'bg-orange-100 text-orange-900 border-orange-300',
  medium: 'bg-yellow-100 text-yellow-900 border-yellow-300',
  low: 'bg-blue-100 text-blue-900 border-blue-300',
  info: 'bg-gray-100 text-gray-700 border-gray-200',
};

const SEVERITY_ORDER = ['critical', 'high', 'medium', 'low', 'info'];

export default function ResultsPage() {
  const { token } = useAuth();
  const { jobId } = useParams<{ jobId: string }>();

  const { data, isLoading } = useQuery<ResultsResponse>({
    queryKey: ['scanner-results', jobId, token],
    queryFn: () =>
      fetch(`${SCANNER_API}/jobs/${jobId}/results?limit=200`, {
        headers: { Authorization: `Bearer ${token}` },
      }).then(r => r.json()),
    enabled: !!token,
  });

  const findings = data?.findings ?? [];
  const counts = SEVERITY_ORDER.reduce<Record<string, number>>((acc, sev) => ({
    ...acc,
    [sev]: findings.filter(f => f.severity === sev).length,
  }), {});

  const downloadSarif = () => {
    window.open(`${SCANNER_API}/jobs/${jobId}/results?format=sarif`, '_blank');
  };

  const grouped = SEVERITY_ORDER
    .map(sev => ({ severity: sev, items: findings.filter(f => f.severity === sev) }))
    .filter(g => g.items.length > 0);

  return (
    <div className="p-6">
      <div className="flex items-center justify-between mb-4">
        <h1 className="text-2xl font-semibold">Scan Results</h1>
        <button
          onClick={downloadSarif}
          className="px-4 py-2 bg-gray-800 text-white rounded text-sm"
        >
          Download SARIF
        </button>
      </div>

      {isLoading && <p className="text-gray-500">Loading…</p>}

      <div className="flex gap-3 mb-6 flex-wrap">
        {SEVERITY_ORDER.map(sev => counts[sev] > 0 && (
          <span key={sev} className={`px-3 py-1 rounded border text-sm font-medium ${SEVERITY_COLOR[sev]}`}>
            {counts[sev]} {sev}
          </span>
        ))}
        {findings.length === 0 && !isLoading && (
          <span className="text-green-700 bg-green-50 px-3 py-1 rounded border border-green-200 text-sm font-medium">
            No findings
          </span>
        )}
      </div>

      {grouped.map(({ severity, items }) => (
        <div key={severity} className="mb-6">
          <h2 className="font-semibold text-sm uppercase tracking-wide text-gray-500 mb-2">
            {severity} ({items.length})
          </h2>
          <div className="grid gap-3">
            {items.map(f => (
              <div key={f.id} className={`border rounded p-4 ${SEVERITY_COLOR[f.severity]}`}>
                <div className="font-medium">{f.title}</div>
                <div className="text-xs opacity-70 mt-0.5">{f.scanner} · {f.category}</div>
                <p className="mt-2 text-sm">{f.description}</p>
                {f.remediation && (
                  <p className="mt-2 text-sm opacity-80">
                    <span className="font-medium">Remediation:</span> {f.remediation}
                  </p>
                )}
              </div>
            ))}
          </div>
        </div>
      ))}
    </div>
  );
}
