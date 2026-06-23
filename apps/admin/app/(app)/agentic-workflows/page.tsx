'use client';

import { useQuery } from '@tanstack/react-query';
import type { ColumnDef } from '@tanstack/react-table';
import { PageHead, KpiGrid, KpiCard, DataTable, Pill, EmptyState } from '@aigw/ui';
import { apiFetch } from '../../../lib/apiClient';

interface Run {
  id: number;
  name: string;
  title: string;
  status: string;
  conclusion: string | null;
  event: string;
  branch: string;
  run_number: number;
  created_at: string;
  html_url: string;
}

interface RunsResponse {
  configured: boolean;
  repo: string;
  runs: Run[];
  summary: { total: number; success: number; failure: number; other: number };
  detail?: string;
}

function conclusionPill(run: Run) {
  if (run.status !== 'completed') return <Pill variant="info" dot>{run.status}</Pill>;
  switch (run.conclusion) {
    case 'success':
      return <Pill variant="good" dot>success</Pill>;
    case 'failure':
    case 'timed_out':
      return <Pill variant="bad" dot>{run.conclusion}</Pill>;
    case 'cancelled':
    case 'skipped':
      return <Pill variant="warn" dot>{run.conclusion}</Pill>;
    default:
      return <Pill dot>{run.conclusion ?? 'unknown'}</Pill>;
  }
}

const columns: ColumnDef<Run>[] = [
  {
    accessorKey: 'name',
    header: 'Workflow',
    cell: ({ row }) => (
      <a href={row.original.html_url} target="_blank" rel="noopener noreferrer">
        {row.original.name} <span style={{ color: 'var(--fg-3)' }}>#{row.original.run_number}</span>
      </a>
    ),
  },
  { accessorKey: 'title', header: 'Run', cell: ({ row }) => row.original.title },
  { accessorKey: 'event', header: 'Trigger' },
  { accessorKey: 'branch', header: 'Branch', meta: { mono: true } },
  {
    accessorKey: 'conclusion',
    header: 'Result',
    cell: ({ row }) => conclusionPill(row.original),
  },
  {
    accessorKey: 'created_at',
    header: 'When',
    cell: ({ row }) =>
      row.original.created_at ? new Date(row.original.created_at).toLocaleString() : '—',
  },
];

export default function AgenticWorkflowsPage() {
  const { data, isLoading } = useQuery<RunsResponse>({
    queryKey: ['agentic-workflows/runs'],
    queryFn: () => apiFetch<RunsResponse>('/agentic-workflows/runs?limit=50'),
    refetchInterval: 30_000,
  });

  const runs = data?.runs ?? [];

  return (
    <div className="page">
      <PageHead
        title="Agentic workflows"
        subtitle="Recent GitHub Actions runs of the repository's gh-aw agentic workflows"
      />

      {data && !data.configured && (
        <EmptyState
          title="Not configured"
          description={
            data.detail ??
            'Set a GitHub token (actions:read) on the admin service to enable this view.'
          }
        />
      )}

      {data?.configured && (
        <>
          <KpiGrid>
            <KpiCard label="Recent runs" value={data.summary.total} />
            <KpiCard label="Succeeded" value={data.summary.success} />
            <KpiCard label="Failed" value={data.summary.failure} />
            <KpiCard label="Other" value={data.summary.other} />
          </KpiGrid>

          <DataTable
            columns={columns}
            data={runs}
            getRowId={(r) => String(r.id)}
            emptyState={
              isLoading ? 'Loading…' : (data?.detail ?? 'No agentic-workflow runs yet (or workflows are dormant).')
            }
          />
        </>
      )}
    </div>
  );
}
