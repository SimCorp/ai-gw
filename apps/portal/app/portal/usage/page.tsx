"use client";

import { useState } from "react";

// Pre-computed SVG bar data from the mock (30 days, stacked Sonnet/Haiku/Gemini)
const BAR_DATA = [
  [142,11.9,14.62],[37.46,12.87,15.22],[46.14,13.09,15.4],[53.39,8.65,15.14],[41.99,8.34,14.46],
  [45.41,8.4,13.43],[47.01,4.94,12.14],[47.27,6.52,10.7],[30.06,8.91,9.25],[29.77,7.66,7.9],
  [30.36,10.79,6.79],[32.46,13.68,6.01],[19.65,11.76,5.63],[25.62,13.22,5.69],[33.35,13.84,6.17],
  [42.33,9.61,7.04],[35.07,9.29,8.22],[44.38,9.09,9.61],[52.7,5.21,11.07],[59.45,6.31,12.48],
  [47.47,8.26,13.72],[50.32,6.74,14.67],[51.47,9.82,15.24],[51.46,12.89,15.39],[34.2,11.35,15.11],
  [34.1,13.29,14.41],[35.07,14.38,13.37],[37.69,10.48,12.06],[25.46,10.28,10.62],[31.98,9.96,9.17],
];

const RANGE_OPTS = ["24h", "7d", "30d", "MTD"] as const;

export default function UsagePage() {
  const [range, setRange] = useState<string>("30d");

  return (
    <main className="pmain">
      <div className="phero">
        <div>
          <h1>Usage &amp; spend</h1>
          <p>Your activity on <strong>agent-platform</strong> · last 30 days</p>
        </div>
        <div style={{ display: "flex", gap: 8 }}>
          <div className="seg">
            {RANGE_OPTS.map((r) => (
              <button key={r} className={range === r ? "is-active" : ""} onClick={() => setRange(r)}>{r}</button>
            ))}
          </div>
          <button className="btn">Export CSV</button>
        </div>
      </div>

      <div className="stat-strip">
        <div className="s">
          <div className="l">Spend · 30d</div><div className="v">$284.10</div>
          <div className="d">3.1% of team total</div>
        </div>
        <div className="s">
          <div className="l">Requests</div><div className="v">38,412</div>
          <div className="d">avg 1,280 / day</div>
        </div>
        <div className="s">
          <div className="l">Tokens · in / out</div>
          <div className="v" style={{ fontSize: 18 }}>42M / 8.1M</div>
          <div className="d">5.2:1 ratio</div>
        </div>
        <div className="s">
          <div className="l">Cache hit · you</div>
          <div className="v good">38%</div>
          <div className="d">saved $98</div>
        </div>
      </div>

      {/* Stacked bar chart */}
      <div className="card" style={{ marginBottom: 18 }}>
        <div className="card__head">
          <h3 className="card__title">Spend over time</h3>
          <span className="card__sub">stacked by model</span>
          <div className="card__actions">
            <span className="pill"><span className="dot" style={{ background: "#D97757" }} />Sonnet</span>
            <span className="pill"><span className="dot" style={{ background: "#FB9B2A" }} />Haiku</span>
            <span className="pill"><span className="dot" style={{ background: "#4285F4" }} />Gemini</span>
          </div>
        </div>
        <div className="card__body">
          <svg viewBox="0 0 600 220" style={{ width: "100%", height: 220, display: "block" }}>
            {/* Grid lines */}
            <g stroke="var(--rule)" strokeWidth="1">
              <line x1="40" y1="20" x2="588" y2="20"/>
              <line x1="40" y1="70" x2="588" y2="70"/>
              <line x1="40" y1="120" x2="588" y2="120"/>
              <line x1="40" y1="170" x2="588" y2="170"/>
            </g>
            <g fill="var(--fg-3)" fontSize="10" fontFamily="var(--font-mono)">
              <text x="36" y="24" textAnchor="end">$20</text>
              <text x="36" y="74" textAnchor="end">$15</text>
              <text x="36" y="124" textAnchor="end">$10</text>
              <text x="36" y="174" textAnchor="end">$0</text>
            </g>
            <g>
              {BAR_DATA.map(([sonnet, haiku, gemini], i) => {
                const x = 48 + i * 18;
                const totalH = sonnet + haiku + gemini;
                const y3 = 170 - totalH; // gemini (bottom of stack, visually top)
                const y2 = 170 - sonnet - haiku;
                const y1 = 170 - sonnet;
                return (
                  <g key={i}>
                    <rect x={x} y={y1} width={12} height={sonnet} fill="#D97757" rx={1}/>
                    <rect x={x} y={y2} width={12} height={haiku} fill="#FB9B2A" rx={1}/>
                    <rect x={x} y={y3} width={12} height={gemini} fill="#4285F4" rx={1}/>
                  </g>
                );
              })}
            </g>
            <g fill="var(--fg-3)" fontSize="10" fontFamily="var(--font-mono)">
              <text x="48" y="190">Apr 7</text>
              <text x="296" y="190">Apr 22</text>
              <text x="588" y="190" textAnchor="end">May 6</text>
            </g>
          </svg>
        </div>
      </div>

      <div className="split-2">
        {/* By key */}
        <div className="card">
          <div className="card__head"><h3 className="card__title">By API key</h3></div>
          <div className="card__body" style={{ padding: 0 }}>
            <table className="tbl">
              <thead>
                <tr>
                  <th>Key</th>
                  <th className="num">Calls</th>
                  <th className="num">Tokens</th>
                  <th className="num">Spend</th>
                </tr>
              </thead>
              <tbody>
                {[
                  { name: "prod-rag-service", calls: "28,210", tokens: "38.2M", spend: "$218.40" },
                  { name: "eval-runner",       calls: "8,114",  tokens: "8.4M",  spend: "$48.20" },
                  { name: "jupyter-notebook",  calls: "2,088",  tokens: "3.5M",  spend: "$17.50" },
                ].map((row) => (
                  <tr key={row.name}>
                    <td><strong>{row.name}</strong></td>
                    <td className="num"><span className="mono">{row.calls}</span></td>
                    <td className="num"><span className="mono">{row.tokens}</span></td>
                    <td className="num"><span className="mono">{row.spend}</span></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>

        {/* By model */}
        <div className="card">
          <div className="card__head"><h3 className="card__title">By model</h3></div>
          <div className="card__body">
            <div className="barlist">
              {[
                { name: "claude-sonnet-4.5",       pct: 100, spend: "$184.20" },
                { name: "gemini-2.5-pro",           pct: 46,  spend: "$58.10" },
                { name: "claude-haiku-4.5",         pct: 26,  spend: "$32.80" },
                { name: "text-embedding-3-small",   pct: 8,   spend: "$9.00" },
              ].map((row) => (
                <div className="row" key={row.name}>
                  <div className="lbl">
                    <span className="name">{row.name}</span>
                    <span className="bar"><i style={{ right: `${100 - row.pct}%` }} /></span>
                  </div>
                  <div className="num">{row.spend}</div>
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>
    </main>
  );
}
