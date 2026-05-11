'use client';

import { useState, useEffect } from 'react';

const BASE = process.env.NEXT_PUBLIC_ADMIN_BASE_URL ?? 'http://localhost:8005';

interface McpServer {
  id: string;
  name: string;
  description: string | null;
  url: string;
  auth_type: 'none' | 'bearer' | 'api_key';
  auth_header: string | null;
  status: 'pending' | 'active' | 'error' | 'disabled';
  enabled: boolean;
  tool_count: number;
  last_ping_at: string | null;
  last_ping_ms: number | null;
  last_error: string | null;
  created_at: string;
}

interface McpTool {
  id: string;
  name: string;
  description: string | null;
  input_schema: Record<string, unknown>;
  enabled: boolean;
}

interface McpDetail {
  server: McpServer;
  tools: McpTool[];
  access: { server_id: string; team_id: string; team_name: string; granted_at: string }[];
}

function SchemaView({ schema }: { schema: Record<string, unknown> }) {
  const [open, setOpen] = useState(false);
  const str = JSON.stringify(schema, null, 2);
  if (!str || str === '{}' || str === 'null') return null;
  return (
    <div style={{ marginTop: 4 }}>
      <button
        style={{
          background: 'none', border: 'none', padding: 0, cursor: 'pointer',
          fontSize: 11.5, color: 'var(--fg-3)', textDecoration: 'underline',
        }}
        onClick={() => setOpen(o => !o)}
      >
        {open ? 'Hide schema ▲' : 'Input schema ▼'}
      </button>
      {open && (
        <pre style={{
          marginTop: 6,
          padding: '10px 12px',
          background: 'var(--surface-soft)',
          borderRadius: 6,
          fontSize: 11.5,
          fontFamily: 'var(--font-mono)',
          lineHeight: 1.5,
          overflowX: 'auto',
          whiteSpace: 'pre-wrap',
          wordBreak: 'break-word',
          color: 'var(--fg-2)',
          margin: 0,
        }}>
          {str}
        </pre>
      )}
    </div>
  );
}

function ServerToolsPanel({ serverId }: { serverId: string }) {
  const [detail, setDetail] = useState<McpDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setLoading(true);
    setError(null);
    fetch(`${BASE}/mcp/servers/${serverId}`)
      .then(r => {
        if (!r.ok) throw new Error(`HTTP ${r.status}`);
        return r.json() as Promise<McpDetail>;
      })
      .then(data => setDetail(data))
      .catch(e => setError(String(e)))
      .finally(() => setLoading(false));
  }, [serverId]);

  if (loading) {
    return (
      <div style={{ padding: '12px 0', color: 'var(--fg-3)', fontSize: 13 }}>
        Loading tools…
      </div>
    );
  }

  if (error) {
    return (
      <div style={{ padding: '12px 0', color: 'var(--bad)', fontSize: 13 }}>
        Failed to load tools: {error}
      </div>
    );
  }

  const tools = (detail?.tools ?? []).filter(t => t.enabled);

  if (tools.length === 0) {
    return (
      <div style={{ padding: '12px 0', color: 'var(--fg-3)', fontSize: 13 }}>
        No enabled tools on this server.
      </div>
    );
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 8, paddingTop: 8 }}>
      {tools.map(tool => (
        <div
          key={tool.id}
          style={{
            padding: '10px 14px',
            background: 'var(--surface-soft)',
            borderRadius: 8,
            border: '1px solid var(--rule)',
          }}
        >
          <div style={{ display: 'flex', alignItems: 'baseline', gap: 8, flexWrap: 'wrap' }}>
            <span className="mono" style={{ fontWeight: 600, fontSize: 13, color: 'var(--fg-1)' }}>
              {tool.name}
            </span>
            {tool.description && (
              <span style={{ fontSize: 12.5, color: 'var(--fg-2)' }}>
                {tool.description}
              </span>
            )}
          </div>
          <SchemaView schema={tool.input_schema} />
        </div>
      ))}
    </div>
  );
}

export default function McpPage() {
  const [servers, setServers] = useState<McpServer[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [expandedId, setExpandedId] = useState<string | null>(null);

  useEffect(() => {
    setLoading(true);
    setError(null);
    fetch(`${BASE}/mcp/servers`)
      .then(r => {
        if (!r.ok) throw new Error(`HTTP ${r.status}`);
        return r.json() as Promise<McpServer[]>;
      })
      .then(data => setServers(Array.isArray(data) ? data : []))
      .catch(e => setError(String(e)))
      .finally(() => setLoading(false));
  }, []);

  const activeServers = servers.filter(s => s.enabled && s.status === 'active');

  return (
    <main className="pmain">
      <div className="phero">
        <div>
          <h1>MCP Servers</h1>
          <p>
            Connect to tools and actions through Model Context Protocol servers.
            {!loading && !error && (
              <> {activeServers.length} server{activeServers.length !== 1 ? 's' : ''} available.</>
            )}
          </p>
        </div>
      </div>

      {error && (
        <div className="card" style={{ borderColor: 'var(--bad)', marginBottom: 16 }}>
          <div className="card__body" style={{ color: 'var(--bad)', fontSize: 13 }}>
            Failed to load MCP servers: {error}
          </div>
        </div>
      )}

      {loading && (
        <div className="card">
          <div className="card__body" style={{ color: 'var(--fg-3)', fontSize: 13, padding: '24px 20px' }}>
            Loading servers…
          </div>
        </div>
      )}

      {!loading && activeServers.length === 0 && !error && (
        <div className="card">
          <div
            className="card__body"
            style={{ textAlign: 'center', padding: '48px 20px', color: 'var(--fg-3)' }}
          >
            <div style={{ fontSize: 13, color: 'var(--fg-2)', marginBottom: 6 }}>
              No MCP servers available
            </div>
            <div style={{ fontSize: 12.5 }}>
              Your team does not have access to any active MCP servers. Contact your admin to get access.
            </div>
          </div>
        </div>
      )}

      <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
        {activeServers.map(server => {
          const isExpanded = expandedId === server.id;
          return (
            <div
              key={server.id}
              className="card"
              style={{
                border: isExpanded ? '1px solid var(--sc-blue, #0A7BD7)' : undefined,
              }}
            >
              <div className="card__head" style={{ alignItems: 'flex-start' }}>
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
                    <span
                      style={{
                        width: 8, height: 8, borderRadius: '50%', flexShrink: 0,
                        background: 'var(--good)',
                        boxShadow: '0 0 0 2px rgba(31,138,91,0.15)',
                      }}
                    />
                    <h3 className="card__title" style={{ margin: 0 }}>{server.name}</h3>
                    <span className="pill" style={{ fontSize: 11, padding: '2px 7px' }}>
                      {server.tool_count} tool{server.tool_count !== 1 ? 's' : ''}
                    </span>
                  </div>
                  <div style={{ marginTop: 4, display: 'flex', gap: 10, flexWrap: 'wrap', alignItems: 'center' }}>
                    <span className="mono" style={{ fontSize: 12, color: 'var(--fg-3)' }}>
                      {server.url}
                    </span>
                    {server.auth_type !== 'none' && (
                      <>
                        <span style={{ color: 'var(--fg-3)', fontSize: 12 }}>·</span>
                        <span style={{ fontSize: 12, color: 'var(--fg-3)' }}>
                          {server.auth_type} auth
                        </span>
                      </>
                    )}
                    {server.description && (
                      <>
                        <span style={{ color: 'var(--fg-3)', fontSize: 12 }}>·</span>
                        <span style={{ fontSize: 12, color: 'var(--fg-2)' }}>
                          {server.description}
                        </span>
                      </>
                    )}
                  </div>
                </div>
                <div className="card__actions">
                  <button
                    className="btn btn--sm"
                    onClick={() => setExpandedId(id => id === server.id ? null : server.id)}
                  >
                    {isExpanded ? '▼ Hide tools' : '▶ Browse tools'}
                  </button>
                </div>
              </div>

              {isExpanded && (
                <div className="card__body">
                  <ServerToolsPanel serverId={server.id} />
                </div>
              )}
            </div>
          );
        })}
      </div>
    </main>
  );
}
