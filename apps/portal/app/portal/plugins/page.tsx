"use client";

import { useState } from "react";
import { MOCK_PLUGINS } from "../_lib/mock-data";
import type { Plugin } from "../_lib/types";

const MAIN_TABS = ["Marketplace", "Installed", "Updates", "Built by you"] as const;
const MAIN_COUNTS = [38, 6, 2, 1];
const CATEGORIES = ["All", "Observability", "Routing", "Safety", "Storage", "Eval", "Editor", "CI/CD"];

export default function PluginsPage() {
  const [tab, setTab] = useState(0);
  const [cat, setCat] = useState("All");
  const [plugins, setPlugins] = useState(MOCK_PLUGINS);

  const visible = plugins.filter((p: Plugin) => {
    if (tab === 1 && !p.installed) return false;
    if (cat !== "All" && p.category !== cat) return false;
    return true;
  });

  const handleToggleInstall = (id: string) => {
    setPlugins((prev: Plugin[]) =>
      prev.map((p: Plugin) => p.id === id ? { ...p, installed: !p.installed } : p)
    );
  };

  return (
    <main className="pmain">
      <style>{`
        .tabs-plug { display:flex; gap:18px; border-bottom:1px solid var(--rule); margin:18px 0 16px; }
        .tabs-plug a { padding:10px 0; font-size:13px; color:var(--fg-2); border-bottom:2px solid transparent; font-weight:500; cursor:pointer; }
        .tabs-plug a.is-active { color:var(--fg-1); border-bottom-color:#818CF8; }
        .tabs-plug .count { font-size:11px; color:var(--fg-3); margin-left:4px; font-variant-numeric:tabular-nums; }
        .plug-grid { display:grid; grid-template-columns:repeat(3,1fr); gap:14px; }
        .plug { background:var(--surface); border:1px solid var(--rule); border-radius:var(--radius-3); padding:18px; display:flex; flex-direction:column; gap:12px; transition:border-color 120ms,transform 120ms,box-shadow 120ms; position:relative; }
        .plug:hover { transform:translateY(-2px); border-color:rgba(129,140,248,0.4); box-shadow:0 12px 28px rgba(129,140,248,0.16); }
        .plug.installed { border-color:rgba(52,211,153,0.4); }
        .plug.installed::before { content:"INSTALLED"; position:absolute; top:12px; right:14px; font-size:9.5px; letter-spacing:0.08em; color:#6EE7B7; font-weight:700; }
        .plug__top { display:flex; align-items:flex-start; gap:12px; }
        .plug__logo { width:44px; height:44px; border-radius:10px; display:grid; place-items:center; color:#fff; font-family:var(--font-mono); font-weight:700; font-size:16px; flex-shrink:0; }
        .plug__name { font-weight:600; font-size:15px; line-height:1.2; }
        .plug__by { font-size:11.5px; color:var(--fg-3); margin-top:2px; }
        .plug__d { font-size:12.5px; color:var(--fg-2); line-height:1.5; flex:1; }
        .plug__foot { display:flex; align-items:center; gap:10px; font-size:11.5px; color:var(--fg-3); padding-top:4px; border-top:1px dashed var(--rule); }
        .plug__foot strong { color:var(--fg-1); font-variant-numeric:tabular-nums; }
        .plug__cta { margin-left:auto; }
        .cat-pills { display:flex; gap:8px; flex-wrap:wrap; margin-bottom:8px; }
        .cat-pill { font-size:11.5px; padding:5px 10px; border-radius:999px; background:var(--surface-2); border:1px solid var(--rule); color:var(--fg-2); cursor:pointer; }
        .cat-pill.is-active { background:rgba(129,140,248,0.16); color:#C7D2FE; border-color:rgba(129,140,248,0.4); }
      `}</style>

      <div className="phero">
        <div>
          <h1>Plugins</h1>
          <p>Extend the gateway, playground, and CLI with first-party and community plugins. <strong>6 installed</strong> · 38 in the registry.</p>
        </div>
        <div style={{ display: "flex", gap: 8 }}>
          <button className="btn">Submit a plugin</button>
          <button className="btn btn--primary">Browse registry</button>
        </div>
      </div>

      <div className="tabs-plug">
        {MAIN_TABS.map((t, i) => (
          <a key={t} className={tab === i ? "is-active" : ""} onClick={() => setTab(i)}>
            {t} <span className="count">{MAIN_COUNTS[i]}</span>
          </a>
        ))}
      </div>

      <div className="cat-pills">
        {CATEGORIES.map((c) => (
          <span key={c} className={`cat-pill${cat === c ? " is-active" : ""}`} onClick={() => setCat(c)}>{c}</span>
        ))}
      </div>

      <div className="plug-grid">
        {visible.map((p: Plugin) => (
          <div key={p.id} className={`plug${p.installed ? " installed" : ""}`}>
            <div className="plug__top">
              <div
                className="plug__logo"
                style={{ background: p.logoCss, color: p.logoCss.includes("2DD4BF") ? "#052E22" : p.logoCss.includes("FBBF24") ? "#2A0E10" : "#fff" }}
              >
                {p.logoLetters}
              </div>
              <div>
                <div className="plug__name">{p.name}</div>
                <div className="plug__by">{p.by}</div>
              </div>
            </div>
            <div className="plug__d">{p.description}</div>
            <div className="plug__foot">
              <span><strong>{p.stars}</strong> ★</span>
              <span><strong>{p.installs.toLocaleString()}</strong> installs</span>
              {p.installed ? (
                <div style={{ marginLeft: "auto", display: "flex", gap: 6 }}>
                  <button className="btn btn--sm plug__cta">Configure</button>
                  <button
                    className="btn btn--sm btn--danger"
                    onClick={() => handleToggleInstall(p.id)}
                  >
                    Uninstall
                  </button>
                </div>
              ) : (
                <button
                  className="btn btn--sm btn--primary plug__cta"
                  onClick={() => handleToggleInstall(p.id)}
                >
                  Install
                </button>
              )}
            </div>
          </div>
        ))}
      </div>
    </main>
  );
}
