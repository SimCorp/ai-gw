"use client";

import Link from "next/link";
import { useState } from "react";
import { MOCK_MODELS } from "../_lib/mock-data";

const FILTER_TABS = ["All", "Chat", "Embeddings", "Vision", "Code"] as const;

export default function ModelsPage() {
  const [activeFilter, setActiveFilter] = useState("All");

  const filtered = MOCK_MODELS.filter((m) => {
    if (activeFilter === "All") return true;
    if (activeFilter === "Chat") return m.caps.includes("chat");
    if (activeFilter === "Embeddings") return m.caps.includes("embed");
    if (activeFilter === "Vision") return m.caps.includes("vision");
    if (activeFilter === "Code") return m.caps.includes("tools");
    return true;
  });

  return (
    <main className="pmain">
      <style>{`
        .mgrid { display:grid; grid-template-columns:repeat(2,1fr); gap:14px; }
        .mcard { background:var(--surface); border:1px solid var(--rule); border-radius:var(--radius-3); padding:18px; display:flex; flex-direction:column; gap:10px; transition:border-color 120ms; }
        .mcard:hover { border-color:var(--sc-blue); }
        .mcard__h { display:flex; align-items:flex-start; gap:12px; }
        .mcard__logo { width:36px; height:36px; border-radius:8px; flex-shrink:0; display:grid; place-items:center; color:#fff; font-weight:700; font-size:13px; }
        .mcard__name { font-family:var(--font-mono); font-weight:600; font-size:14px; }
        .mcard__prov { font-size:12px; color:var(--fg-3); }
        .mcard__d { font-size:12.5px; color:var(--fg-2); line-height:1.5; }
        .mcard__row { display:flex; gap:14px; font-size:11.5px; color:var(--fg-2); flex-wrap:wrap; }
        .mcard__row strong { color:var(--fg-1); font-variant-numeric:tabular-nums; }
        .mcard__caps { display:flex; gap:4px; flex-wrap:wrap; }
        .mcard__foot { display:flex; gap:6px; align-items:center; padding-top:10px; border-top:1px solid var(--rule); }
      `}</style>

      <div className="phero">
        <div>
          <h1>Models</h1>
          <p>14 models approved for <strong>agent-platform</strong>. All are OpenAI-compatible — same SDK, same code.</p>
        </div>
        <div className="tabs-pills">
          {FILTER_TABS.map((t) => (
            <button key={t} className={activeFilter === t ? "is-active" : ""} onClick={() => setActiveFilter(t)}>{t}</button>
          ))}
        </div>
      </div>

      <div className="mgrid">
        {filtered.map((m) => (
          <div className="mcard" key={m.id}>
            <div className="mcard__h">
              <div className="mcard__logo" style={{ background: m.logoColor }}>{m.logoText}</div>
              <div style={{ flex: 1 }}>
                <div className="mcard__name">{m.name}</div>
                <div className="mcard__prov">{m.providerShort}</div>
              </div>
              {m.status === "healthy" && (
                <span className="pill pill--good"><span className="dot" />healthy</span>
              )}
              {m.status === "degraded" && (
                <span className="pill pill--bad"><span className="dot" />{m.errorRate ?? "degraded"}</span>
              )}
            </div>
            <div className="mcard__d">{m.description}</div>
            <div className="mcard__caps">
              {m.caps.map((c) => <span className="tag" key={c}>{c}</span>)}
            </div>
            <div className="mcard__row">
              <span><strong>{m.context}</strong> context</span>
              {m.priceIn && <span><strong>{m.priceIn}</strong>/M in</span>}
              {m.priceOut && <span><strong>{m.priceOut}</strong>/M out</span>}
              {m.priceFlat && <span><strong>{m.priceFlat}</strong>/M tokens</span>}
              {m.requiresScope && (
                <span style={{ color: "var(--warn)" }}>requires <strong>{m.requiresScope}</strong> scope</span>
              )}
              {m.note && <span>{m.note}</span>}
            </div>
            <div className="mcard__foot">
              {m.requiresScope ? (
                <>
                  <Link href="/portal/playground" className="btn btn--sm">Try in playground</Link>
                  <button className="btn btn--sm">Request access</button>
                </>
              ) : (
                <>
                  <Link href="/portal/playground" className={`btn btn--sm${m.status === "healthy" ? " btn--primary" : ""}`}>
                    Try in playground
                  </Link>
                  {m.caps.includes("chat") && <button className="btn btn--sm">Code sample</button>}
                </>
              )}
              {m.fallback && (
                <span style={{ marginLeft: "auto", fontSize: 11, color: "var(--fg-3)" }}>
                  fallback → {m.fallback}
                </span>
              )}
              {m.status === "degraded" && (
                <span style={{ marginLeft: "auto", fontSize: 11, color: "var(--bad)" }}>⚠ failover engaged</span>
              )}
            </div>
          </div>
        ))}
      </div>

      <p style={{ marginTop: 18, color: "var(--fg-3)", fontSize: 12.5 }}>
        Need a model that isn&apos;t here?{" "}
        <a href="#" style={{ color: "var(--sc-blue)" }}>Request approval</a> — admins review on Mondays.
      </p>
    </main>
  );
}
