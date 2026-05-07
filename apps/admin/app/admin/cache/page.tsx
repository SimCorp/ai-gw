'use client';

import React from 'react';
import { useQuery } from '@tanstack/react-query';
import { LoadingState, ErrorState } from '../_components/PageStates';
import { CACHE_STATS, CACHE_POLICY, CACHE_TEAM_OVERRIDES, CACHE_TOP_PROMPTS } from '../_mocks/data';

type CacheData = {
  stats: typeof CACHE_STATS;
  policy: typeof CACHE_POLICY;
  teamOverrides: typeof CACHE_TEAM_OVERRIDES;
  topPrompts: typeof CACHE_TOP_PROMPTS;
};

function noteVariant(note: string) {
  if (note === 'stricter') return 'info';
  if (note === 'opted-out') return 'bad';
  if (note === 'low value') return 'warn';
  return 'default';
}

export default function CachePage() {
  const { data, isLoading, isError, error, refetch } = useQuery<CacheData>({
    queryKey: ['cache'],
    queryFn: () => fetch('/api/v1/cache').then(r => r.json()),
  });

  const d = data ?? { stats: CACHE_STATS, policy: CACHE_POLICY, teamOverrides: CACHE_TEAM_OVERRIDES, topPrompts: CACHE_TOP_PROMPTS };

  if (isLoading) return <section className="page"><LoadingState rows={6} /></section>;
  if (isError) return <section className="page"><ErrorState error={error as Error} retry={() => refetch()} /></section>;

  return (
    <section className="page">
      <div className="page__head">
        <div>
          <h1 className="page__title">Semantic cache</h1>
          <p className="page__sub">Redis Stack 7.2 · vector index · <span className="mono">aigw_cache:v3</span></p>
        </div>
        <div className="page__actions">
          <button className="btn">Flush by team…</button>
          <button className="btn">Reindex</button>
          <button className="btn btn--primary">Edit defaults</button>
        </div>
      </div>

      <div className="minimet-row" style={{ marginBottom: 18 }}>
        <div className="minimet"><div className="minimet__l">Hit rate · 24h</div><div className="minimet__v" style={{ color: 'var(--good)' }}>31.4<span className="unit">%</span></div></div>
        <div className="minimet"><div className="minimet__l">Tokens saved</div><div className="minimet__v">187<span className="unit">M</span></div></div>
        <div className="minimet"><div className="minimet__l">$ saved</div><div className="minimet__v">$1,209</div></div>
        <div className="minimet"><div className="minimet__l">Memory</div><div className="minimet__v">14.2<span className="unit">/32 GB</span></div></div>
        <div className="minimet"><div className="minimet__l">Vector index</div><div className="minimet__v">2.41<span className="unit">M</span></div></div>
        <div className="minimet"><div className="minimet__l">Ops/s p99</div><div className="minimet__v">4,810</div></div>
      </div>

      <div className="split-2" style={{ marginBottom: 16 }}>
        <div className="card">
          <div className="card__head">
            <h3 className="card__title">Hit rate over time</h3>
            <span className="card__sub">last 7d · stacked</span>
            <div className="card__actions">
              <span className="pill"><span className="dot" style={{ background: 'var(--sc-teal)' }}></span>Semantic</span>
              <span className="pill"><span className="dot" style={{ background: 'var(--sc-blue)' }}></span>Exact</span>
            </div>
          </div>
          <div className="card__body">
            <svg viewBox="0 0 600 220" style={{ width: '100%', height: 220, display: 'block' }}>
              <g stroke="var(--rule)" strokeWidth="1">
                <line x1="36" y1="20" x2="588" y2="20"/><line x1="36" y1="70" x2="588" y2="70"/>
                <line x1="36" y1="120" x2="588" y2="120"/><line x1="36" y1="170" x2="588" y2="170"/>
              </g>
              <g fill="var(--fg-3)" fontSize="10" fontFamily="var(--font-mono)">
                <text x="32" y="24" textAnchor="end">50%</text><text x="32" y="74" textAnchor="end">35%</text>
                <text x="32" y="124" textAnchor="end">20%</text><text x="32" y="174" textAnchor="end">5%</text>
              </g>
              <path d="M40,150 L120,148 L200,142 L280,138 L360,135 L440,132 L520,128 L588,125 L588,170 L40,170 Z" fill="var(--sc-blue)" opacity="0.85"/>
              <path d="M40,118 L120,112 L200,108 L280,100 L360,95 L440,88 L520,82 L588,78 L588,125 L520,128 L440,132 L360,135 L280,138 L200,142 L120,148 L40,150 Z" fill="var(--sc-teal)" opacity="0.85"/>
              <g fill="var(--fg-3)" fontSize="10" fontFamily="var(--font-mono)">
                <text x="40" y="190">Apr 30</text><text x="296" y="190">May 3</text>
                <text x="588" y="190" textAnchor="end">May 6</text>
              </g>
            </svg>
          </div>
        </div>

        <div className="card">
          <div className="card__head"><h3 className="card__title">Similarity distribution</h3><span className="card__sub">semantic hits · last 24h</span></div>
          <div className="card__body">
            <svg viewBox="0 0 600 220" style={{ width: '100%', height: 220, display: 'block' }}>
              <g stroke="var(--rule)" strokeWidth="1">
                <line x1="36" y1="20" x2="588" y2="20"/><line x1="36" y1="70" x2="588" y2="70"/>
                <line x1="36" y1="120" x2="588" y2="120"/><line x1="36" y1="170" x2="588" y2="170"/>
              </g>
              <line x1="378" y1="20" x2="378" y2="170" stroke="var(--bad)" strokeWidth="1" strokeDasharray="4 4"/>
              <text x="382" y="32" fill="var(--bad)" fontSize="10">Threshold 0.92</text>
              <g fill="var(--sc-teal)">
                {[2,3,5,8,12,18,28,40,52,68,86,104,120,142,160,170,148,108,72,38,14].map((v, i) => {
                  const x = 44 + i * 26; const h = v * 0.85; const y = 170 - h;
                  return <rect key={i} x={x} y={y} width="22" height={h} rx="1.5"/>;
                })}
              </g>
              <g fill="var(--fg-3)" fontSize="10" fontFamily="var(--font-mono)">
                <text x="44" y="190">0.80</text><text x="290" y="190">0.90</text>
                <text x="588" y="190" textAnchor="end">1.00</text>
              </g>
            </svg>
          </div>
        </div>
      </div>

      <div className="split-2" style={{ marginBottom: 16 }}>
        <div className="card">
          <div className="card__head"><h3 className="card__title">Default policy</h3><div className="card__actions"><button className="btn btn--sm">Edit</button></div></div>
          <div className="card__body">
            <div className="dl">
              <dt>Status</dt><dd><span className="pill pill--good"><span className="dot"></span>Enabled (org-wide)</span></dd>
              <dt>TTL</dt><dd>12 hours</dd>
              <dt>Similarity threshold</dt><dd>0.92</dd>
              <dt>Embedding model</dt><dd className="mono">text-embedding-3-small</dd>
              <dt>Embedding cache</dt><dd>24 hours · separate Redis prefix</dd>
              <dt>Stream caching</dt><dd>Assemble before store · streaming passthrough unaffected</dd>
              <dt>On Redis failure</dt><dd>Fail open (request proceeds, miss recorded)</dd>
            </div>
          </div>
        </div>

        <div className="card">
          <div className="card__head"><h3 className="card__title">Per-team overrides</h3><span className="card__sub">5 teams differ from default</span></div>
          <div className="card__body" style={{ padding: 0 }}>
            <table className="tbl">
              <thead><tr><th>Team</th><th>Threshold</th><th>TTL</th><th className="num">Hit %</th><th></th></tr></thead>
              <tbody>
                {d.teamOverrides.map(o => {
                  const v = noteVariant(o.note);
                  return (
                    <tr key={o.team}>
                      <td><a href={`/admin/teams`}>{o.team}</a></td>
                      <td className="mono">{o.threshold}</td>
                      <td className="mono">{o.ttl}</td>
                      <td className="num mono">{o.hit}</td>
                      <td>
                        {v === 'default' ? <span className="pill">{o.note}</span>
                          : v === 'info' ? <span className="pill pill--info">{o.note}</span>
                          : v === 'bad' ? <span className="pill pill--bad">{o.note}</span>
                          : <span className="pill pill--warn">{o.note}</span>}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </div>
      </div>

      <div className="card">
        <div className="card__head"><h3 className="card__title">Top cached prompts</h3><span className="card__sub">last 24h · by hit count</span></div>
        <div className="card__body" style={{ padding: 0 }}>
          <table className="tbl">
            <thead><tr><th>Prompt fingerprint</th><th>Team</th><th>Model</th><th className="num">Hits</th><th className="num">Avg sim</th><th className="num">Tokens saved</th><th>Last hit</th></tr></thead>
            <tbody>
              {d.topPrompts.map(p => (
                <tr key={p.fingerprint}>
                  <td><span className="mono">{p.fingerprint}</span></td>
                  <td>{p.team}</td>
                  <td className="mono">{p.model}</td>
                  <td className="num mono">{p.hits}</td>
                  <td className="num mono">{p.avgSim}</td>
                  <td className="num mono">{p.tokensSaved}</td>
                  <td className="mono">{p.lastHit}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </section>
  );
}
