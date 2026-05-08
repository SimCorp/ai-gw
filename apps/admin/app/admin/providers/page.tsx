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
        </div>
        {saveMsg && <span style={{ fontSize: 12, color: saveMsg === 'Saved' ? 'var(--good)' : 'var(--bad)' }}>{saveMsg}</span>}
        {testResult && (
          <span style={{ fontSize: 12, color: testResult.ok ? 'var(--good)' : 'var(--bad)' }}>
            {testResult.ok
              ? `Pass · ${testResult.latency_ms}ms · ${testResult.model}`
              : `Fail: ${testResult.error}`}
          </span>
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
      `}</style>
    </section>
  );
}
