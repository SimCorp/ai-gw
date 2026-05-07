"use client";

import React from "react";
import Link from "next/link";
import { useState } from "react";
import { MOCK_PROMPTS } from "../_lib/mock-data";

const TABS = ["All", "Mine (4)", "My team (9)", "Org-shared (15)", "Starred ★"];

export default function PromptsPage() {
  const [search, setSearch] = useState("");
  const [tab, setTab] = useState(0);

  const filtered = MOCK_PROMPTS.filter((p) =>
    !search || p.title.toLowerCase().includes(search.toLowerCase()) || p.description.toLowerCase().includes(search.toLowerCase())
  );

  return (
    <main className="pmain">
      <style>{`
        .pgrid { display:grid; grid-template-columns:repeat(2,1fr); gap:14px; }
        .pcard { background:var(--surface); border:1px solid var(--rule); border-radius:var(--radius-3); padding:16px 18px; display:flex; flex-direction:column; gap:8px; cursor:pointer; transition:border-color 120ms; }
        .pcard:hover { border-color:var(--sc-blue); }
        .pcard__t { font-weight:600; font-size:14px; }
        .pcard__d { color:var(--fg-2); font-size:12.5px; line-height:1.5; flex:1; }
        .pcard__m { font-size:11px; color:var(--fg-3); display:flex; gap:12px; align-items:center; }
        .pcard__preview { background:var(--surface-2); border:1px solid var(--rule); border-radius:6px; padding:9px 11px; font-family:var(--font-mono); font-size:11.5px; color:var(--fg-2); line-height:1.5; max-height:60px; overflow:hidden; position:relative; }
        .pcard__preview::after { content:""; position:absolute; left:0; right:0; bottom:0; height:24px; background:linear-gradient(to bottom,transparent,var(--surface-2)); }
      `}</style>

      <div className="phero">
        <div>
          <h1>Prompts</h1>
          <p>Vetted starters from across SimCorp · <strong>28 templates</strong> · fork into your playground in one click.</p>
        </div>
        <div style={{ display: "flex", gap: 8 }}>
          <div className="search" style={{ width: 240 }}>
            <svg width="14" height="14" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5">
              <circle cx="7" cy="7" r="4.5"/><path d="M10.5 10.5L14 14"/>
            </svg>
            <input placeholder="Search prompts…" value={search} onChange={(e: React.ChangeEvent<HTMLInputElement>) => setSearch(e.target.value)} />
          </div>
          <button className="btn btn--primary">+ New prompt</button>
        </div>
      </div>

      <div className="tabs-pills" style={{ marginBottom: 18 }}>
        {TABS.map((t, i) => (
          <button key={t} className={tab === i ? "is-active" : ""} onClick={() => setTab(i)}>{t}</button>
        ))}
      </div>

      <div className="pgrid">
        {filtered.map((p) => (
          <div className="pcard" key={p.id}>
            <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
              <span className="pcard__t">{p.title}</span>
              <span className={`pill ${p.versionPill}`}>{p.version}</span>
              <span style={{ marginLeft: "auto", color: "var(--fg-3)", fontSize: 11 }}>
                {p.stars ? `★ ${p.stars}` : p.mine ? "yours" : ""}
              </span>
            </div>
            <div className="pcard__d">{p.description}</div>
            <div className="pcard__preview">{p.preview}</div>
            <div className="pcard__m">
              <span>by <strong style={{ color: "var(--fg-2)" }}>{p.author}</strong></span>
              {p.uses && <><span>·</span><span>{p.uses.toLocaleString()} uses</span></>}
              {p.model && <><span>·</span><span>{p.model}</span></>}
              {p.lastEdited && <><span>·</span><span>last edited {p.lastEdited}</span></>}
              <span style={{ marginLeft: "auto" }}>
                <Link href="/portal/playground" style={{ color: "var(--sc-blue)", fontWeight: 500 }}>Open in playground →</Link>
              </span>
            </div>
          </div>
        ))}
      </div>
    </main>
  );
}
