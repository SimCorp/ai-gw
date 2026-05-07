'use client';

import React, { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import Link from 'next/link';
import { LoadingState, ErrorState } from '../_components/PageStates';

const RANGES = ['1h', '24h', '7d', '30d', '90d'];

const TOP_TEAMS = [
  { name: 'platform-research',    spend: '$842.10',  bar: 0 },
  { name: 'agent-platform',       spend: '$648.55',  bar: 23 },
  { name: 'client-services-ai',   spend: '$496.20',  bar: 41 },
  { name: 'post-trade-ops',       spend: '$378.90',  bar: 55 },
  { name: 'risk-engineering',     spend: '$311.42',  bar: 64 },
  { name: 'data-platform',        spend: '$229.18',  bar: 73 },
  { name: 'developer-experience', spend: '$182.04',  bar: 81 },
  { name: 'design-systems',       spend: '$118.62',  bar: 88 },
];

export default function DashboardPage() {
  const [range, setRange] = useState('24h');

  const { data, isLoading, isError, error, refetch } = useQuery<Record<string, string>>({
    queryKey: ['dashboard', range],
    queryFn: () => fetch('/api/v1/dashboard').then(r => r.json()),
  });

  if (isLoading) return <section className="page"><LoadingState rows={8} /></section>;
  if (isError) return <section className="page"><ErrorState error={error as Error} retry={() => refetch()} /></section>;

  return (
    <section className="page">
      <div className="page__head">
        <div>
          <h1 className="page__title">Platform overview</h1>
          <p className="page__sub">Org-wide usage, cost, and health · last 24 hours</p>
        </div>
        <div className="page__actions">
          <div className="seg" role="tablist">
            {RANGES.map(r => (
              <button
                key={r}
                className={range === r ? 'is-active' : undefined}
                onClick={() => setRange(r)}
                aria-pressed={range === r}
              >{r}</button>
            ))}
          </div>
          <button className="btn">Export</button>
          <button className="btn btn--primary">+ New team</button>
        </div>
      </div>

      {/* KPI row 1 */}
      <div className="kpi-grid" style={{ marginBottom: 16 }}>
        <div className="kpi">
          <div className="kpi__label">Total spend</div>
          <div className="kpi__value">$3,847<span className="unit">.21</span></div>
          <div className="kpi__delta down">▼ 12.4% vs prev 24h</div>
          <svg className="spark kpi__spark" viewBox="0 0 100 28" preserveAspectRatio="none">
            <path d="M0,18 L10,16 L20,20 L30,12 L40,15 L50,9 L60,13 L70,8 L80,11 L90,6 L100,9" fill="none" stroke="var(--sc-blue)" strokeWidth="1.5"/>
            <path d="M0,18 L10,16 L20,20 L30,12 L40,15 L50,9 L60,13 L70,8 L80,11 L90,6 L100,9 L100,28 L0,28 Z" fill="var(--sc-blue)" opacity="0.08"/>
          </svg>
        </div>
        <div className="kpi">
          <div className="kpi__label">Cache savings</div>
          <div className="kpi__value">$1,209<span className="unit">.45</span></div>
          <div className="kpi__delta up">▲ 8.1% vs prev 24h</div>
          <svg className="spark kpi__spark" viewBox="0 0 100 28" preserveAspectRatio="none">
            <path d="M0,22 L10,20 L20,18 L30,16 L40,14 L50,12 L60,11 L70,9 L80,7 L90,5 L100,4" fill="none" stroke="var(--good)" strokeWidth="1.5"/>
            <path d="M0,22 L10,20 L20,18 L30,16 L40,14 L50,12 L60,11 L70,9 L80,7 L90,5 L100,4 L100,28 L0,28 Z" fill="var(--good)" opacity="0.10"/>
          </svg>
        </div>
        <div className="kpi">
          <div className="kpi__label">Requests</div>
          <div className="kpi__value">2.41<span className="unit">M</span></div>
          <div className="kpi__delta up">▲ 3.2% · 27.8 req/s avg</div>
          <svg className="spark kpi__spark" viewBox="0 0 100 28" preserveAspectRatio="none">
            <path d="M0,15 L8,18 L16,12 L24,16 L32,10 L40,14 L48,8 L56,12 L64,6 L72,10 L80,5 L88,9 L100,4" fill="none" stroke="var(--sc-purple)" strokeWidth="1.5"/>
          </svg>
        </div>
        <div className="kpi">
          <div className="kpi__label">p99 gateway latency</div>
          <div className="kpi__value">38<span className="unit">ms</span></div>
          <div className="kpi__delta flat">▬ within SLO (50ms)</div>
          <svg className="spark kpi__spark" viewBox="0 0 100 28" preserveAspectRatio="none">
            <path d="M0,14 L10,16 L20,12 L30,15 L40,11 L50,14 L60,12 L70,15 L80,13 L90,16 L100,14" fill="none" stroke="var(--fg-2)" strokeWidth="1.5"/>
          </svg>
        </div>
      </div>

      {/* KPI row 2 */}
      <div className="kpi-grid" style={{ gridTemplateColumns: 'repeat(4,1fr)', marginBottom: 20 }}>
        <div className="kpi">
          <div className="kpi__label">Cache hit rate</div>
          <div className="kpi__value">31.4<span className="unit">%</span></div>
          <div className="kpi__delta up">semantic 18.9% · exact 12.5%</div>
        </div>
        <div className="kpi">
          <div className="kpi__label">Active API keys</div>
          <div className="kpi__value">487</div>
          <div className="kpi__delta flat">42 teams · 1,184 callers</div>
        </div>
        <div className="kpi">
          <div className="kpi__label">Error rate</div>
          <div className="kpi__value">0.21<span className="unit">%</span></div>
          <div className="kpi__delta up">▼ 0.04 pp</div>
        </div>
        <div className="kpi">
          <div className="kpi__label">Tokens (in / out)</div>
          <div className="kpi__value">412<span className="unit">M / 188M</span></div>
          <div className="kpi__delta flat">2.19:1 ratio</div>
        </div>
      </div>

      {/* Charts row */}
      <div className="split-2" style={{ marginBottom: 16 }}>
        <div className="card">
          <div className="card__head">
            <h3 className="card__title">Request volume &amp; cache hits</h3>
            <span className="card__sub">stacked, requests/min</span>
            <div className="card__actions">
              <span className="pill"><span className="dot" style={{ background: 'var(--sc-blue)' }}></span>Provider</span>
              <span className="pill"><span className="dot" style={{ background: 'var(--sc-teal)' }}></span>Cache hit</span>
            </div>
          </div>
          <div className="card__body">
            <svg viewBox="0 0 800 240" preserveAspectRatio="none" style={{ width: '100%', height: 240, display: 'block' }}>
              <g stroke="var(--rule)" strokeWidth="1">
                <line x1="40" y1="20" x2="780" y2="20"/><line x1="40" y1="70" x2="780" y2="70"/>
                <line x1="40" y1="120" x2="780" y2="120"/><line x1="40" y1="170" x2="780" y2="170"/><line x1="40" y1="220" x2="780" y2="220"/>
              </g>
              <g fill="var(--fg-3)" fontSize="10" fontFamily="var(--font-mono)">
                <text x="36" y="24" textAnchor="end">120</text><text x="36" y="74" textAnchor="end">90</text>
                <text x="36" y="124" textAnchor="end">60</text><text x="36" y="174" textAnchor="end">30</text><text x="36" y="224" textAnchor="end">0</text>
              </g>
              <path d="M40,170 L80,150 L120,140 L160,155 L200,130 L240,135 L280,110 L320,115 L360,95 L400,100 L440,80 L480,90 L520,70 L560,85 L600,60 L640,75 L680,55 L720,72 L760,50 L780,60 L780,220 L40,220 Z" fill="var(--sc-blue)" opacity="0.85"/>
              <path d="M40,150 L80,135 L120,125 L160,138 L200,115 L240,118 L280,95 L320,100 L360,80 L400,86 L440,65 L480,75 L520,55 L560,68 L600,42 L640,58 L680,38 L720,55 L760,32 L780,42 L780,60 L760,50 L720,72 L680,55 L640,75 L600,60 L560,85 L520,70 L480,90 L440,80 L400,100 L360,95 L320,115 L280,110 L240,135 L200,130 L160,155 L120,140 L80,150 L40,170 Z" fill="var(--sc-teal)" opacity="0.85"/>
              <g fill="var(--fg-3)" fontSize="10" fontFamily="var(--font-mono)">
                <text x="40" y="234">06:00</text><text x="225" y="234">12:00</text>
                <text x="410" y="234">18:00</text><text x="600" y="234">00:00</text>
                <text x="760" y="234" textAnchor="end">now</text>
              </g>
            </svg>
          </div>
        </div>

        <div className="card">
          <div className="card__head">
            <h3 className="card__title">Top teams · spend</h3>
            <span className="card__sub">last 24h</span>
            <div className="card__actions">
              <Link href="/admin/teams" className="btn btn--sm btn--ghost">View all →</Link>
            </div>
          </div>
          <div className="card__body" style={{ paddingTop: 8 }}>
            <div className="barlist">
              {TOP_TEAMS.map(t => (
                <div key={t.name} className="row">
                  <div className="lbl">
                    <span className="name">{t.name}</span>
                    <span className="bar"><i style={{ right: `${t.bar}%` }}></i></span>
                  </div>
                  <div className="num">{t.spend}</div>
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>

      {/* 3-col row */}
      <div className="split-3" style={{ marginBottom: 16 }}>
        <div className="card">
          <div className="card__head"><h3 className="card__title">Model mix</h3><span className="card__sub">by spend</span></div>
          <div className="card__body">
            <div style={{ display: 'flex', alignItems: 'center', gap: 14 }}>
              <svg viewBox="0 0 80 80" width="100" height="100" style={{ flexShrink: 0 }}>
                <circle cx="40" cy="40" r="32" fill="none" stroke="var(--rule)" strokeWidth="14"/>
                <circle cx="40" cy="40" r="32" fill="none" stroke="var(--sc-blue)" strokeWidth="14" strokeDasharray="92 200" strokeDashoffset="0" transform="rotate(-90 40 40)"/>
                <circle cx="40" cy="40" r="32" fill="none" stroke="var(--sc-teal)" strokeWidth="14" strokeDasharray="58 200" strokeDashoffset="-92" transform="rotate(-90 40 40)"/>
                <circle cx="40" cy="40" r="32" fill="none" stroke="var(--sc-purple)" strokeWidth="14" strokeDasharray="32 200" strokeDashoffset="-150" transform="rotate(-90 40 40)"/>
                <circle cx="40" cy="40" r="32" fill="none" stroke="var(--sc-orange)" strokeWidth="14" strokeDasharray="19 200" strokeDashoffset="-182" transform="rotate(-90 40 40)"/>
              </svg>
              <div style={{ flex: 1, display: 'flex', flexDirection: 'column', gap: 6, fontSize: 12 }}>
                {[
                  { color: 'var(--sc-blue)', label: 'claude-sonnet-4.5', pct: '46%' },
                  { color: 'var(--sc-teal)', label: 'gemini-2.5-pro', pct: '29%' },
                  { color: 'var(--sc-purple)', label: 'claude-haiku-4.5', pct: '16%' },
                  { color: 'var(--sc-orange)', label: 'gpt-5 (BYO)', pct: '9%' },
                ].map(m => (
                  <div key={m.label} style={{ display: 'flex', justifyContent: 'space-between' }}>
                    <span><span className="statusdot" style={{ background: m.color, boxShadow: 'none' }}></span>{m.label}</span>
                    <span className="mono">{m.pct}</span>
                  </div>
                ))}
              </div>
            </div>
          </div>
        </div>

        <div className="card">
          <div className="card__head"><h3 className="card__title">Provider health</h3><span className="card__sub">live</span></div>
          <div className="card__body" style={{ padding: 0 }}>
            <table className="tbl">
              <tbody>
                <tr><td><span className="statusdot statusdot--good"></span>Anthropic</td><td className="num mono">28ms</td><td><span className="pill pill--good">healthy</span></td></tr>
                <tr><td><span className="statusdot statusdot--good"></span>Google Gemini</td><td className="num mono">41ms</td><td><span className="pill pill--good">healthy</span></td></tr>
                <tr><td><span className="statusdot statusdot--warn"></span>GitHub Models</td><td className="num mono">187ms</td><td><span className="pill pill--warn">degraded</span></td></tr>
                <tr><td><span className="statusdot statusdot--good"></span>Ollama (eu-1)</td><td className="num mono">12ms</td><td><span className="pill pill--good">healthy</span></td></tr>
                <tr><td><span className="statusdot statusdot--bad"></span>Azure OpenAI (BYO)</td><td className="num mono">—</td><td><span className="pill pill--bad">5xx 8.2%</span></td></tr>
              </tbody>
            </table>
          </div>
        </div>

        <div className="card">
          <div className="card__head"><h3 className="card__title">Cache</h3><span className="card__sub">last 24h</span></div>
          <div className="card__body">
            <div className="dl">
              <dt>Hit rate (total)</dt><dd>31.4%</dd>
              <dt>Exact match</dt><dd>12.5%</dd>
              <dt>Semantic match</dt><dd>18.9%</dd>
              <dt>Avg similarity</dt><dd>0.927</dd>
              <dt>Embedding calls</dt><dd>1.2M</dd>
              <dt>Redis memory</dt><dd>14.2 GB / 32 GB</dd>
              <dt>Redis ops/s p99</dt><dd>4,810</dd>
              <dt>Tokens saved</dt><dd>187.4M</dd>
            </div>
          </div>
        </div>
      </div>

      {/* Bottom row */}
      <div className="split-2">
        <div className="card">
          <div className="card__head">
            <h3 className="card__title">Recent activity</h3>
            <div className="card__actions"><Link href="/admin/audit" className="btn btn--sm btn--ghost">Audit log →</Link></div>
          </div>
          <div className="card__body" style={{ padding: 0 }}>
            <table className="tbl">
              <thead><tr><th>Time</th><th>Actor</th><th>Action</th><th>Target</th></tr></thead>
              <tbody>
                <tr><td className="mono">14:42:08</td><td>j.larsen@simcorp.com</td><td>rotated key</td><td><span className="tag">agent-platform · prod</span></td></tr>
                <tr><td className="mono">14:38:55</td><td>system</td><td>auto-throttled</td><td><span className="tag">data-platform</span> · 429s × 142</td></tr>
                <tr><td className="mono">14:21:11</td><td>m.rasmussen@simcorp.com</td><td>updated policy</td><td>cache_threshold 0.92 → 0.94</td></tr>
                <tr><td className="mono">13:58:02</td><td>k.haukur@simcorp.com</td><td>created team</td><td>nordic-research</td></tr>
                <tr><td className="mono">13:44:30</td><td>system</td><td>provider failover</td><td>anthropic → gemini · 47s</td></tr>
                <tr><td className="mono">13:12:04</td><td>a.silva@simcorp.com</td><td>revoked key</td><td><span className="mono">sk_live_••••a31f</span></td></tr>
              </tbody>
            </table>
          </div>
        </div>

        <div className="card">
          <div className="card__head">
            <h3 className="card__title">Active alerts</h3>
            <span className="card__sub">3 open</span>
          </div>
          <div className="card__body" style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
            {[
              { color: 'bad', title: 'Azure OpenAI (BYO) — 5xx surge', desc: '8.2% error rate over last 15 min · auto-failover engaged · 2 teams affected', btn: 'Investigate' },
              { color: 'warn', title: 'data-platform — rate limit', desc: '142 × 429 in 10 min · current 60 rpm cap, requested 120', btn: 'Review' },
              { color: 'warn', title: 'agent-platform — budget at 84%', desc: '$8,420 / $10,000 monthly · projected to exceed by May 27', btn: 'Adjust' },
            ].map(a => (
              <div key={a.title} style={{ display: 'flex', gap: 10, padding: 10, border: '1px solid var(--rule)', borderRadius: 6, background: `var(--${a.color}-soft)` }}>
                <span className={`statusdot statusdot--${a.color}`} style={{ marginTop: 5 }}></span>
                <div style={{ flex: 1 }}>
                  <div style={{ fontWeight: 600, fontSize: 12.5 }}>{a.title}</div>
                  <div className="muted" style={{ fontSize: 11.5 }}>{a.desc}</div>
                </div>
                <button className="btn btn--sm">{a.btn}</button>
              </div>
            ))}
          </div>
        </div>
      </div>
    </section>
  );
}
