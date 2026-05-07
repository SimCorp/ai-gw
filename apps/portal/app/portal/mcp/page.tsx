"use client";

import { useState } from "react";
import { MOCK_MCP } from "../_lib/mock-data";

export default function McpPage() {
  const [activeId, setActiveId] = useState(MOCK_MCP[0].id);
  const active = MOCK_MCP.find((s) => s.id === activeId)!;

  return (
    <main className="pmain">
      <style>{`
        .mcp-grid { display:grid; grid-template-columns:1.3fr 1fr; gap:18px; align-items:start; }
        .mcp-list { display:flex; flex-direction:column; gap:12px; }
        .mcp-card { background:var(--surface); border:1px solid var(--rule); border-radius:var(--radius-3); padding:16px 18px; cursor:pointer; transition:border-color 100ms,box-shadow 100ms; }
        .mcp-card:hover,.mcp-card.is-active { border-color:rgba(129,140,248,0.5); box-shadow:0 0 0 3px rgba(129,140,248,0.12); }
        .mcp-h { display:flex; align-items:center; gap:12px; margin-bottom:8px; }
        .mcp-mark { width:36px; height:36px; border-radius:9px; display:grid; place-items:center; font-family:var(--font-mono); font-weight:700; font-size:14px; flex-shrink:0; }
        .mcp-name { font-weight:600; font-size:14px; font-family:var(--font-mono); }
        .mcp-d { font-size:12.5px; color:var(--fg-2); line-height:1.5; margin-bottom:10px; }
        .mcp-row { display:flex; gap:14px; font-size:11.5px; color:var(--fg-3); align-items:center; flex-wrap:wrap; }
        .mcp-row strong { color:var(--fg-1); font-variant-numeric:tabular-nums; }
        .tool-row { display:flex; align-items:flex-start; gap:10px; padding:10px 12px; border:1px solid var(--rule); border-radius:8px; }
        .tool-row+.tool-row { margin-top:8px; }
        .tool-name { font-family:var(--font-mono); font-size:12.5px; font-weight:600; color:var(--fg-1); }
        .tool-args { font-family:var(--font-mono); font-size:11px; color:var(--fg-3); margin-top:3px; }
        .tool-d { font-size:11.5px; color:var(--fg-2); margin-top:4px; line-height:1.45; }
        .tool-cap { display:inline-flex; align-items:center; gap:4px; font-size:10.5px; padding:1px 6px; border-radius:4px; background:rgba(129,140,248,0.14); color:#C7D2FE; font-family:var(--font-mono); }
        .kv { display:grid; grid-template-columns:90px 1fr; gap:6px 12px; font-size:12.5px; }
        .kv .k { color:var(--fg-3); }
        .kv .v { color:var(--fg-1); font-family:var(--font-mono); font-size:12px; }
      `}</style>

      <div className="phero">
        <div>
          <h1>MCP servers</h1>
          <p>Model Context Protocol servers expose tools your agents can call. <strong>14 servers</strong> · 11 internal, 3 vendored.</p>
        </div>
        <div style={{ display: "flex", gap: 8 }}>
          <button className="btn">Browse registry</button>
          <button className="btn btn--primary">+ Connect server</button>
        </div>
      </div>

      <div className="stat-strip">
        <div className="s"><div className="l">Connected servers</div><div className="v">14</div><div className="d">11 internal · 3 vendored</div></div>
        <div className="s"><div className="l">Total tools</div><div className="v">87</div><div className="d">52 read · 35 write</div></div>
        <div className="s"><div className="l">Calls · 24h</div><div className="v">12,408</div><div className="d">+8% vs prev</div></div>
        <div className="s"><div className="l">P95 tool latency</div><div className="v">142 ms</div><div className="d">target &lt; 200 ms</div></div>
      </div>

      <div className="mcp-grid">
        <div className="mcp-list">
          {MOCK_MCP.map((server) => (
            <div
              key={server.id}
              className={`mcp-card${activeId === server.id ? " is-active" : ""}`}
              onClick={() => setActiveId(server.id)}
            >
              <div className="mcp-h">
                <div
                  className="mcp-mark"
                  style={{ background: server.markBg, color: server.markText, boxShadow: "0 6px 18px rgba(192,132,252,0.3)" }}
                >
                  {server.logoLetters}
                </div>
                <div style={{ flex: 1 }}>
                  <div className="mcp-name">{server.name}</div>
                  <div style={{ fontSize: 11.5, color: "var(--fg-3)" }}>
                    {server.type} · {server.version} · maintained by {server.maintainer}
                  </div>
                </div>
                {server.status === "healthy" && (
                  <span className="pill pill--good"><span className="dot" />healthy</span>
                )}
                {server.status === "degraded" && (
                  <span className="pill pill--warn"><span className="dot" />degraded</span>
                )}
                {server.status === "auth failing" && (
                  <span className="pill pill--bad"><span className="dot" />auth failing</span>
                )}
              </div>
              <div className="mcp-d">{server.description}</div>
              <div className="mcp-row">
                <span><strong>{server.tools}</strong> tools</span>
                <span><strong>{server.calls24h.toLocaleString()}</strong> calls/24h</span>
                {server.status !== "auth failing" ? (
                  <span>
                    <strong style={server.status === "degraded" ? { color: "var(--warn)" } : undefined}>
                      {server.p50}
                    </strong>
                    {server.status === "degraded" ? " ⚠" : ""} p50
                  </span>
                ) : (
                  <span style={{ color: "var(--bad)" }}><strong>{server.p50}</strong></span>
                )}
                <span style={{ marginLeft: "auto" }}>
                  {server.status === "auth failing" ? (
                    <button className="btn btn--sm">Reconnect</button>
                  ) : (
                    <span className="tool-cap">{server.transport}</span>
                  )}
                </span>
              </div>
            </div>
          ))}
        </div>

        {/* Detail pane */}
        <div className="card" style={{ position: "sticky", top: 28 }}>
          <div className="card__head">
            <h3 className="card__title">{active.name}</h3>
            <span className="card__sub">{active.version} · {active.tools} tools</span>
            <div className="card__actions">
              <button className="btn btn--sm">Logs</button>
              <button className="btn btn--sm">Restart</button>
            </div>
          </div>
          <div className="card__body">
            {active.endpoint && (
              <div className="kv" style={{ marginBottom: 14 }}>
                <div className="k">Endpoint</div><div className="v">{active.endpoint}</div>
                {active.image && <><div className="k">Image</div><div className="v">{active.image}</div></>}
                {active.auth && <><div className="k">Auth</div><div className="v">{active.auth}</div></>}
                {active.scopes && <><div className="k">Scopes</div><div className="v">{active.scopes}</div></>}
                {active.owners && <><div className="k">Owners</div><div className="v" style={{ fontFamily: "var(--font-sans)" }}>{active.owners}</div></>}
              </div>
            )}

            <div className="muted" style={{ fontSize: 10.5, textTransform: "uppercase", letterSpacing: "0.06em", fontWeight: 600, marginBottom: 8 }}>
              Tools exposed
            </div>

            {active.toolList ? (
              <>
                {active.toolList.map((tool) => (
                  <div className="tool-row" key={tool.name}>
                    <div style={{ flex: 1 }}>
                      <div className="tool-name">{tool.name}</div>
                      <div className="tool-args">{tool.args}</div>
                      <div className="tool-d">{tool.description}</div>
                    </div>
                    <span className="tool-cap">{tool.cap}</span>
                  </div>
                ))}
                <div style={{ marginTop: 10, textAlign: "center" }}>
                  <a href="#" style={{ fontSize: 12, color: "var(--sc-link)" }}>View all {active.tools} tools →</a>
                </div>
              </>
            ) : (
              <div style={{ color: "var(--fg-3)", fontSize: 13, textAlign: "center", padding: "16px 0" }}>
                No tool details available.
              </div>
            )}
          </div>
        </div>
      </div>
    </main>
  );
}
