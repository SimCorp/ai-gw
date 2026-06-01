'use client';

import React, { useState, useEffect } from 'react';
import { useQuery } from '@tanstack/react-query';
import { LoadingState, ErrorState } from '../_components/PageStates';

const BASE = process.env.NEXT_PUBLIC_ADMIN_API ?? 'http://localhost:8005';

interface ExtraEnvVar {
  env_var: string;
  label: string;
  placeholder: string;
}

interface Provider {
  name: string;
  icon: string;
  env_var: string;
  models: string[];
  litellm_model_names: string[];
  test_model: string;
  is_set: boolean;
  description?: string;
  extra_env_vars?: ExtraEnvVar[];
  docs_url?: string;
  key_placeholder?: string;
}

interface ProvidersResponse {
  providers: Provider[];
}

interface EmbeddingTestResult {
  ok: boolean;
  latency_ms?: number;
  dim?: number;
  model?: string;
  error?: string;
}

interface TestResult {
  ok: boolean;
  latency_ms?: number;
  reply?: string;
  model?: string;
  error?: string;
  embedding?: EmbeddingTestResult;
}

interface DiscoveredModel {
  id: string;
  name: string;
  registered: boolean;
  registry_id: string | null;
  enabled: boolean | null;
}

const PROVIDER_COLORS: Record<string, string> = {
  'Anthropic': '#D97757',
  'OpenAI': '#10A37F',
  'Google': '#4285F4',
  'GitHub Copilot': '#24292F',
  'Azure AI Foundry': '#0078D4',
  'GitHub Models': '#1A1D31',
};

function getProviderColor(name: string): string {
  for (const [key, color] of Object.entries(PROVIDER_COLORS)) {
    if (name.toLowerCase().includes(key.toLowerCase())) return color;
  }
  return '#555';
}

function ProviderCard({ p, onSaved }: { p: Provider; onSaved: () => void }) {
  const [keyInput, setKeyInput] = useState('');
  const [extraInputs, setExtraInputs] = useState<Record<string, string>>(
    () => Object.fromEntries((p.extra_env_vars ?? []).map(e => [e.env_var, '']))
  );
  const [saving, setSaving] = useState(false);
  const [saveMsg, setSaveMsg] = useState('');
  const [testing, setTesting] = useState(false);
  const [testResult, setTestResult] = useState<TestResult | null>(null);
  const [discovering, setDiscovering] = useState(false);
  const [discoveredModels, setDiscoveredModels] = useState<DiscoveredModel[] | null>(null);
  const [discoverError, setDiscoverError] = useState('');
  // action per model: 'skip' | 'enable' | 'disable' | 'keep'
  const [modelActions, setModelActions] = useState<Record<string, string>>({});
  const [applying, setApplying] = useState(false);
  const [applyMsg, setApplyMsg] = useState('');

  async function saveKey() {
    if (!keyInput.trim()) return;
    setSaving(true);
    setSaveMsg('');
    try {
      const payload: Record<string, string> = { [p.env_var]: keyInput.trim() };
      for (const [k, v] of Object.entries(extraInputs)) {
        if (v.trim()) payload[k] = v.trim();
      }
      const res = await fetch(BASE + '/api/settings/providers', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });
      if (res.ok) {
        setSaveMsg('Saved');
        setKeyInput('');
        setExtraInputs(Object.fromEntries((p.extra_env_vars ?? []).map(e => [e.env_var, ''])));
        onSaved();
      } else {
        setSaveMsg('Error saving');
      }
    } catch {
      setSaveMsg('Error saving');
    } finally {
      setSaving(false);
    }
  }

  async function testKey() {
    setTesting(true);
    setTestResult(null);
    try {
      const res = await fetch(`${BASE}/ui/settings/test/${p.env_var}`, {
        method: 'POST',
      });
      const json: TestResult = await res.json();
      setTestResult(json);
    } catch {
      setTestResult({ ok: false, error: 'Request failed' });
    } finally {
      setTesting(false);
    }
  }

  async function fetchModels() {
    setDiscovering(true);
    setDiscoverError('');
    setApplyMsg('');
    try {
      const res = await fetch(`${BASE}/api/settings/providers/${p.env_var}/discover`, {
        method: 'POST',
      });
      const json = await res.json();
      if (json.ok) {
        setDiscoveredModels(json.models);
        // Default all to 'disable'; preserve existing user selections
        setModelActions(prev => {
          const next: Record<string, string> = {};
          for (const m of json.models as DiscoveredModel[]) {
            next[m.id] = prev[m.id] ?? 'disable';
          }
          return next;
        });
      } else {
        setDiscoverError(json.error || 'Discovery failed');
      }
    } catch {
      setDiscoverError('Request failed');
    } finally {
      setDiscovering(false);
    }
  }

  async function applyChanges() {
    if (!discoveredModels) return;
    setApplying(true);
    setApplyMsg('');
    let enabled = 0, disabled = 0, fail = 0;
    for (const m of discoveredModels) {
      const action = modelActions[m.id] ?? 'disable';
      const isCurrentlyEnabled = m.registered && m.enabled !== false;
      if (action === 'enable' && !isCurrentlyEnabled) {
        if (!m.registered) {
          try {
            const res = await fetch(BASE + '/api/models', {
              method: 'POST',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify({ model_id: m.id, name: m.name, provider: p.name, enabled: true }),
            });
            if (res.ok) enabled++; else fail++;
          } catch { fail++; }
        } else if (m.registry_id) {
          try {
            const res = await fetch(`${BASE}/api/models/${m.registry_id}`, {
              method: 'PATCH',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify({ enabled: true }),
            });
            if (res.ok) enabled++; else fail++;
          } catch { fail++; }
        }
      } else if (action === 'disable' && isCurrentlyEnabled && m.registry_id) {
        try {
          const res = await fetch(`${BASE}/api/models/${m.registry_id}`, {
            method: 'PATCH',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ enabled: false }),
          });
          if (res.ok) disabled++; else fail++;
        } catch { fail++; }
      }
    }
    const parts = [];
    if (enabled) parts.push(`${enabled} enabled`);
    if (disabled) parts.push(`${disabled} disabled`);
    if (fail) parts.push(`${fail} failed`);
    setApplyMsg(parts.join(', ') || 'No changes');
    await fetchModels();
    setApplying(false);
  }

  const pendingChanges = discoveredModels?.filter(m => {
    const action = modelActions[m.id] ?? 'disable';
    const isCurrentlyEnabled = m.registered && m.enabled !== false;
    return (action === 'enable' && !isCurrentlyEnabled) || (action === 'disable' && isCurrentlyEnabled);
  }).length ?? 0;

  const logoColor = getProviderColor(p.name);

  return (
    <div className="prov-card">
      <div className="prov-card__head">
        <div className="prov-logo" style={{ background: logoColor, fontSize: 20 }}>{p.icon}</div>
        <div style={{ flex: 1 }}>
          <div style={{ fontWeight: 600, fontSize: 13.5 }}>{p.name}</div>
          <div className="muted" style={{ fontSize: 12 }}>
            {p.models.length} model{p.models.length !== 1 ? 's' : ''} · {p.env_var}
          </div>
        </div>
        {p.is_set
          ? <span className="pill pill--good"><span className="dot"></span>Key configured</span>
          : <span className="pill pill--warn"><span className="dot"></span>No key set</span>
        }
      </div>
      <div className="prov-card__body">
        <div className="prov-stat" style={{ gridColumn: '1 / -1' }}>
          <span className="prov-stat__l">Models</span>
          <span className="prov-stat__v" style={{ fontSize: 12, fontWeight: 400, display: 'flex', gap: 4, flexWrap: 'wrap' }}>
            {p.models.map(m => <span key={m} className="tag">{m}</span>)}
          </span>
        </div>
        {p.description && (
          <div className="prov-stat" style={{ gridColumn: '1 / -1' }}>
            <span className="muted" style={{ fontSize: 11.5 }}>{p.description}</span>
          </div>
        )}
      </div>
      <div className="prov-card__foot" style={{ flexDirection: 'column', alignItems: 'stretch', gap: 8 }}>
        {(p.extra_env_vars ?? []).map(ev => (
          <div key={ev.env_var} style={{ display: 'flex', flexDirection: 'column', gap: 3 }}>
            <label style={{ fontSize: 11, color: 'var(--fg-2)', fontWeight: 500 }}>{ev.label}</label>
            <input
              type="text"
              className="search"
              placeholder={ev.placeholder}
              value={extraInputs[ev.env_var] ?? ''}
              onChange={e => setExtraInputs(prev => ({ ...prev, [ev.env_var]: e.target.value }))}
              style={{ height: 30, padding: '0 10px', fontSize: 12, background: 'var(--surface-2)', border: '1px solid var(--rule)', borderRadius: 6 }}
            />
          </div>
        ))}
        <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
          <input
            type="password"
            autoComplete="off"
            className="search"
            placeholder={p.is_set ? `Replace key… ${p.key_placeholder ? `(${p.key_placeholder})` : ''}`.trim() : (p.key_placeholder ?? 'Paste API key…')}
            value={keyInput}
            onChange={e => setKeyInput(e.target.value)}
            style={{ flex: 1, height: 30, padding: '0 10px', fontSize: 12 }}
          />
          <button className="btn btn--sm btn--primary" onClick={saveKey} disabled={saving || !keyInput.trim()}>
            {saving ? 'Saving…' : 'Save key'}
          </button>
          {p.is_set && (
            <button className="btn btn--sm" onClick={testKey} disabled={testing}>
              {testing ? 'Testing…' : 'Test'}
            </button>
          )}
        </div>
        {p.is_set && (
          <div style={{ borderTop: '1px solid var(--rule)', paddingTop: 8, display: 'flex', alignItems: 'center', gap: 8 }}>
            <span style={{ fontSize: 10.5, fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.05em', color: 'var(--fg-3)' }}>Model registry</span>
            <button className="btn btn--sm" onClick={fetchModels} disabled={discovering} style={{ marginLeft: 'auto' }}>
              {discovering ? 'Fetching…' : 'Fetch models'}
            </button>
          </div>
        )}
        {saveMsg && <span style={{ fontSize: 12, color: saveMsg === 'Saved' ? 'var(--good)' : 'var(--bad)' }}>{saveMsg}</span>}
        {testResult && (
          <span style={{ fontSize: 12, color: testResult.ok ? 'var(--good)' : 'var(--bad)' }}>
            {testResult.ok
              ? `Chat: Pass · ${testResult.latency_ms}ms · ${testResult.model}`
              : `Chat: Fail: ${testResult.error}`}
          </span>
        )}
        {testResult?.embedding && (
          <span style={{ fontSize: 12, color: testResult.embedding.ok ? 'var(--good)' : 'var(--bad)' }}>
            {testResult.embedding.ok
              ? `Embedding: Pass · ${testResult.embedding.latency_ms}ms · ${testResult.embedding.model} · dim ${testResult.embedding.dim}`
              : `Embedding: Fail: ${testResult.embedding.error}`}
          </span>
        )}
        {discoverError && (
          <span style={{ fontSize: 12, color: 'var(--bad)' }}>Discovery failed: {discoverError}</span>
        )}
        {discoveredModels && (
          <div className="discover-panel">
            <div style={{ fontSize: 11.5, fontWeight: 600, color: 'var(--fg-2)', marginBottom: 6 }}>
              {discoveredModels.length} models available from {p.name}
            </div>
            <div className="discover-list">
              {discoveredModels.map(m => {
                const action = modelActions[m.id] ?? 'disable';
                return (
                  <div key={m.id} className="discover-item">
                    <span className="discover-model-id">{m.id}</span>
                    {m.name !== m.id && <span style={{ fontSize: 11, color: 'var(--fg-2)', marginLeft: 6, flex: 1 }}>{m.name}</span>}
                    <span style={{ flex: 1 }} />
                    <select
                      className="discover-action-select"
                      value={action}
                      onChange={e => setModelActions(prev => ({ ...prev, [m.id]: e.target.value }))}
                    >
                      <option value="disable">Disable</option>
                      <option value="enable">Enable</option>
                    </select>
                  </div>
                );
              })}
            </div>
            <div style={{ display: 'flex', gap: 8, alignItems: 'center', marginTop: 8 }}>
              <button
                className="btn btn--sm btn--primary"
                onClick={applyChanges}
                disabled={applying || pendingChanges === 0}
              >
                {applying ? 'Applying…' : `Apply ${pendingChanges} change${pendingChanges !== 1 ? 's' : ''}`}
              </button>
            </div>
            {applyMsg && (
              <span style={{ fontSize: 12, color: applyMsg.includes('failed') ? 'var(--bad)' : 'var(--good)', marginTop: 4 }}>
                {applyMsg}
              </span>
            )}
          </div>
        )}
        {p.docs_url && (
          <div style={{ marginTop: 2 }}>
            <a
              href={p.docs_url}
              target="_blank"
              rel="noopener noreferrer"
              style={{ fontSize: 11.5, color: 'var(--fg-2)', textDecoration: 'none' }}
              onMouseEnter={e => (e.currentTarget.style.color = 'var(--fg-1)')}
              onMouseLeave={e => (e.currentTarget.style.color = 'var(--fg-2)')}
            >
              Docs ↗
            </a>
          </div>
        )}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Auto-Drive Routing section
// ---------------------------------------------------------------------------

interface GatewayInfo {
  autoroute: {
    enabled: boolean;
    candidates?: string[];
    current_model?: string | null;
    score?: number | null;
  };
}

interface ModelScore {
  model: string;
  score: number;
}

function AutoDriveSection() {
  const [gatewayInfo, setGatewayInfo] = useState<GatewayInfo | null>(null);
  const [scores, setScores] = useState<ModelScore[]>([]);
  const [loading, setLoading] = useState(true);
  const [toggleBusy, setToggleBusy] = useState(false);
  const [candidatesInput, setCandidatesInput] = useState('');
  const [savingCandidates, setSavingCandidates] = useState(false);
  const [saveMsg, setSaveMsg] = useState('');

  async function loadGatewayInfo() {
    try {
      const res = await fetch(BASE + '/gateway-info');
      if (res.ok) {
        const json: GatewayInfo = await res.json();
        setGatewayInfo(json);
        if (json.autoroute?.candidates?.length) {
          setCandidatesInput(json.autoroute.candidates.join(', '));
        }
      }
    } catch {
      // ignore — show empty state
    } finally {
      setLoading(false);
    }
  }

  async function loadScores() {
    try {
      const res = await fetch(BASE + '/config');
      if (res.ok) {
        const cfg = await res.json();
        // config blob may have a model_scores map
        const raw = cfg?.model_scores;
        if (raw && typeof raw === 'object') {
          setScores(
            Object.entries(raw as Record<string, number>).map(([model, score]) => ({ model, score }))
          );
        }
      }
    } catch {
      // ignore
    }
  }

  useEffect(() => {
    loadGatewayInfo();
    loadScores();
  }, []);

  async function toggleAutoroute() {
    if (!gatewayInfo) return;
    const newVal = !gatewayInfo.autoroute.enabled;
    setToggleBusy(true);
    try {
      await fetch(BASE + '/config/notify', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ key: 'autoroute_enabled', value: String(newVal) }),
      });
      setGatewayInfo(prev =>
        prev ? { ...prev, autoroute: { ...prev.autoroute, enabled: newVal } } : prev
      );
    } catch {
      // silently fail
    } finally {
      setToggleBusy(false);
    }
  }

  async function saveCandidates() {
    setSavingCandidates(true);
    setSaveMsg('');
    try {
      const res = await fetch(BASE + '/config/notify', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ key: 'autoroute_models', value: candidatesInput.trim() }),
      });
      if (res.ok) {
        setSaveMsg('Saved');
      } else {
        setSaveMsg('Error saving');
      }
    } catch {
      setSaveMsg('Error saving');
    } finally {
      setSavingCandidates(false);
      setTimeout(() => setSaveMsg(''), 3000);
    }
  }

  const isEnabled = gatewayInfo?.autoroute?.enabled ?? false;

  return (
    <div style={{ marginTop: 40 }}>
      <div style={{
        display: 'flex', justifyContent: 'space-between', alignItems: 'center',
        marginBottom: 16, paddingBottom: 12, borderBottom: '1px solid var(--rule)',
      }}>
        <div>
          <h2 style={{ margin: 0, fontSize: 16, fontWeight: 700 }}>Auto-Drive Routing</h2>
          <p style={{ margin: '4px 0 0', fontSize: 12.5, color: 'var(--fg-2)' }}>
            Automatically route requests to the best-performing model based on rolling quality scores.
          </p>
        </div>
        {loading ? (
          <span style={{ fontSize: 12, color: 'var(--fg-3)' }}>Loading…</span>
        ) : (
          <button
            className={`btn btn--sm ${isEnabled ? 'btn--primary' : 'btn--ghost'}`}
            onClick={toggleAutoroute}
            disabled={toggleBusy}
            style={{ minWidth: 90 }}
          >
            {toggleBusy ? 'Updating…' : isEnabled ? 'Enabled' : 'Disabled'}
          </button>
        )}
      </div>

      <div style={{
        display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16,
        background: 'var(--surface)', border: '1px solid var(--rule)',
        borderRadius: 'var(--radius-3)', padding: 20,
      }}>
        {/* Candidate models input */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
          <label style={{ fontSize: 12, fontWeight: 600, color: 'var(--fg-2)', textTransform: 'uppercase', letterSpacing: '0.04em' }}>
            Candidate models
          </label>
          <textarea
            value={candidatesInput}
            onChange={e => setCandidatesInput(e.target.value)}
            placeholder="gpt-4o, claude-3-5-sonnet, gemini-1.5-pro"
            rows={4}
            style={{
              padding: '8px 10px', fontSize: 12.5,
              background: 'var(--surface-2)', border: '1px solid var(--rule)',
              borderRadius: 6, color: 'var(--fg-1)', outline: 'none',
              resize: 'vertical', fontFamily: 'var(--font-mono)',
            }}
          />
          <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            <button
              className="btn btn--sm btn--primary"
              onClick={saveCandidates}
              disabled={savingCandidates || !candidatesInput.trim()}
            >
              {savingCandidates ? 'Saving…' : 'Save candidates'}
            </button>
            {saveMsg && (
              <span style={{ fontSize: 12, color: saveMsg === 'Saved' ? 'var(--good)' : 'var(--bad)' }}>
                {saveMsg}
              </span>
            )}
          </div>
          <p style={{ margin: 0, fontSize: 11.5, color: 'var(--fg-3)' }}>
            Comma-separated list of model IDs eligible for auto-routing.
          </p>
        </div>

        {/* Model score gauges */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
          <div style={{ fontSize: 12, fontWeight: 600, color: 'var(--fg-2)', textTransform: 'uppercase', letterSpacing: '0.04em' }}>
            Model scores
          </div>
          {scores.length === 0 ? (
            <div style={{
              padding: '20px 14px', border: '1px solid var(--rule)', borderRadius: 6,
              background: 'var(--surface-2)', fontSize: 12.5, color: 'var(--fg-3)',
              textAlign: 'center',
            }}>
              Pending data — scores will appear once Auto-Drive collects request history.
            </div>
          ) : (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
              {scores.map(({ model, score }) => (
                <div key={model} style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                    <span style={{ fontSize: 12, fontFamily: 'var(--font-mono)', color: 'var(--fg-1)' }}>{model}</span>
                    <span style={{ fontSize: 11.5, color: 'var(--fg-2)', fontVariantNumeric: 'tabular-nums' }}>
                      {(score * 100).toFixed(1)}%
                    </span>
                  </div>
                  <div style={{
                    height: 6, borderRadius: 3, background: 'var(--surface-2)',
                    border: '1px solid var(--rule)', overflow: 'hidden',
                  }}>
                    <div style={{
                      height: '100%',
                      width: `${Math.min(100, score * 100)}%`,
                      background: score >= 0.8 ? 'var(--green)' : score >= 0.5 ? 'var(--teal)' : 'var(--blue)',
                      borderRadius: 3,
                      transition: 'width 0.4s ease',
                    }} />
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

export default function ProvidersPage() {
  const { data, isLoading, isError, error, refetch } = useQuery<ProvidersResponse>({
    queryKey: ['providers'],
    queryFn: () => fetch(BASE + '/api/settings/providers').then(r => r.json()),
  });

  if (isLoading) return <section className="page"><LoadingState rows={6} /></section>;
  if (isError) return <section className="page"><ErrorState error={error as Error} retry={() => refetch()} /></section>;

  const providers = data?.providers ?? [];
  const configuredCount = providers.filter(p => p.is_set).length;

  return (
    <section className="page">
      <div className="page__head">
        <div>
          <h1 className="page__title">Providers</h1>
          <p className="page__sub">{providers.length} upstream providers · {configuredCount} key{configuredCount !== 1 ? 's' : ''} configured · LiteLLM-routed</p>
        </div>
        <div className="page__actions">
          <button className="btn" onClick={() => refetch()}>Refresh</button>
        </div>
      </div>

      <div className="prov">
        {providers.map(p => (
          <ProviderCard key={p.env_var} p={p} onSaved={() => refetch()} />
        ))}
      </div>

      <AutoDriveSection />

      <style>{`
        .prov {
          display: grid;
          grid-template-columns: repeat(2, 1fr);
          gap: var(--gap-card);
          margin-top: 16px;
        }
        .prov-card { background: var(--surface); border: 1px solid var(--rule); border-radius: var(--radius-3); overflow: hidden; }
        .prov-card__head { display:flex; align-items:center; gap:12px; padding: 14px 16px; border-bottom: 1px solid var(--rule); }
        .prov-logo { width: 36px; height: 36px; border-radius: 8px; display:grid; place-items:center; color:#fff; font-weight: 700; font-size: 13px; flex-shrink: 0; }
        .prov-card__body { padding: 14px 16px; display: grid; grid-template-columns: 1fr 1fr; gap: 8px 14px; }
        .prov-stat { display:flex; flex-direction:column; gap:2px; }
        .prov-stat__l { font-size: 10.5px; color: var(--fg-2); text-transform: uppercase; letter-spacing: 0.04em; font-weight: 500; }
        .prov-stat__v { font-size: 14.5px; font-weight: 600; font-variant-numeric: tabular-nums; }
        .prov-card__foot { padding: 10px 16px; border-top: 1px solid var(--rule); background: var(--surface-2); display:flex; align-items:center; gap: 8px; font-size: 11.5px; color: var(--fg-2); }
        .prov-card__foot .mono { color: var(--fg-1); }
        .tag { display: inline-block; background: var(--surface-soft); border: 1px solid var(--rule); border-radius: 4px; padding: 1px 6px; font-size: 11px; font-family: var(--font-mono); }
        .discover-panel { background: var(--surface); border: 1px solid var(--rule); border-radius: 6px; padding: 10px 12px; margin-top: 4px; }
        .discover-list { max-height: 220px; overflow-y: auto; display: flex; flex-direction: column; gap: 2px; }
        .discover-item { display: flex; align-items: center; padding: 4px 6px; border-radius: 4px; font-size: 12px; gap: 4px; }
        .discover-item:hover { background: var(--surface-2); }
        .discover-model-id { font-family: var(--font-mono); font-size: 11.5px; white-space: nowrap; }
        .discover-action-select { font-size: 11px; background: var(--surface); border: 1px solid var(--rule); border-radius: 4px; padding: 2px 6px; color: var(--fg-1); cursor: pointer; flex-shrink: 0; }
      `}</style>
    </section>
  );
}
