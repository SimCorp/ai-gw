'use client';

import React, { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { apiFetch } from '../../../lib/apiClient';
import { LoadingState, ErrorState } from '../_components/PageStates';

interface Repo {
  name: string;
  github_url: string;
  ref: string;
  status: 'registered' | 'building' | 'ready' | 'failed';
  last_commit: string | null;
  last_built_at: string | null;
  enabled: boolean;
}

interface Build {
  id: string;
  status: 'queued' | 'running' | 'succeeded' | 'failed';
  nodes: number | null;
  edges: number | null;
  error: string | null;
  queued_at: string | null;
  started_at: string | null;
  finished_at: string | null;
}

const STATUS_COLOR: Record<Repo['status'], string> = {
  ready: 'var(--good)',
  building: 'var(--accent)',
  registered: 'var(--fg-3)',
  failed: 'var(--bad)',
};

function StatusPill({ status }: { status: string }) {
  const color = STATUS_COLOR[status as Repo['status']] ?? 'var(--fg-3)';
  return (
    <span style={{ fontSize: 11, fontWeight: 600, color, border: `1px solid ${color}`, borderRadius: 999, padding: '1px 8px' }}>
      {status}
    </span>
  );
}

function fmt(ts: string | null): string {
  return ts ? new Date(ts).toLocaleString() : '—';
}

function QueryBox({ repo, ready }: { repo: string; ready: boolean }) {
  const [q, setQ] = useState('');
  const ask = useMutation({
    mutationFn: (question: string) =>
      apiFetch<{ repo: string; result: string }>(
        `/graphify/query?repo=${encodeURIComponent(repo)}&q=${encodeURIComponent(question)}`,
      ),
  });
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
      <div style={{ display: 'flex', gap: 6 }}>
        <input
          value={q}
          onChange={e => setQ(e.target.value)}
          placeholder={ready ? 'Ask the graph, e.g. "what connects auth to the database?"' : 'Build the graph first…'}
          disabled={!ready || ask.isPending}
          onKeyDown={e => { if (e.key === 'Enter' && q.trim()) ask.mutate(q.trim()); }}
          style={{ flex: 1, padding: '7px 10px', fontSize: 12, background: 'var(--surface-2)', border: '1px solid var(--rule)', borderRadius: 6, color: 'var(--fg-1)', outline: 'none' }}
        />
        <button
          onClick={() => ask.mutate(q.trim())}
          disabled={!ready || !q.trim() || ask.isPending}
          style={{ padding: '7px 14px', fontSize: 12, fontWeight: 600, background: ready && q.trim() ? 'var(--accent)' : 'var(--surface-2)', color: ready && q.trim() ? '#fff' : 'var(--fg-3)', border: '1px solid var(--rule)', borderRadius: 6, cursor: ready && q.trim() ? 'pointer' : 'not-allowed' }}
        >
          {ask.isPending ? 'Querying…' : 'Query'}
        </button>
      </div>
      {ask.isError && <div style={{ fontSize: 12, color: 'var(--bad)' }}>{(ask.error as Error).message}</div>}
      {ask.data && (
        <pre style={{ margin: 0, padding: '10px 12px', background: 'var(--surface-2)', border: '1px solid var(--rule)', borderRadius: 6, fontSize: 11.5, color: 'var(--fg-1)', whiteSpace: 'pre-wrap', maxHeight: 320, overflow: 'auto' }}>
          {ask.data.result}
        </pre>
      )}
    </div>
  );
}

function GraphModal({ repo, onClose }: { repo: string; onClose: () => void }) {
  const { data, isLoading, error } = useQuery<{ html: string }>({
    queryKey: ['graph-html', repo],
    queryFn: () => apiFetch(`/graphify/repos/${encodeURIComponent(repo)}/graph_html`),
  });
  return (
    <div onClick={onClose} style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.6)', display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 100, padding: 24 }}>
      <div onClick={e => e.stopPropagation()} style={{ background: 'var(--surface)', border: '1px solid var(--rule)', borderRadius: 10, width: '90vw', height: '88vh', display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '10px 14px', borderBottom: '1px solid var(--rule)' }}>
          <span style={{ fontSize: 13, fontWeight: 600, color: 'var(--fg-1)' }}>Knowledge graph — {repo}</span>
          <button onClick={onClose} style={{ padding: '3px 10px', fontSize: 12, background: 'var(--surface-2)', border: '1px solid var(--rule)', borderRadius: 6, color: 'var(--fg-2)', cursor: 'pointer' }}>Close</button>
        </div>
        <div style={{ flex: 1, minHeight: 0 }}>
          {isLoading && <div style={{ padding: 24, color: 'var(--fg-3)', fontSize: 13 }}>Loading graph…</div>}
          {error && <div style={{ padding: 24, color: 'var(--bad)', fontSize: 13 }}>{(error as Error).message}</div>}
          {data && (
            <iframe
              title={`graph-${repo}`}
              srcDoc={data.html}
              // allow-scripts only (NOT allow-same-origin): the graph HTML is
              // derived from repo content and runs JS, so keep it in an opaque
              // origin where it cannot read the admin token in localStorage.
              sandbox="allow-scripts"
              style={{ width: '100%', height: '100%', border: 'none', background: '#fff' }}
            />
          )}
        </div>
      </div>
    </div>
  );
}

function RepoRow({ repo, onChanged }: { repo: Repo; onChanged: () => void }) {
  const [expanded, setExpanded] = useState(false);
  const [showReport, setShowReport] = useState(false);
  const [showGraph, setShowGraph] = useState(false);
  const queryClient = useQueryClient();
  const ready = repo.status === 'ready';

  const { data: builds } = useQuery<{ builds: Build[] }>({
    queryKey: ['graph-builds', repo.name],
    queryFn: () => apiFetch(`/graphify/repos/${encodeURIComponent(repo.name)}/builds`),
    enabled: expanded,
    refetchInterval: repo.status === 'building' ? 4000 : false,
  });

  const report = useQuery<{ markdown: string }>({
    queryKey: ['graph-report', repo.name],
    queryFn: () => apiFetch(`/graphify/repos/${encodeURIComponent(repo.name)}/report`),
    enabled: showReport,
  });

  const rebuild = useMutation({
    mutationFn: () => apiFetch(`/graphify/repos/${encodeURIComponent(repo.name)}/rebuild`, { method: 'POST' }),
    onSuccess: onChanged,
  });

  const remove = useMutation({
    mutationFn: () => apiFetch(`/graphify/repos/${encodeURIComponent(repo.name)}`, { method: 'DELETE' }),
    onSuccess: onChanged,
  });

  const latest = builds?.builds?.[0];

  return (
    <div style={{ border: '1px solid var(--rule)', borderRadius: 8, overflow: 'hidden', background: 'var(--surface)' }}>
      <div
        onClick={() => setExpanded(v => !v)}
        style={{ display: 'flex', alignItems: 'center', gap: 12, padding: '12px 16px', cursor: 'pointer' }}
        onMouseEnter={e => (e.currentTarget as HTMLElement).style.background = 'var(--surface-2)'}
        onMouseLeave={e => (e.currentTarget as HTMLElement).style.background = ''}
      >
        <span style={{ fontSize: 10, color: 'var(--fg-3)', transform: expanded ? 'rotate(90deg)' : 'none', display: 'inline-block', transition: 'transform 0.15s', flexShrink: 0 }}>▶</span>
        <div style={{ width: 32, height: 32, borderRadius: 8, background: 'var(--surface-3)', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 16, flexShrink: 0 }}>🕸️</div>
        <div style={{ flex: 1, minWidth: 0 }}>
          <div style={{ fontSize: 13, fontWeight: 600, color: 'var(--fg-1)' }}>{repo.name}</div>
          <div style={{ fontSize: 11, color: 'var(--fg-3)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{repo.github_url}</div>
        </div>
        {ready && (
          <span style={{ fontSize: 11, color: 'var(--fg-3)', flexShrink: 0 }}>built {fmt(repo.last_built_at)}</span>
        )}
        <StatusPill status={repo.status} />
      </div>

      {expanded && (
        <div style={{ borderTop: '1px solid var(--rule)', padding: '14px 16px', display: 'flex', flexDirection: 'column', gap: 12 }}>
          {/* Actions */}
          <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
            <button onClick={() => rebuild.mutate()} disabled={rebuild.isPending || repo.status === 'building'} style={btn()}>
              {repo.status === 'building' ? 'Building…' : rebuild.isPending ? 'Queuing…' : 'Rebuild'}
            </button>
            <button onClick={() => setShowReport(v => !v)} disabled={!ready} style={btn()}>{showReport ? 'Hide report' : 'View report'}</button>
            <button onClick={() => setShowGraph(true)} disabled={!ready} style={btn()}>View graph</button>
            <button
              onClick={() => { if (confirm(`Remove repo "${repo.name}" and its graph artefacts?`)) remove.mutate(); }}
              disabled={remove.isPending}
              style={{ ...btn(), color: 'var(--bad)', marginLeft: 'auto' }}
            >
              Delete
            </button>
          </div>

          {/* Query */}
          <QueryBox repo={repo.name} ready={ready} />

          {/* Latest build status */}
          {latest && (
            <div style={{ fontSize: 11.5, color: 'var(--fg-3)' }}>
              Latest build: <strong style={{ color: 'var(--fg-2)' }}>{latest.status}</strong>
              {latest.nodes != null && ` · ${latest.nodes} nodes / ${latest.edges} edges`}
              {latest.finished_at && ` · ${fmt(latest.finished_at)}`}
              {latest.error && <div style={{ color: 'var(--bad)', marginTop: 4 }}>{latest.error}</div>}
            </div>
          )}

          {/* Report */}
          {showReport && (
            <div>
              {report.isLoading && <div style={{ fontSize: 12, color: 'var(--fg-3)' }}>Loading report…</div>}
              {report.error && <div style={{ fontSize: 12, color: 'var(--bad)' }}>{(report.error as Error).message}</div>}
              {report.data && (
                <pre style={{ margin: 0, padding: '12px 14px', background: 'var(--surface-2)', border: '1px solid var(--rule)', borderRadius: 6, fontSize: 11.5, color: 'var(--fg-1)', whiteSpace: 'pre-wrap', maxHeight: 420, overflow: 'auto' }}>
                  {report.data.markdown}
                </pre>
              )}
            </div>
          )}
        </div>
      )}

      {showGraph && <GraphModal repo={repo.name} onClose={() => { setShowGraph(false); queryClient.removeQueries({ queryKey: ['graph-html', repo.name] }); }} />}
    </div>
  );
}

function btn(): React.CSSProperties {
  return { padding: '5px 12px', fontSize: 12, fontWeight: 600, background: 'var(--surface-2)', border: '1px solid var(--rule)', borderRadius: 6, color: 'var(--fg-2)', cursor: 'pointer' };
}

export default function KnowledgeGraphsPage() {
  const queryClient = useQueryClient();
  const [showCreate, setShowCreate] = useState(false);
  const [name, setName] = useState('');
  const [url, setUrl] = useState('');
  const [ref, setRef] = useState('main');

  const { data, isLoading, error } = useQuery<{ repos: Repo[] }>({
    queryKey: ['graph-repos'],
    queryFn: () => apiFetch('/graphify/repos'),
    // Keep the list fresh while any repo is building.
    refetchInterval: q => ((q.state.data as { repos: Repo[] } | undefined)?.repos?.some(r => r.status === 'building') ? 4000 : false),
  });

  const create = useMutation({
    mutationFn: () =>
      apiFetch('/graphify/repos', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name: name.trim(), github_url: url.trim() || null, ref: ref.trim() || 'main' }),
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['graph-repos'] });
      setName(''); setUrl(''); setRef('main'); setShowCreate(false);
    },
  });

  const refresh = () => queryClient.invalidateQueries({ queryKey: ['graph-repos'] });
  const repos = data?.repos ?? [];

  return (
    <div style={{ maxWidth: 820, margin: '0 auto', padding: '24px 20px' }}>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 20 }}>
        <div>
          <h1 style={{ fontSize: 20, fontWeight: 700, color: 'var(--fg-1)', margin: 0 }}>Knowledge Graphs</h1>
          <p style={{ fontSize: 13, color: 'var(--fg-3)', margin: '4px 0 0' }}>
            Build queryable knowledge graphs of repos so agents can navigate code by concept instead of grepping files.
          </p>
        </div>
        <button onClick={() => setShowCreate(v => !v)} style={{ padding: '8px 14px', fontSize: 12, fontWeight: 600, background: 'var(--accent)', color: '#fff', border: 'none', borderRadius: 6, cursor: 'pointer' }}>
          + Register repo
        </button>
      </div>

      {showCreate && (
        <div style={{ marginBottom: 16, padding: '14px 16px', background: 'var(--surface)', border: '1px solid var(--rule)', borderRadius: 8 }}>
          <div style={{ fontSize: 12, fontWeight: 600, color: 'var(--fg-1)', marginBottom: 8 }}>Register a repo</div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
            <input value={name} onChange={e => setName(e.target.value)} placeholder="Repo name, e.g. ims" autoFocus style={inp()} />
            <input value={url} onChange={e => setUrl(e.target.value)} placeholder="GitHub URL (optional — defaults to the configured org + name)" style={inp()} />
            <div style={{ display: 'flex', gap: 6 }}>
              <input value={ref} onChange={e => setRef(e.target.value)} placeholder="Branch/tag (default: main)" style={{ ...inp(), maxWidth: 200 }} />
              <button
                onClick={() => create.mutate()}
                disabled={!name.trim() || create.isPending}
                style={{ padding: '7px 14px', fontSize: 12, fontWeight: 600, background: name.trim() ? 'var(--accent)' : 'var(--surface-2)', color: name.trim() ? '#fff' : 'var(--fg-3)', border: `1px solid ${name.trim() ? 'var(--accent)' : 'var(--rule)'}`, borderRadius: 6, cursor: name.trim() ? 'pointer' : 'not-allowed' }}
              >
                {create.isPending ? 'Registering…' : 'Register & build'}
              </button>
              <button onClick={() => { setShowCreate(false); }} style={{ padding: '7px 10px', fontSize: 12, background: 'var(--surface-2)', border: '1px solid var(--rule)', borderRadius: 6, color: 'var(--fg-2)', cursor: 'pointer' }}>Cancel</button>
            </div>
          </div>
          {create.isError && <div style={{ marginTop: 6, fontSize: 12, color: 'var(--bad)' }}>{(create.error as Error).message}</div>}
        </div>
      )}

      {isLoading && <LoadingState rows={3} />}
      {error && <ErrorState error={error as Error} />}
      {!isLoading && !error && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
          {repos.length === 0 ? (
            <div style={{ textAlign: 'center', padding: '40px 0', color: 'var(--fg-3)', fontSize: 13 }}>No repos yet. Register one above.</div>
          ) : (
            repos.map(r => <RepoRow key={r.name} repo={r} onChanged={refresh} />)
          )}
        </div>
      )}
    </div>
  );
}

function inp(): React.CSSProperties {
  return { width: '100%', boxSizing: 'border-box', padding: '7px 10px', fontSize: 12, background: 'var(--surface-2)', border: '1px solid var(--rule)', borderRadius: 6, color: 'var(--fg-1)', outline: 'none' };
}
