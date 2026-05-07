"use client";

import { useState } from "react";
import { MOCK_AGENTS } from "../_lib/mock-data";

const RUN_STEPS = [
  { type: "done",    label: "Plan",                                time: "+0.0s",           body: `"I'll fetch current positions, pull target weights, compute drift, and check constraints before proposing trades."` },
  { type: "done",    label: "tool",  tool: "positions.get",        time: "+0.4s · 218ms",   body: "→ 142 positions, NAV $284.4M · drift max 84 bp on EM-debt sleeve" },
  { type: "done",    label: "tool",  tool: "target_weights.fetch", time: "+0.7s · 92ms",    body: "→ model weights as of 2026-05-06 · 11 sleeves, 142 securities" },
  { type: "done",    label: "tool",  tool: "market_data.quote",    time: "+1.2s · 412ms",   body: "→ 14 securities flagged for rebalance · liquidity OK on all but 2" },
  { type: "running", label: "tool",  tool: "constraints.check",    time: "+1.9s · running", body: "Validating: concentration limits, sector caps, single-issuer 5% rule…" },
  { type: "pending", label: "Compose proposal & post to Slack" },
];

export default function AgentsPage() {
  const [activeAgent, setActiveAgent] = useState(MOCK_AGENTS[0].id);
  const agent = MOCK_AGENTS.find((a) => a.id === activeAgent)!;

  return (
    <main className="pmain">
      <style>{`
        @keyframes pulse { 0%,100% { box-shadow:0 0 0 0 rgba(129,140,248,0.4); } 50% { box-shadow:0 0 0 5px transparent; } }
        .agrid { display:grid; grid-template-columns:1.4fr 1fr; gap:18px; align-items:start; }
        .alist { display:flex; flex-direction:column; gap:12px; }
        .acard { background:var(--surface); border:1px solid var(--rule); border-radius:var(--radius-3); padding:16px 18px; cursor:pointer; transition:border-color 120ms; }
        .acard:hover,.acard.is-active { border-color:var(--sc-blue); box-shadow:0 0 0 3px var(--sc-blue-soft); }
        .acard__h { display:flex; align-items:center; gap:12px; margin-bottom:8px; }
        .acard__name { font-weight:600; font-size:14px; font-family:var(--font-mono); }
        .acard__d { font-size:12.5px; color:var(--fg-2); line-height:1.5; margin-bottom:10px; }
        .acard__row { display:flex; gap:14px; font-size:11.5px; color:var(--fg-3); align-items:center; }
        .acard__row strong { color:var(--fg-1); font-variant-numeric:tabular-nums; }
        .steps { position:relative; padding-left:18px; margin-top:10px; }
        .steps::before { content:""; position:absolute; left:6px; top:4px; bottom:4px; width:1px; background:var(--rule); }
        .step { position:relative; margin-bottom:12px; }
        .step::before { content:""; position:absolute; left:-16px; top:4px; width:9px; height:9px; border-radius:50%; background:var(--surface); border:2px solid var(--good); }
        .step.s-run::before { border-color:var(--sc-blue); background:var(--sc-blue-soft); animation:pulse 1.5s ease-in-out infinite; }
        .step.s-pending::before { border-color:var(--rule-strong); }
        .step__h { display:flex; align-items:center; gap:8px; font-size:12.5px; font-weight:500; }
        .step__t { font-family:var(--font-mono); font-size:11px; color:var(--fg-3); }
        .step__b { background:var(--surface-2); border:1px solid var(--rule); border-radius:6px; padding:8px 11px; font-family:var(--font-mono); font-size:11.5px; color:var(--fg-2); margin-top:5px; line-height:1.5; }
      `}</style>

      <div className="phero">
        <div>
          <h1>Agents</h1>
          <p>Tool-using LLM workflows that you can schedule, observe, and rerun. <strong>3 of yours</strong> · governed by team rate limits.</p>
        </div>
        <div style={{ display: "flex", gap: 8 }}>
          <button className="btn">Browse templates</button>
          <button className="btn btn--primary">+ New agent</button>
        </div>
      </div>

      <div className="agrid">
        <div className="alist">
          {MOCK_AGENTS.map((a) => (
            <div
              key={a.id}
              className={`acard${activeAgent === a.id ? " is-active" : ""}`}
              onClick={() => setActiveAgent(a.id)}
            >
              <div className="acard__h">
                <span style={{
                  width: 8, height: 8, borderRadius: "50%",
                  background: a.status === "running" ? "var(--sc-blue)" : a.status === "scheduled" ? "var(--good)" : "var(--warn)",
                  boxShadow: a.status === "running" ? "0 0 0 3px var(--sc-blue-soft)" : undefined,
                }} />
                <span className="acard__name">{a.name}</span>
                {a.status === "running" && <span className="pill pill--info" style={{ marginLeft: "auto" }}>running</span>}
                {a.status === "scheduled" && <span className="pill" style={{ marginLeft: "auto" }}>scheduled · 06:00 UTC</span>}
                {a.status === "draft" && <span className="pill pill--warn" style={{ marginLeft: "auto" }}>draft</span>}
              </div>
              <div className="acard__d">{a.description}</div>
              <div className="acard__row">
                <span><strong>{a.tools}</strong> tools</span>
                <span><strong>{a.model}</strong></span>
                {a.lastRun && <span>last run <strong>{a.lastRun}</strong></span>}
                {!a.lastRun && <span>never deployed</span>}
                {a.successRate && (
                  <span style={{ marginLeft: "auto", color: "var(--good)" }}>
                    <strong>{a.successRate}</strong>
                  </span>
                )}
              </div>
            </div>
          ))}
        </div>

        {/* Live run detail */}
        <div className="card" style={{ position: "sticky", top: 28 }}>
          <div className="card__head">
            <h3 className="card__title">{agent.name} · run 4218</h3>
            <span className="card__sub">
              {agent.status === "running" ? "started 18 min ago · running" : `status: ${agent.status}`}
            </span>
            <div className="card__actions">
              {agent.status === "running" && <button className="btn btn--sm">Cancel</button>}
              {agent.status !== "running" && <button className="btn btn--sm">Run now</button>}
            </div>
          </div>
          <div className="card__body">
            {agent.status === "running" && (
              <>
                <div style={{ display: "grid", gridTemplateColumns: "repeat(3,1fr)", gap: 10, marginBottom: 14 }}>
                  <div>
                    <div className="muted" style={{ fontSize: 10.5, textTransform: "uppercase", letterSpacing: "0.04em" }}>Trigger</div>
                    <div style={{ fontSize: 13, fontWeight: 500 }}>cron · 14:30 UTC</div>
                  </div>
                  <div>
                    <div className="muted" style={{ fontSize: 10.5, textTransform: "uppercase", letterSpacing: "0.04em" }}>Tokens</div>
                    <div style={{ fontSize: 13, fontWeight: 500, fontVariantNumeric: "tabular-nums" }}>28,410 / 4,288</div>
                  </div>
                  <div>
                    <div className="muted" style={{ fontSize: 10.5, textTransform: "uppercase", letterSpacing: "0.04em" }}>Cost</div>
                    <div style={{ fontSize: 13, fontWeight: 500 }}>$0.68</div>
                  </div>
                </div>

                <div className="steps">
                  {RUN_STEPS.map((step, i) => (
                    <div
                      key={i}
                      className={`step${step.type === "running" ? " s-run" : step.type === "pending" ? " s-pending" : ""}`}
                      style={step.type === "pending" ? { opacity: 0.4 } : undefined}
                    >
                      <div className="step__h">
                        {step.tool ? (
                          <>
                            <span>tool ·</span>
                            <span className="mono">{step.tool}</span>
                          </>
                        ) : (
                          <span>{step.label}</span>
                        )}
                        {step.time && <span className="step__t">{step.time}</span>}
                      </div>
                      {step.body && (
                        <div className="step__b">{step.body}</div>
                      )}
                    </div>
                  ))}
                </div>
              </>
            )}
            {agent.status !== "running" && (
              <div style={{ color: "var(--fg-3)", fontSize: 13, textAlign: "center", padding: "24px 0" }}>
                {agent.status === "draft" ? "Configure this agent to start running." : "No active run. Scheduled runs appear here when executing."}
              </div>
            )}
          </div>
        </div>
      </div>
    </main>
  );
}
