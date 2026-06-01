'use client';

import "@xyflow/react/dist/style.css";

import { useState, useEffect, useCallback, useRef } from 'react';
import { useParams, useRouter } from 'next/navigation';
import {
  ReactFlow,
  Background,
  Controls,
  useNodesState,
  useEdgesState,
  addEdge,
  MiniMap,
  Panel,
  Node,
  Edge,
  Connection,
  NodeProps,
} from '@xyflow/react';

const ADMIN_BASE = process.env.NEXT_PUBLIC_ADMIN_BASE_URL ?? 'http://localhost:8005';

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface AgentDef {
  id: string;
  slug: string;
  name: string;
  category: string;
}

interface NodeData extends Record<string, unknown> {
  agent_slug: string;
  agent_name: string;
  category: string;
  inputs: Record<string, string>;
  loop_enabled: boolean;
  loop_max_iterations: number;
}

// ---------------------------------------------------------------------------
// Custom node
// ---------------------------------------------------------------------------

const CATEGORY_COLORS: Record<string, string> = {
  llm:       'var(--blue)',
  tool:      '#a78bfa',
  transform: '#34d399',
  io:        '#fb923c',
  control:   '#f472b6',
};

function AgentNode({ data, selected }: NodeProps) {
  const d = data as NodeData;
  const color = CATEGORY_COLORS[d.category] ?? 'var(--fg-3)';
  return (
    <div style={{
      background: selected ? 'var(--surface)' : 'var(--bg)',
      border: `1.5px solid ${selected ? color : 'var(--rule)'}`,
      borderRadius: 8,
      padding: '8px 14px',
      minWidth: 140,
      boxShadow: selected ? `0 0 0 2px ${color}33` : '0 2px 8px rgba(0,0,0,0.35)',
      cursor: 'grab',
    }}>
      <div style={{ fontSize: 10, color, fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.05em', marginBottom: 2 }}>
        {d.category}
      </div>
      <div style={{ fontSize: 13, fontWeight: 600, color: 'var(--fg-1)' }}>{d.agent_name}</div>
      <div style={{ fontSize: 10.5, color: 'var(--fg-3)', fontFamily: 'var(--font-mono,monospace)', marginTop: 1 }}>{d.agent_slug}</div>
      {d.loop_enabled && (
        <div style={{ fontSize: 10, color: '#fb923c', marginTop: 3 }}>loop ×{d.loop_max_iterations}</div>
      )}
    </div>
  );
}

const NODE_TYPES = { agent: AgentNode };

// ---------------------------------------------------------------------------
// Right panel — node config
// ---------------------------------------------------------------------------

function NodePanel({
  node,
  onChange,
  onClose,
}: {
  node: Node;
  onChange: (id: string, data: Partial<NodeData>) => void;
  onClose: () => void;
}) {
  const d = node.data as NodeData;
  const [inputs, setInputs] = useState<Array<[string, string]>>(Object.entries(d.inputs));
  const [loopEnabled, setLoopEnabled] = useState(d.loop_enabled);
  const [loopMax, setLoopMax] = useState(d.loop_max_iterations);

  const flush = useCallback((nextInputs: Array<[string, string]>, le: boolean, lm: number) => {
    onChange(node.id, {
      inputs: Object.fromEntries(nextInputs.filter(([k]) => k.trim())),
      loop_enabled: le,
      loop_max_iterations: lm,
    });
  }, [node.id, onChange]);

  const addRow = () => {
    const next: Array<[string, string]> = [...inputs, ['', '']];
    setInputs(next);
  };

  const updateRow = (i: number, key: string, val: string) => {
    const next = inputs.map((r, idx) => idx === i ? [key, val] as [string, string] : r);
    setInputs(next);
    flush(next, loopEnabled, loopMax);
  };

  const removeRow = (i: number) => {
    const next = inputs.filter((_, idx) => idx !== i);
    setInputs(next);
    flush(next, loopEnabled, loopMax);
  };

  const handleLoop = (le: boolean, lm: number) => {
    setLoopEnabled(le);
    setLoopMax(lm);
    flush(inputs, le, lm);
  };

  return (
    <div style={{
      position: 'absolute', top: 0, right: 0, bottom: 0, width: 280,
      background: 'var(--bg)', borderLeft: '1px solid var(--rule)',
      display: 'flex', flexDirection: 'column', zIndex: 10,
    }}>
      <div style={{ padding: '14px 16px 10px', display: 'flex', justifyContent: 'space-between', alignItems: 'center', borderBottom: '1px solid var(--rule)' }}>
        <span style={{ fontWeight: 600, fontSize: 13, color: 'var(--fg-1)' }}>Node config</span>
        <button onClick={onClose} style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--fg-3)', fontSize: 16, lineHeight: 1 }}>×</button>
      </div>
      <div style={{ flex: 1, overflowY: 'auto', padding: '14px 16px' }}>
        <div style={{ fontSize: 11, color: 'var(--fg-3)', marginBottom: 4 }}>Agent slug</div>
        <div style={{ fontSize: 12, fontFamily: 'var(--font-mono,monospace)', color: 'var(--fg-1)', marginBottom: 12 }}>{d.agent_slug}</div>

        <div style={{ fontSize: 11, color: 'var(--fg-3)', marginBottom: 8, fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.05em' }}>Inputs</div>
        {inputs.map(([k, v], i) => (
          <div key={i} style={{ display: 'flex', gap: 4, marginBottom: 6 }}>
            <input
              placeholder="key"
              value={k}
              onChange={e => updateRow(i, e.target.value, v)}
              style={inputStyle}
            />
            <input
              placeholder="value"
              value={v}
              onChange={e => updateRow(i, k, e.target.value)}
              style={{ ...inputStyle, flex: 1.5 }}
            />
            <button onClick={() => removeRow(i)} style={smallBtnStyle}>×</button>
          </div>
        ))}
        <button onClick={addRow} style={addBtnStyle}>+ Add input</button>

        <div style={{ marginTop: 16, fontSize: 11, color: 'var(--fg-3)', fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.05em' }}>Loop</div>
        <label style={{ display: 'flex', alignItems: 'center', gap: 8, marginTop: 8, fontSize: 12, color: 'var(--fg-2)', cursor: 'pointer' }}>
          <input
            type="checkbox"
            checked={loopEnabled}
            onChange={e => handleLoop(e.target.checked, loopMax)}
          />
          Enable loop
        </label>
        {loopEnabled && (
          <div style={{ marginTop: 8 }}>
            <div style={{ fontSize: 11, color: 'var(--fg-3)', marginBottom: 4 }}>Max iterations</div>
            <input
              type="number"
              min={1}
              max={100}
              value={loopMax}
              onChange={e => handleLoop(loopEnabled, Number(e.target.value))}
              style={{ ...inputStyle, width: '100%' }}
            />
          </div>
        )}
      </div>
    </div>
  );
}

const inputStyle: React.CSSProperties = {
  flex: 1, padding: '4px 7px', fontSize: 12,
  background: 'var(--surface)', border: '1px solid var(--rule)',
  borderRadius: 5, color: 'var(--fg-1)', outline: 'none',
};
const smallBtnStyle: React.CSSProperties = {
  padding: '3px 7px', fontSize: 13, background: 'none', border: '1px solid var(--rule)',
  borderRadius: 5, color: 'var(--fg-3)', cursor: 'pointer',
};
const addBtnStyle: React.CSSProperties = {
  marginTop: 2, fontSize: 11, padding: '3px 10px',
  background: 'none', border: '1px solid var(--rule)',
  borderRadius: 5, color: 'var(--fg-3)', cursor: 'pointer',
};

// ---------------------------------------------------------------------------
// Edge condition panel
// ---------------------------------------------------------------------------

function EdgePanel({
  edge,
  onConditionChange,
  onClose,
}: {
  edge: Edge;
  onConditionChange: (id: string, condition: string | null) => void;
  onClose: () => void;
}) {
  const [cond, setCond] = useState<string>((edge.data as { condition?: string })?.condition ?? '');

  return (
    <div style={{
      position: 'absolute', top: 0, right: 0, bottom: 0, width: 280,
      background: 'var(--bg)', borderLeft: '1px solid var(--rule)',
      display: 'flex', flexDirection: 'column', zIndex: 10,
    }}>
      <div style={{ padding: '14px 16px 10px', display: 'flex', justifyContent: 'space-between', alignItems: 'center', borderBottom: '1px solid var(--rule)' }}>
        <span style={{ fontWeight: 600, fontSize: 13, color: 'var(--fg-1)' }}>Edge condition</span>
        <button onClick={onClose} style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--fg-3)', fontSize: 16, lineHeight: 1 }}>×</button>
      </div>
      <div style={{ flex: 1, padding: '14px 16px' }}>
        <div style={{ fontSize: 11, color: 'var(--fg-3)', marginBottom: 4 }}>Condition (JSON path expression)</div>
        <input
          placeholder='e.g. outputs.status == "success"'
          value={cond}
          onChange={e => {
            setCond(e.target.value);
            onConditionChange(edge.id, e.target.value.trim() || null);
          }}
          style={{ ...inputStyle, width: '100%' }}
        />
        <div style={{ fontSize: 10.5, color: 'var(--fg-3)', marginTop: 8 }}>
          Leave empty to always follow this edge.
        </div>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Main designer page
// ---------------------------------------------------------------------------

let nodeCounter = 0;
const nextId = () => `n${++nodeCounter}`;

export default function DesignerPage() {
  const { workflowId } = useParams() as { workflowId: string };
  const router = useRouter();

  const [agents, setAgents] = useState<AgentDef[]>([]);
  const [nodes, setNodes, onNodesChange] = useNodesState<Node>([]);
  const [edges, setEdges, onEdgesChange] = useEdgesState<Edge>([]);
  const [selectedNode, setSelectedNode] = useState<Node | null>(null);
  const [selectedEdge, setSelectedEdge] = useState<Edge | null>(null);
  const [saving, setSaving] = useState(false);
  const [running, setRunning] = useState(false);
  const [saveMsg, setSaveMsg] = useState<string | null>(null);
  const reactFlowWrapper = useRef<HTMLDivElement>(null);

  // Fetch agents palette
  useEffect(() => {
    fetch(`${ADMIN_BASE}/agents`)
      .then(r => r.ok ? r.json() : Promise.reject(`HTTP ${r.status}`))
      .then(d => setAgents(d.agents ?? d ?? []))
      .catch(() => setAgents([]));
  }, []);

  // Load existing workflow DAG
  useEffect(() => {
    if (!workflowId) return;
    // First fetch the workflow list to get latest_version, then fetch that version
    fetch(`${ADMIN_BASE}/workflows`)
      .then(r => r.ok ? r.json() : null)
      .then((d: { workflows?: Array<{ id: string; latest_version: number }> } | null) => {
        const wf = d?.workflows?.find(w => w.id === workflowId);
        if (!wf || wf.latest_version < 1) return null;
        return fetch(`${ADMIN_BASE}/workflows/${workflowId}/versions/${wf.latest_version}`)
          .then(r => r.ok ? r.json() : null);
      })
      .then((data: { dag?: { nodes?: Array<{ id: string; agent_slug: string; inputs: Record<string, string>; loop?: { enabled: boolean; max_iterations: number } }>; edges?: Array<{ from: string; to: string; condition?: string | null }> } } | null) => {
        const dag = data?.dag;
        if (!dag?.nodes?.length) return;
        // Rebuild ReactFlow nodes with auto-layout
        const newNodes: Node[] = dag.nodes.map((n, i) => ({
          id: n.id,
          type: 'agent' as const,
          position: { x: 100 + (i % 4) * 220, y: 100 + Math.floor(i / 4) * 160 },
          data: {
            agent_slug: n.agent_slug,
            agent_name: n.agent_slug,
            category: 'llm',
            inputs: n.inputs ?? {},
            loop_enabled: n.loop?.enabled ?? false,
            loop_max_iterations: n.loop?.max_iterations ?? 10,
          } satisfies NodeData,
        }));
        const newEdges: Edge[] = (dag.edges ?? []).map((e, i) => ({
          id: `e${i}`,
          source: e.from,
          target: e.to,
          data: { condition: e.condition ?? null },
        }));
        setNodes(newNodes);
        setEdges(newEdges);
      })
      .catch(() => {/* start with empty canvas on any error */});
  }, [workflowId, setNodes, setEdges]);

  // Connect handler
  const onConnect = useCallback((params: Connection) => {
    setEdges(eds => addEdge({ ...params, data: { condition: null } }, eds));
  }, [setEdges]);

  // Node selection
  const onNodeClick = useCallback((_: React.MouseEvent, n: Node) => {
    setSelectedEdge(null);
    setSelectedNode(n);
  }, []);

  const onEdgeClick = useCallback((_: React.MouseEvent, e: Edge) => {
    setSelectedNode(null);
    setSelectedEdge(e);
  }, []);

  const onPaneClick = useCallback(() => {
    setSelectedNode(null);
    setSelectedEdge(null);
  }, []);

  // Drag from palette onto canvas
  const onDragOver = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    e.dataTransfer.dropEffect = 'move';
  }, []);

  const onDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    const raw = e.dataTransfer.getData('application/agent-def');
    if (!raw) return;
    const agent: AgentDef = JSON.parse(raw);
    const rect = reactFlowWrapper.current?.getBoundingClientRect();
    if (!rect) return;
    const x = e.clientX - rect.left - 70;
    const y = e.clientY - rect.top - 30;
    const id = nextId();
    const newNode: Node = {
      id,
      type: 'agent',
      position: { x, y },
      data: {
        agent_slug: agent.slug,
        agent_name: agent.name,
        category: agent.category,
        inputs: {},
        loop_enabled: false,
        loop_max_iterations: 10,
      } satisfies NodeData,
    };
    setNodes(ns => [...ns, newNode]);
  }, [setNodes]);

  // Update node data from panel
  const updateNodeData = useCallback((id: string, patch: Partial<NodeData>) => {
    setNodes(ns => ns.map(n => n.id === id ? { ...n, data: { ...n.data, ...patch } } : n));
    setSelectedNode(prev => prev && prev.id === id ? { ...prev, data: { ...prev.data, ...patch } } : prev);
  }, [setNodes]);

  // Update edge condition
  const updateEdgeCondition = useCallback((id: string, condition: string | null) => {
    setEdges(es => es.map(e => e.id === id ? { ...e, data: { ...e.data, condition } } : e));
    setSelectedEdge(prev => prev && prev.id === id ? { ...prev, data: { ...prev.data, condition } } : prev);
  }, [setEdges]);

  // Build DAG JSON
  const buildDag = useCallback(() => {
    const entryNode = nodes.length > 0
      ? (nodes.find(n => !edges.some(e => e.target === n.id)) ?? nodes[0]).id
      : '';
    return {
      entry_node: entryNode,
      nodes: nodes.map(n => {
        const d = n.data as NodeData;
        return {
          id: n.id,
          agent_slug: d.agent_slug,
          inputs: d.inputs,
          loop: { enabled: d.loop_enabled, max_iterations: d.loop_max_iterations },
        };
      }),
      edges: edges.map(e => ({
        from: e.source,
        to: e.target,
        condition: (e.data as { condition?: string | null })?.condition ?? null,
      })),
    };
  }, [nodes, edges]);

  const handleSave = async () => {
    setSaving(true);
    setSaveMsg(null);
    try {
      const dag = buildDag();
      const res = await fetch(`${ADMIN_BASE}/workflows/${workflowId}/versions`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ dag }),
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      setSaveMsg('Saved');
      setTimeout(() => setSaveMsg(null), 2500);
    } catch (err) {
      setSaveMsg(`Error: ${err}`);
    } finally {
      setSaving(false);
    }
  };

  const handleRun = async () => {
    setRunning(true);
    try {
      const res = await fetch(`${ADMIN_BASE}/runs`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ workflow_id: workflowId, inputs: {} }),
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const d = await res.json();
      const runId = d.run_id ?? d.id;
      if (runId) router.push(`/portal/workflows/${workflowId}/runs/${runId}`);
    } catch (err) {
      setSaveMsg(`Run error: ${err}`);
    } finally {
      setRunning(false);
    }
  };

  const panelOpen = !!(selectedNode || selectedEdge);

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100vh', background: 'var(--bg)' }}>
      {/* Top bar */}
      <div style={{
        display: 'flex', alignItems: 'center', gap: 12,
        padding: '0 16px', height: 52, flexShrink: 0,
        borderBottom: '1px solid var(--rule)',
        background: 'var(--bg)',
      }}>
        <button
          onClick={() => router.push(`/portal/workflows`)}
          style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--fg-3)', fontSize: 13, padding: '4px 0' }}
        >
          ← Workflows
        </button>
        <span style={{ flex: 1, fontSize: 14, fontWeight: 600, color: 'var(--fg-1)' }}>Designer</span>
        {saveMsg && <span style={{ fontSize: 12, color: saveMsg.startsWith('Error') ? 'var(--red, #ef4444)' : 'var(--green)' }}>{saveMsg}</span>}
        <button
          onClick={handleSave}
          disabled={saving}
          style={topBtnStyle(false)}
        >
          {saving ? 'Saving…' : 'Save version'}
        </button>
        <button
          onClick={handleRun}
          disabled={running}
          style={topBtnStyle(true)}
        >
          {running ? 'Starting…' : 'Run'}
        </button>
      </div>

      {/* Body */}
      <div style={{ flex: 1, display: 'flex', overflow: 'hidden' }}>
        {/* Palette */}
        <div style={{
          width: 200, flexShrink: 0, borderRight: '1px solid var(--rule)',
          overflowY: 'auto', padding: '12px 10px',
          background: 'var(--bg)',
        }}>
          <div style={{ fontSize: 10.5, fontWeight: 700, color: 'var(--fg-3)', textTransform: 'uppercase', letterSpacing: '0.06em', marginBottom: 8 }}>Agents</div>
          {agents.length === 0 && (
            <div style={{ fontSize: 11.5, color: 'var(--fg-3)' }}>No agents available.</div>
          )}
          {agents.map(a => (
            <div
              key={a.id}
              draggable
              onDragStart={e => {
                e.dataTransfer.setData('application/agent-def', JSON.stringify(a));
                e.dataTransfer.effectAllowed = 'move';
              }}
              style={{
                padding: '8px 10px', marginBottom: 6, borderRadius: 6,
                border: '1px solid var(--rule)', background: 'var(--surface)',
                cursor: 'grab', userSelect: 'none',
              }}
            >
              <div style={{ fontSize: 10, color: CATEGORY_COLORS[a.category] ?? 'var(--fg-3)', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.05em' }}>{a.category}</div>
              <div style={{ fontSize: 12, fontWeight: 600, color: 'var(--fg-1)', marginTop: 1 }}>{a.name}</div>
              <div style={{ fontSize: 10.5, color: 'var(--fg-3)', fontFamily: 'var(--font-mono,monospace)' }}>{a.slug}</div>
            </div>
          ))}
        </div>

        {/* Canvas + right panel */}
        <div style={{ flex: 1, position: 'relative', overflow: 'hidden' }} ref={reactFlowWrapper} onDragOver={onDragOver} onDrop={onDrop}>
          <ReactFlow
            nodes={nodes}
            edges={edges}
            onNodesChange={onNodesChange}
            onEdgesChange={onEdgesChange}
            onConnect={onConnect}
            onNodeClick={onNodeClick}
            onEdgeClick={onEdgeClick}
            onPaneClick={onPaneClick}
            nodeTypes={NODE_TYPES}
            fitView
            style={{ width: '100%', height: '100%' }}
          >
            <Background color="var(--rule)" gap={20} />
            <Controls />
            <MiniMap
              nodeColor={() => 'var(--surface)'}
              style={{ background: 'var(--bg)', border: '1px solid var(--rule)' }}
            />
            {nodes.length === 0 && (
              <Panel position="top-center">
                <div style={{ marginTop: 60, fontSize: 13, color: 'var(--fg-3)', textAlign: 'center', pointerEvents: 'none' }}>
                  Drag agents from the palette to build your workflow
                </div>
              </Panel>
            )}
          </ReactFlow>

          {/* Right panel — node or edge config */}
          {panelOpen && selectedNode && (
            <NodePanel
              node={selectedNode}
              onChange={updateNodeData}
              onClose={() => setSelectedNode(null)}
            />
          )}
          {panelOpen && selectedEdge && (
            <EdgePanel
              edge={selectedEdge}
              onConditionChange={updateEdgeCondition}
              onClose={() => setSelectedEdge(null)}
            />
          )}
        </div>
      </div>
    </div>
  );
}

function topBtnStyle(primary: boolean): React.CSSProperties {
  return {
    padding: '5px 14px', fontSize: 12, borderRadius: 6, cursor: 'pointer',
    fontWeight: 600,
    background: primary ? 'var(--blue)' : 'var(--surface)',
    color: primary ? '#fff' : 'var(--fg-1)',
    border: primary ? 'none' : '1px solid var(--rule)',
  };
}
