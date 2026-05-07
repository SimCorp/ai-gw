'use client';

import React, { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import Link from 'next/link';
import { LoadingState, ErrorState } from '../../_components/PageStates';
import { AGENT_PLATFORM_TEAM } from '../../_mocks/data';

type TeamDetail = typeof AGENT_PLATFORM_TEAM;

const TABS = ['overview', 'keys', 'policies', 'members', 'audit'] as const;
type Tab = typeof TABS[number];

export default function TeamDetailPage({ params }: { params: { id: string } }) {
  const [tab, setTab] = useState<Tab>('overview');

  const { data, isLoading, isError, error, refetch } = useQuery<TeamDetail>({
    queryKey: ['team-detail', params.id],
    queryFn: () => fetch(`/api/v1/teams/${params.id}/detail`).then(r => r.json()),
  });

  const t = data ?? AGENT_PLATFORM_TEAM;

  if (isLoading) return <section className="page"><LoadingState rows={8} /></section>;
  if (isError) return <section className="page"><ErrorState error={error as Error} retry={() => refetch()} /></section>;

  return (
    <section className="page">
      <div className="page__head">
        <div style={{ display: 'flex', alignItems: 'center', gap: 14 }}>
          <span style={{
            display: 'grid', placeItems: 'center',
            width: 36, height: 36, borderRadius: 8,
            background: 'linear-gradient(135deg,var(--sc-blue),var(--sc-purple))',
            color: '#fff', fontWeight: 700, fontSize: 13,
          }}>TC</span>
          <div>
            <h1 className="page__title">
              {t.name} <span style={{ color: 'var(--fg-3)', fontWeight: 400, fontSize: 13, marginLeft: 6 }} className="mono">{t.idLabel}</span>
            </h1>
            <p className="page__sub">Owner <strong>{t.owner}</strong> · {typeof t.members === 'number' ? t.members : 18} members · created {t.createdAt}</p>
          </div>
        </div>
        <div className="page__actions">
          <button className="btn">Edit</button>
          <button className="btn">Suspend</button>
          <button className="btn btn--primary">+ Issue API key</button>
        </div>
      </div>

      <div className="minimet-row" style={{ marginBottom: 18 }}>
        <div className="minimet"><div className="minimet__l">Spend MTD</div><div className="minimet__v">{t.spendMtd}</div></div>
        <div className="minimet"><div className="minimet__l">Budget</div><div className="minimet__v">{t.budgetPct}<span className="unit">%</span> · {t.budgetCap} cap</div></div>
        <div className="minimet"><div className="minimet__l">Requests 24h</div><div className="minimet__v">{t.req24h}</div></div>
        <div className="minimet"><div className="minimet__l">Cache hit</div><div className="minimet__v">{t.cacheHit}<span className="unit">%</span></div></div>
        <div className="minimet"><div className="minimet__l">p99 latency</div><div className="minimet__v">{t.p99}</div></div>
        <div className="minimet"><div className="minimet__l">Error rate</div><div className="minimet__v">{t.errorRate}</div></div>
      </div>

      <nav className="tabbar">
        <a href="#overview" className={tab === 'overview' ? 'is-active' : undefined} onClick={e => { e.preventDefault(); setTab('overview'); }}>Overview</a>
        <a href="#keys" className={tab === 'keys' ? 'is-active' : undefined} onClick={e => { e.preventDefault(); setTab('keys'); }}>API keys <span className="tag" style={{ marginLeft: 6 }}>14</span></a>
        <a href="#policies" className={tab === 'policies' ? 'is-active' : undefined} onClick={e => { e.preventDefault(); setTab('policies'); }}>Policies</a>
        <a href="#members" className={tab === 'members' ? 'is-active' : undefined} onClick={e => { e.preventDefault(); setTab('members'); }}>Members <span className="tag" style={{ marginLeft: 6 }}>18</span></a>
        <a href="#audit" className={tab === 'audit' ? 'is-active' : undefined} onClick={e => { e.preventDefault(); setTab('audit'); }}>Audit</a>
      </nav>
      <div style={{ height: 18 }} />

      {tab === 'overview' && (
        <>
          <div className="split-2" style={{ marginBottom: 16 }}>
            <div className="card">
              <div className="card__head">
                <h3 className="card__title">Spend</h3>
                <span className="card__sub">last 30 days · vs {t.budgetCap} cap</span>
              </div>
              <div className="card__body">
                <svg viewBox="0 0 600 200" preserveAspectRatio="none" style={{ width: '100%', height: 200, display: 'block' }}>
                  <g stroke="var(--rule)" strokeWidth="1">
                    <line x1="36" y1="20" x2="588" y2="20"/><line x1="36" y1="65" x2="588" y2="65"/>
                    <line x1="36" y1="110" x2="588" y2="110"/><line x1="36" y1="155" x2="588" y2="155"/>
                  </g>
                  <line x1="36" y1="42" x2="588" y2="42" stroke="var(--bad)" strokeWidth="1" strokeDasharray="4 4"/>
                  <text x="586" y="38" textAnchor="end" fill="var(--bad)" fontSize="10">Cap {t.budgetCap}</text>
                  <g fill="var(--fg-3)" fontSize="10" fontFamily="var(--font-mono)">
                    <text x="32" y="24" textAnchor="end">10k</text><text x="32" y="69" textAnchor="end">6k</text>
                    <text x="32" y="114" textAnchor="end">3k</text><text x="32" y="159" textAnchor="end">0</text>
                  </g>
                  <g fill="var(--sc-blue)">
                    {Array.from({ length: 30 }).map((_, i) => {
                      const v = Math.min(8 + i * 0.7 + (i % 3) * 0.6, 28);
                      const h = v * 5.5; const x = 44 + i * 18; const y = 155 - h;
                      return <rect key={i} x={x} y={y} width="12" height={h} rx="1.5"/>;
                    })}
                  </g>
                  <g fill="var(--fg-3)" fontSize="10" fontFamily="var(--font-mono)">
                    <text x="44" y="172">Apr 7</text><text x="296" y="172">Apr 22</text>
                    <text x="588" y="172" textAnchor="end">May 6</text>
                  </g>
                </svg>
              </div>
            </div>

            <div className="card">
              <div className="card__head"><h3 className="card__title">Models used</h3><span className="card__sub">last 7d</span></div>
              <div className="card__body" style={{ paddingTop: 8 }}>
                <div className="barlist">
                  {[
                    { name: 'claude-sonnet-4.5', spend: '$3,108', bar: 0 },
                    { name: 'gemini-2.5-pro', spend: '$1,920', bar: 38 },
                    { name: 'claude-haiku-4.5', spend: '$891', bar: 62 },
                    { name: 'text-embedding-3-small', spend: '$284', bar: 80 },
                    { name: 'ollama/llama-3.1-70b', spend: '$0 (BYO)', bar: 91 },
                  ].map(m => (
                    <div key={m.name} className="row">
                      <div className="lbl"><span className="name">{m.name}</span><span className="bar"><i style={{ right: `${m.bar}%` }}></i></span></div>
                      <div className="num">{m.spend}</div>
                    </div>
                  ))}
                </div>
              </div>
            </div>
          </div>

          <div className="split-3">
            <div className="card">
              <div className="card__head"><h3 className="card__title">Cache breakdown</h3></div>
              <div className="card__body">
                <div className="dl">
                  <dt>Hit rate</dt><dd>42%</dd>
                  <dt>Exact match</dt><dd>17%</dd>
                  <dt>Semantic match</dt><dd>25%</dd>
                  <dt>Avg similarity</dt><dd>0.939</dd>
                  <dt>Tokens saved</dt><dd>21.8M</dd>
                  <dt>$ saved</dt><dd>$1,084</dd>
                </div>
              </div>
            </div>
            <div className="card">
              <div className="card__head"><h3 className="card__title">Top callers</h3><span className="card__sub">by spend</span></div>
              <div className="card__body" style={{ padding: 0 }}>
                <table className="tbl">
                  <tbody>
                    <tr><td><span className="mono">rag-indexer-v3</span></td><td className="num mono">$2,841</td></tr>
                    <tr><td><span className="mono">pr-review-bot</span></td><td className="num mono">$1,718</td></tr>
                    <tr><td><span className="mono">eval-runner</span></td><td className="num mono">$881</td></tr>
                    <tr><td><span className="mono">jupyter-notebook</span></td><td className="num mono">$612</td></tr>
                    <tr><td><span className="mono">ci-tests</span></td><td className="num mono">$108</td></tr>
                  </tbody>
                </table>
              </div>
            </div>
            <div className="card">
              <div className="card__head"><h3 className="card__title">Recent errors</h3><span className="card__sub">last 24h</span></div>
              <div className="card__body" style={{ padding: 0 }}>
                <table className="tbl">
                  <tbody>
                    <tr><td className="mono">14:42</td><td><span className="pill pill--bad">429</span></td><td><span className="mono">claude-sonnet-4.5</span></td></tr>
                    <tr><td className="mono">11:18</td><td><span className="pill pill--bad">502</span></td><td><span className="mono">gemini-2.5-pro</span></td></tr>
                    <tr><td className="mono">09:54</td><td><span className="pill pill--warn">timeout</span></td><td><span className="mono">claude-sonnet-4.5</span></td></tr>
                    <tr><td className="mono">06:21</td><td><span className="pill pill--bad">401</span></td><td><span className="muted">expired key</span></td></tr>
                  </tbody>
                </table>
              </div>
            </div>
          </div>
        </>
      )}

      {tab === 'keys' && (
        <div className="card">
          <div className="card__head">
            <h3 className="card__title">API keys</h3>
            <span className="card__sub">14 active · 3 expiring within 30 days</span>
            <div className="card__actions">
              <button className="btn btn--sm">Rotate all</button>
              <button className="btn btn--primary btn--sm">+ Issue key</button>
            </div>
          </div>
          <div className="card__body" style={{ padding: 0 }}>
            <table className="tbl">
              <thead>
                <tr><th>Name / scope</th><th>Key</th><th>Created by</th><th>Last used</th><th className="num">Calls (7d)</th><th>Expires</th><th>Status</th><th></th></tr>
              </thead>
              <tbody>
                {t.keys.map(k => (
                  <tr key={k.name}>
                    <td><div className="cell-2"><strong>{k.name}</strong><span className="lo">scope: {k.scope}</span></div></td>
                    <td><span className="mono">{k.key}</span></td>
                    <td>{k.createdBy}</td>
                    <td>{k.lastUsed}</td>
                    <td className="num mono">{k.calls7d}</td>
                    <td>{k.expires}</td>
                    <td>
                      {k.status === 'active' && <span className="pill pill--good"><span className="dot"></span>active</span>}
                      {k.status === 'expiring' && <span className="pill pill--warn"><span className="dot"></span>expiring</span>}
                      {k.status === 'revoke_pending' && <span className="pill pill--bad"><span className="dot"></span>revoke pending</span>}
                    </td>
                    <td><button className="btn btn--sm btn--ghost">⋯</button></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {tab === 'policies' && (
        <div>
          <div className="split-2" style={{ marginBottom: 16 }}>
            <div className="card">
              <div className="card__head"><h3 className="card__title">Cache policy</h3><div className="card__actions"><button className="btn btn--sm">Edit</button></div></div>
              <div className="card__body">
                <div className="dl">
                  <dt>Status</dt><dd><span className="pill pill--good"><span className="dot"></span>Enabled</span></dd>
                  <dt>TTL</dt><dd>24 hours</dd>
                  <dt>Similarity threshold</dt><dd>0.94 <span className="muted">(stricter than default 0.92)</span></dd>
                  <dt>Embedding model</dt><dd className="mono">text-embedding-3-small</dd>
                  <dt>Opt-out paths</dt><dd className="mono">/v1/chat/completions?stream=true (when temp&gt;0.4)</dd>
                </div>
              </div>
            </div>
            <div className="card">
              <div className="card__head"><h3 className="card__title">Rate limits</h3><div className="card__actions"><button className="btn btn--sm">Edit</button></div></div>
              <div className="card__body">
                <div className="dl">
                  <dt>Tier</dt><dd>Standard</dd>
                  <dt>Requests / min</dt><dd>240 <span className="muted">(per team, all models)</span></dd>
                  <dt>Tokens / min</dt><dd>1.2M input · 600K output</dd>
                  <dt>Concurrent streams</dt><dd>32</dd>
                  <dt>Burst</dt><dd>2× for 30s</dd>
                </div>
              </div>
            </div>
          </div>
          <div className="split-2">
            <div className="card">
              <div className="card__head"><h3 className="card__title">Allowed models</h3><div className="card__actions"><button className="btn btn--sm">Edit</button></div></div>
              <div className="card__body" style={{ padding: 0 }}>
                <table className="tbl">
                  <thead><tr><th>Model</th><th>Provider</th><th>Tier</th><th>Fallback</th></tr></thead>
                  <tbody>
                    <tr><td className="mono">claude-sonnet-4.5</td><td>Anthropic</td><td><span className="pill pill--info">prod</span></td><td className="mono">gemini-2.5-pro</td></tr>
                    <tr><td className="mono">claude-haiku-4.5</td><td>Anthropic</td><td><span className="pill pill--info">prod</span></td><td>—</td></tr>
                    <tr><td className="mono">gemini-2.5-pro</td><td>Google</td><td><span className="pill pill--info">prod</span></td><td className="mono">claude-sonnet-4.5</td></tr>
                    <tr><td className="mono">text-embedding-3-small</td><td>OpenAI</td><td><span className="pill">embed</span></td><td>—</td></tr>
                    <tr><td className="mono">ollama/llama-3.1-70b</td><td>BYO · ollama-eu-1</td><td><span className="pill">dev</span></td><td>—</td></tr>
                  </tbody>
                </table>
              </div>
            </div>
            <div className="card">
              <div className="card__head"><h3 className="card__title">Budget &amp; alerts</h3><div className="card__actions"><button className="btn btn--sm">Edit</button></div></div>
              <div className="card__body">
                <div className="dl">
                  <dt>Monthly cap</dt><dd>$9,150</dd>
                  <dt>Soft alert at</dt><dd>70% ($6,405) <span className="pill pill--warn">tripped May 4</span></dd>
                  <dt>Hard cap action</dt><dd>Throttle to 50% rate</dd>
                  <dt>Notify</dt><dd>a.kowalski, platform-eng@simcorp.com</dd>
                  <dt>Chargeback code</dt><dd className="mono">CC-4419-PLATFORM</dd>
                </div>
              </div>
            </div>
          </div>
        </div>
      )}

      {tab === 'members' && (
        <div className="card">
          <div className="card__head">
            <h3 className="card__title">Members</h3>
            <span className="card__sub">18 · synced from Entra group <span className="mono">simcorp-platform-eng</span></span>
            <div className="card__actions"><button className="btn btn--sm">Sync now</button><button className="btn btn--primary btn--sm">+ Add</button></div>
          </div>
          <div className="card__body" style={{ padding: 0 }}>
            <table className="tbl">
              <thead><tr><th>Name</th><th>Email</th><th>Role</th><th>Joined</th><th>Last active</th><th></th></tr></thead>
              <tbody>
                {t.members.map((m: { name: string; email: string; initials: string; color: string; role: string; joined: string; lastActive: string }) => (
                  <tr key={m.email}>
                    <td><div className="gap-2"><span className="avatar" style={{ background: m.color }}>{m.initials}</span> {m.name}</div></td>
                    <td>{m.email}</td>
                    <td>
                      {m.role === 'Owner' ? <span className="pill pill--info">Owner</span> :
                       m.role === 'Maintainer' ? <span className="pill">Maintainer</span> :
                       <span className="pill">Member</span>}
                    </td>
                    <td>{m.joined}</td>
                    <td>{m.lastActive}</td>
                    <td><button className="btn btn--sm btn--ghost">⋯</button></td>
                  </tr>
                ))}
                <tr><td colSpan={6} style={{ textAlign: 'center', color: 'var(--fg-3)', padding: 14 }}>
                  <a href="#" className="muted">Show 12 more members</a>
                </td></tr>
              </tbody>
            </table>
          </div>
        </div>
      )}

      {tab === 'audit' && (
        <div className="card">
          <div className="card__body">
            <p className="muted">Filtered audit log for {t.name}. <Link href="/admin/audit" style={{ color: 'var(--sc-link)' }}>Open full audit log →</Link></p>
          </div>
        </div>
      )}
    </section>
  );
}
