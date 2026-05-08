'use client';

import React, { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { LoadingState, ErrorState } from '../_components/PageStates';

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
}

interface ProvidersResponse {
  providers: Provider[];
}

interface TestResult {
  ok: boolean;
  latency_ms?: number;
  reply?: string;
  model?: string;
  error?: string;
}

interface DiscoveredModel {
  id: string;
  name: string;
  registered: boolean;
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
  const [selectedModels, setSelectedModels] = useState<Set<string>>(new Set());
  const [enabling, setEnabling] = useState(false);
  const [enableMsg, setEnableMsg] = useState('');

  async function saveKey() {
    if (!keyInput.trim()) return;
    setSaving(true);
    setSaveMsg('');
    try {
      const payload: Record<string, string> = { [p.env_var]: keyInput.trim() };
      for (const [k, v] of Object.entries(extraInputs)) {
        if (v.trim()) payload[k] = v.trim();
      }
      const res = await fetch('http://localhost:8005/api/settings/providers', {
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
      const res = await fetch(`http://localhost:8005/ui/settings/test/${p.env_var}`, {
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
    setDiscoveredModels(null);
    setDiscoverError('');
    setSelectedModels(new Set());
    setEnableMsg('');
    try {
      const res = await fetch(`http://localhost:8005/api/settings/providers/${p.env_var}/discover`, {
        method: 'POST',
      });
      const json = await res.json();
      if (json.ok) {
        setDiscoveredModels(json.models);
        // Pre-select unregistered models
        const pre = new Set<string>(json.models.filter((m: DiscoveredModel) => !m.registered).map((m: DiscoveredModel) => m.id));
        setSelectedModels(pre);
      } else {
        setDiscoverError(json.error || 'Discovery failed');
      }
    } catch {
      setDiscoverError('Request failed');
    } finally {
      setDiscovering(false);
    }
  }

  function toggleModel(id: string) {
    setSelectedModels(prev => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  async function enableSelected() {
    if (selectedModels.size === 0) return;
    setEnabling(true);
    setEnableMsg('');
    let ok = 0;
    let fail = 0;
    for (const id of selectedModels) {
      const model = discoveredModels?.find(m => m.id === id);
      if (!model) continue;
      try {
        const res = await fetch('http://localhost:8005/api/models', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            model_id: id,
            name: model.name,
            provider: p.name,
            enabled: true,
          }),
        });
        if (res.ok) ok++;
        else fail++;
      } catch {
        fail++;
      }
    }
    setEnableMsg(fail === 0 ? `Enabled ${ok} model${ok !== 1 ? 's' : ''}` : `${ok} enabled, ${fail} failed`);
    // Refresh discovered list to update registered status
    await fetchModels();
    setEnabling(false);
  }

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
            className="search"
            placeholder={p.is_set ? 'Replace key…' : 'Paste API key…'}
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
          {p.is_set && (
            <button className="btn btn--sm" onClick={fetchModels} disabled={discovering}>
              {discovering ? 'Fetching…' : 'Fetch models'}
            </button>
          )}
        </div>
        {saveMsg && <span style={{ fontSize: 12, color: saveMsg === 'Saved' ? 'var(--good)' : 'var(--bad)' }}>{saveMsg}</span>}
        {testResult && (
          <span style={{ fontSize: 12, color: testResult.ok ? 'var(--good)' : 'var(--bad)' }}>
            {testResult.ok
              ? `Pass · ${testResult.latency_ms}ms · ${testResult.model}`
              : `Fail: ${testResult.error}`}
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
              {discoveredModels.map(m => (
                <label key={m.id} className={`discover-item${m.registered ? ' discover-item--done' : ''}`}>
                  <input
                    type="checkbox"
                    checked={selectedModels.has(m.id)}
                    onChange={() => !m.registered && toggleModel(m.id)}
                    disabled={m.registered}
                    style={{ marginRight: 7, accentColor: logoColor }}
                  />
                  <span className="discover-model-id">{m.id}</span>
                  {m.name !== m.id && <span style={{ fontSize: 11, color: 'var(--fg-2)', marginLeft: 6 }}>{m.name}</span>}
                  {m.registered && <span style={{ fontSize: 10.5, color: 'var(--good)', marginLeft: 'auto' }}>Already enabled</span>}
                </label>
              ))}
            </div>
            <div style={{ display: 'flex', gap: 8, alignItems: 'center', marginTop: 8 }}>
              <button
                className="btn btn--sm btn--primary"
                onClick={enableSelected}
                disabled={enabling || selectedModels.size === 0}
              >
                {enabling ? 'Enabling…' : `Enable ${selectedModels.size} selected`}
              </button>
              <button
                className="btn btn--sm"
                onClick={() => {
                  const unregistered = discoveredModels.filter(m => !m.registered).map(m => m.id);
                  setSelectedModels(new Set(unregistered));
                }}
                style={{ fontSize: 11 }}
              >
                Select all new
              </button>
              <button
                className="btn btn--sm"
                onClick={() => setSelectedModels(new Set())}
                style={{ fontSize: 11 }}
              >
                Clear
              </button>
            </div>
            {enableMsg && (
              <span style={{ fontSize: 12, color: enableMsg.includes('failed') ? 'var(--bad)' : 'var(--good)', marginTop: 4 }}>
                {enableMsg}
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

export default function ProvidersPage() {
  const { data, isLoading, isError, error, refetch } = useQuery<ProvidersResponse>({
    queryKey: ['providers'],
    queryFn: () => fetch('http://localhost:8005/api/settings/providers').then(r => r.json()),
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
        .discover-item { display: flex; align-items: center; padding: 4px 6px; border-radius: 4px; cursor: pointer; font-size: 12px; transition: background 0.1s; }
        .discover-item:hover { background: var(--surface-2); }
        .discover-item--done { opacity: 0.6; cursor: default; }
        .discover-model-id { font-family: var(--font-mono); font-size: 11.5px; }
      `}</style>
    </section>
  );
}
