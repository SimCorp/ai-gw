'use client';

import { useState, useEffect, useRef } from 'react';
import { useParams } from 'next/navigation';

const BASE = process.env.NEXT_PUBLIC_ADMIN_BASE_URL ?? 'http://localhost:8005';

interface NodeState {
  node_id: string;
  iteration: number;
  status: string;
  started_at?: string | null;
  finished_at?: string | null;
  outputs?: Record<string, unknown> | null;
  error?: string | null;
}

interface RunState {
  status: string;
  workflow_id: string;
  version: number;
  triggered_by_kind: string;
  started_at?: string | null;
  finished_at?: string | null;
  error?: string | null;
}

const STATUS_COLOR: Record<string, string> = {
  pending:   'var(--fg-3)',
  running:   'var(--blue)',
  succeeded: 'var(--green)',
  failed:    'var(--red, #ef4444)',
  cancelled: 'var(--fg-3)',
};

const STATUS_ICON: Record<string, string> = {
  pending:   '○',
  running:   '◎',
  succeeded: '●',
  failed:    '✕',
  cancelled: '—',
};

function Badge({ status }: { status: string }) {
  return (
    <span style={{
      display: 'inline-flex', alignItems: 'center', gap: 5,
      padding: '2px 8px', borderRadius: 4, fontSize: 11.5, fontWeight: 600,
      color: STATUS_COLOR[status] ?? 'var(--fg-3)',
      border: `1px solid ${STATUS_COLOR[status] ?? 'var(--rule)'}`,
      background: 'transparent',
    }}>
      {STATUS_ICON[status] ?? '?'} {status}
    </span>
  );
}

export default function RunViewerPage() {
  const { runId } = useParams() as { runId: string };

  const [run, setRun] = useState<RunState | null>(null);
  const [nodes, setNodes] = useState<NodeState[]>([]);
  const [logs, setLogs] = useState<Record<string, string[]>>({});
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [live, setLive] = useState(false);
  const esRef = useRef<EventSource | null>(null);

  // Initial fetch
  useEffect(() => {
    if (!runId || runId === 'new') return;
    fetch(`${BASE}/runs/${runId}`)
      .then(r => { if (!r.ok) throw new Error(`HTTP ${r.status}`); return r.json(); })
      .then(d => {
        setRun(d.run);
        setNodes(d.nodes ?? []);
      })
      .catch(e => setError(String(e)))
      .finally(() => setLoading(false));
  }, [runId]);

  // SSE subscription
  useEffect(() => {
    if (!runId || runId === 'new') return;
    const terminal = ['succeeded', 'failed', 'cancelled'];
    if (run && terminal.includes(run.status)) return;

    const es = new EventSource(`${BASE}/runs/${runId}/stream`);
    esRef.current = es;
    setLive(true);

    es.addEventListener('snapshot', (e) => {
      const d = JSON.parse(e.data).payload;
      setRun(prev => prev ? { ...prev, status: d.status } : null);
      setNodes(d.nodes ?? []);
    });

    const handleEvent = (e: MessageEvent) => {
      const env = JSON.parse(e.data);
      const kind: string = env.kind;
      const payload = env.payload;

      if (kind === 'workflow.run.finished') {
        setRun(prev => prev ? { ...prev, status: payload.status, finished_at: payload.finished_at } : null);
        es.close();
        setLive(false);
      }
      if (kind === 'workflow.node.started') {
        setNodes(prev => prev.map(n =>
          n.node_id === payload.node_id ? { ...n, status: 'running', started_at: env.ts } : n
        ));
      }
      if (kind === 'workflow.node.finished') {
        setNodes(prev => prev.map(n =>
          n.node_id === payload.node_id
            ? { ...n, status: payload.status, outputs: payload.outputs, error: payload.error, finished_at: env.ts }
            : n
        ));
      }
      if (kind === 'workflow.node.log') {
        setLogs(prev => ({
          ...prev,
          [payload.node_id]: [...(prev[payload.node_id] ?? []).slice(-49), payload.line],
        }));
      }
    };

    es.onmessage = handleEvent;
    es.onerror = () => { setLive(false); };

    return () => { es.close(); setLive(false); };
  }, [runId, run?.status]);

  if (runId === 'new') {
    return (
      <main className="pmain">
        <div className="phero"><div><h1>Runs</h1><p>Select a run ID to view its status.</p></div></div>
      </main>
    );
  }

  if (loading) return (
    <main className="pmain">
      <div className="phero"><div><h1>Run</h1></div></div>
      <div className="card"><div className="card__body" style={{ padding: '40px 20px', textAlign: 'center', color: 'var(--fg-3)' }}>Loading…</div></div>
    </main>
  );

  if (error) return (
    <main className="pmain">
      <div className="phero"><div><h1>Run</h1></div></div>
      <div className="card" style={{ borderColor: 'var(--red)' }}><div className="card__body" style={{ color: 'var(--red)' }}>{error}</div></div>
    </main>
  );

  return (
    <main className="pmain">
      <div className="phero">
        <div>
          <h1 style={{ fontSize: 18 }}>Run <span style={{ color: 'var(--fg-3)', fontFamily: 'var(--font-mono,monospace)', fontSize: 14 }}>{runId.slice(0, 8)}…</span></h1>
          {run && <p style={{ marginTop: 4, fontSize: 13 }}>Workflow {run.workflow_id.slice(0, 8)} · v{run.version}</p>}
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          {live && <span style={{ fontSize: 12, color: 'var(--blue)' }}>● live</span>}
          {run && <Badge status={run.status} />}
        </div>
      </div>

      {/* Node list */}
      <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
        {nodes.length === 0 && (
          <div className="card"><div className="card__body" style={{ color: 'var(--fg-3)', padding: '20px', textAlign: 'center', fontSize: 13 }}>
            No nodes yet.
          </div></div>
        )}
        {nodes.map(n => (
          <div key={`${n.node_id}-${n.iteration}`} className="card">
            <div className="card__body">
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 8 }}>
                <span style={{ fontWeight: 600, fontSize: 13, fontFamily: 'var(--font-mono,monospace)' }}>{n.node_id}</span>
                <Badge status={n.status} />
              </div>

              {/* Timing */}
              {(n.started_at || n.finished_at) && (
                <div style={{ fontSize: 11.5, color: 'var(--fg-3)', marginBottom: 6 }}>
                  {n.started_at && `Started ${new Date(n.started_at).toLocaleTimeString()}`}
                  {n.started_at && n.finished_at && ' · '}
                  {n.finished_at && `Done ${new Date(n.finished_at).toLocaleTimeString()}`}
                </div>
              )}

              {/* Error */}
              {n.error && (
                <div style={{ fontSize: 12, color: 'var(--red, #ef4444)', background: 'rgba(239,68,68,0.08)', padding: '6px 10px', borderRadius: 5, marginBottom: 6 }}>
                  {n.error}
                </div>
              )}

              {/* Log lines */}
              {(logs[n.node_id] ?? []).length > 0 && (
                <details style={{ marginBottom: 6 }}>
                  <summary style={{ fontSize: 11.5, color: 'var(--fg-3)', cursor: 'pointer' }}>
                    Logs ({logs[n.node_id].length} lines)
                  </summary>
                  <pre style={{
                    margin: '6px 0 0', padding: '8px', background: 'var(--surface-2)',
                    borderRadius: 5, fontSize: 11, lineHeight: 1.5, overflowX: 'auto',
                    maxHeight: 200, overflowY: 'auto',
                  }}>
                    {logs[n.node_id].join('\n')}
                  </pre>
                </details>
              )}

              {/* Outputs */}
              {n.outputs && (
                <details>
                  <summary style={{ fontSize: 11.5, color: 'var(--fg-3)', cursor: 'pointer' }}>Outputs</summary>
                  <pre style={{
                    margin: '6px 0 0', padding: '8px', background: 'var(--surface-2)',
                    borderRadius: 5, fontSize: 11, lineHeight: 1.5, overflowX: 'auto',
                    maxHeight: 200, overflowY: 'auto',
                  }}>
                    {JSON.stringify(n.outputs, null, 2)}
                  </pre>
                </details>
              )}
            </div>
          </div>
        ))}
      </div>

      {/* Run outputs */}
      {run?.status === 'succeeded' && (
        <div className="card" style={{ marginTop: 8, borderColor: 'var(--green)' }}>
          <div className="card__body">
            <div style={{ fontWeight: 600, fontSize: 13, color: 'var(--green)', marginBottom: 6 }}>Run completed</div>
            <div style={{ fontSize: 11.5, color: 'var(--fg-3)' }}>
              {run.started_at && run.finished_at &&
                `Duration: ${((new Date(run.finished_at).getTime() - new Date(run.started_at).getTime()) / 1000).toFixed(1)}s`}
            </div>
          </div>
        </div>
      )}
    </main>
  );
}
