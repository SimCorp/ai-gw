'use client';

import React, { useState } from 'react';
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
  critical: 'bg-[var(--bad-soft)] text-[var(--bad)] border-[var(--bad)]',
  high: 'bg-[var(--warn-soft)] text-[var(--cat-orange)] border-[var(--cat-orange)]',
  medium: 'bg-[var(--warn-soft)] text-[var(--warn)] border-[var(--warn)]',
  low: 'bg-[var(--accent-soft)] text-[var(--accent-text)] border-[var(--accent)]',
  info: 'bg-[var(--surface-soft)] text-[var(--fg-3)] border-[var(--rule)]',
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

  const [downloading, setDownloading] = useState(false);
  const [downloadError, setDownloadError] = useState<string | null>(null);

  // The SARIF endpoint requires a Bearer token, so we can't use window.open
  // (it cannot send an Authorization header). Fetch the file as a blob with the
  // auth header, then trigger a client-side download via a temporary object URL.
  const downloadSarif = async () => {
    if (!token || downloading) return;
    setDownloading(true);
    setDownloadError(null);
    try {
      const res = await fetch(`${SCANNER_API}/jobs/${jobId}/results?format=sarif`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (!res.ok) throw new Error(`Download failed (${res.status})`);
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `scan-${jobId}.sarif.json`;
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(url);
    } catch (e) {
      setDownloadError(e instanceof Error ? e.message : 'Download failed');
    } finally {
      setDownloading(false);
    }
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
          disabled={!token || downloading}
          className="px-4 py-2 bg-[var(--fg-1)] text-[var(--fg-inv)] rounded text-sm disabled:opacity-50"
        >
          {downloading ? 'Downloading…' : 'Download SARIF'}
        </button>
      </div>
      {downloadError && (
        <p className="text-sm text-[var(--bad)] mb-2">{downloadError}</p>
      )}

      {isLoading && <p className="text-[var(--fg-3)]">Loading…</p>}

      <div className="flex gap-3 mb-6 flex-wrap">
        {SEVERITY_ORDER.map(sev => counts[sev] > 0 && (
          <span key={sev} className={`px-3 py-1 rounded border text-sm font-medium ${SEVERITY_COLOR[sev]}`}>
            {counts[sev]} {sev}
          </span>
        ))}
        {findings.length === 0 && !isLoading && (
          <span className="text-[var(--good)] bg-[var(--good-soft)] px-3 py-1 rounded border border-[var(--good)] text-sm font-medium">
            No findings
          </span>
        )}
      </div>

      {grouped.map(({ severity, items }) => (
        <div key={severity} className="mb-6">
          <h2 className="font-semibold text-sm uppercase tracking-wide text-[var(--fg-3)] mb-2">
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
