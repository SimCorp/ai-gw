'use client';

import React from 'react';
import { useQuery } from '@tanstack/react-query';
import { LoadingState, ErrorState } from '../_components/PageStates';

const ADMIN_BASE = 'http://localhost:8005';

interface SystemHealth {
  redis: {
    status: string;
    ping_ms: number;
    used_memory_mb: number;
    connected_clients: number;
  };
  gateway: {
    status: string;
    requests_last_60s: number;
    cache_hit_rate_last_60s: number;
  };
}

// Static representative data for sections without live endpoints
const CACHE_TEAM_OVERRIDES = [
  { team: 'agent-platform',        threshold: '0.94', ttl: '24h', hit: '42%', note: 'stricter' as const },
  { team: 'platform-research',     threshold: '0.90', ttl: '6h',  hit: '38%', note: 'looser'   as const },
  { team: 'client-services-ai',    threshold: '0.92', ttl: '48h', hit: '34%', note: 'long-ttl' as const },
  { team: 'compliance-automation', threshold: '—',    ttl: '—',   hit: '—',   note: 'opted-out' as const },
  { team: 'sandbox-experiments',   threshold: '0.96', ttl: '1h',  hit: '9%',  note: 'low value' as const },
];

const CACHE_TOP_PROMPTS = [
  { fingerprint: '"You are a trading research assistant…" + Q1 EM debt summary', team: 'agent-platform',      model: 'claude-sonnet-4.5', hits: '218', avgSim: '0.961', tokensSaved: '1.2M', lastHit: '2 min ago' },
  { fingerprint: 'SDK changelog summarisation prompt template',                   team: 'developer-experience', model: 'claude-haiku-4.5',  hits: '184', avgSim: '0.948', tokensSaved: '412K', lastHit: '4 min ago' },
  { fingerprint: 'Support ticket classifier · v2.1',                              team: 'client-services-ai',   model: 'gemini-2.5-pro',    hits: '142', avgSim: '0.931', tokensSaved: '820K', lastHit: '6 min ago' },
  { fingerprint: 'Code review prompt · python style guide',                       team: 'platform-research',    model: 'claude-sonnet-4.5', hits: '98',  avgSim: '0.918', tokensSaved: '512K', lastHit: '11 min ago' },
  { fingerprint: 'Incident postmortem draft · weekly',                            team: 'risk-engineering',     model: 'claude-sonnet-4.5', hits: '62',  avgSim: '0.974', tokensSaved: '388K', lastHit: '28 min ago' },
];

function noteVariant(note: string) {
  if (note === 'stricter') return 'info';
  if (note === 'opted-out') return 'bad';
  if (note === 'low value') return 'warn';
  return 'default';
}

export default function CachePage() {
  const { data: health, isLoading, isError, error, refetch } = useQuery<SystemHealth>({
    queryKey: ['system-health'],
    queryFn: () => fetch(`${ADMIN_BASE}/system/health`).then(r => r.json()),
    refetchInterval: 15000,
  });

  if (isLoading) return <section className="page"><LoadingState rows={6} /></section>;
  if (isError) return <section className="page"><ErrorState error={error as Error} retry={() => refetch()} /></section>;

  const usedMemoryMb = health?.redis?.used_memory_mb ?? 0;
  const connectedClients = health?.redis?.connected_clients ?? 0;
  const cacheHitRate = health?.gateway?.cache_hit_rate_last_60s ?? 0;
  const requestsLast60s = health?.gateway?.requests_last_60s ?? 0;
  const redisStatus = health?.redis?.status ?? 'unknown';
  const pingMs = health?.redis?.ping_ms ?? 0;

  const hitRatePct = (cacheHitRate * 100).toFixed(1);
  const memoryDisplay = usedMemoryMb < 1024
    ? `${usedMemoryMb.toFixed(1)} MB`
    : `${(usedMemoryMb / 1024).toFixed(2)} GB`;

  return (
    <section className="page">
      <div className="page__head">
        <div>
          <h1 className="page__title">Semantic cache</h1>
          <p className="page__sub">
            Redis Stack 7.2 · vector index · <span className="mono">aigw_cache:v3</span>
            {' · '}
            <span className={redisStatus === 'ok' ? 'pill pill--good' : 'pill pill--bad'} style={{ display: 'inline-flex', marginLeft: 4 }}>
              <span className="dot"></span>redis {redisStatus}
            </span>
          </p>
        </div>
        <div className="page__actions">
          <button className="btn">Flush by team…</button>
          <button className="btn">Reindex</button>
          <button className="btn btn--primary">Edit defaults</button>
        </div>
      </div>

      <div className="minimet-row" style={{ marginBottom: 18 }}>
        <div className="minimet">
          <div className="minimet__l">Hit rate · 60s</div>
          <div className="minimet__v" style={{ color: cacheHitRate > 0 ? 'var(--good)' : undefined }}>
            {hitRatePct}<span className="unit">%</span>
          </div>
        </div>
        <div className="minimet">
          <div className="minimet__l">Requests · 60s</div>
          <div className="minimet__v">{requestsLast60s.toLocaleString()}</div>
        </div>
        <div className="minimet">
          <div className="minimet__l">Redis ping</div>
          <div className="minimet__v">{pingMs.toFixed(1)}<span className="unit">ms</span></div>
        </div>
        <div className="minimet">
          <div className="minimet__l">Memory used</div>
          <div className="minimet__v">{memoryDisplay}</div>
        </div>
        <div className="minimet">
          <div className="minimet__l">Clients</div>
          <div className="minimet__v">{connectedClients}</div>
        </div>
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
          <div className="card__head">
            <h3 className="card__title">Per-team overrides</h3>
            <span className="card__sub">representative data · 5 teams differ from default</span>
          </div>
          <div className="card__body" style={{ padding: 0 }}>
            <table className="tbl">
              <thead><tr><th>Team</th><th>Threshold</th><th>TTL</th><th className="num">Hit %</th><th></th></tr></thead>
              <tbody>
                {CACHE_TEAM_OVERRIDES.map(o => {
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
        <div className="card__head">
          <h3 className="card__title">Top cached prompts</h3>
          <span className="card__sub">representative data · live prompt fingerprints not yet available</span>
        </div>
        <div className="card__body" style={{ padding: 0 }}>
          <table className="tbl">
            <thead><tr><th>Prompt fingerprint</th><th>Team</th><th>Model</th><th className="num">Hits</th><th className="num">Avg sim</th><th className="num">Tokens saved</th><th>Last hit</th></tr></thead>
            <tbody>
              {CACHE_TOP_PROMPTS.map(p => (
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
