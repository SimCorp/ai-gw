"use client";

import Link from "next/link";
import { useState, useEffect } from "react";

const LITELLM_BASE = process.env.NEXT_PUBLIC_LITELLM_BASE_URL ?? "http://localhost:8080/litellm";
const LITELLM_KEY = process.env.NEXT_PUBLIC_LITELLM_KEY ?? "sk-litellm-local-dev";
const ADMIN_BASE = process.env.NEXT_PUBLIC_ADMIN_BASE_URL ?? "http://localhost:8005";

interface LiteLLMModel {
  id: string;
  object: string;
  created: number;
  owned_by: string;
}

interface AdminModel {
  id: string;
  name: string;
  model_id: string;
  provider: string;
  enabled: boolean;
  created_at: string;
}

interface DisplayModel {
  id: string;
  name: string;
  provider: string;
  logoColor: string;
  logoText: string;
  inLiteLLM: boolean;
}

// Prefix checks must come before substring checks so that e.g. copilot-claude-3.5-sonnet
// is classified as GitHub Copilot rather than Anthropic.
function detectProvider(id: string): { provider: string; logoColor: string; logoText: string } {
  const lower = id.toLowerCase();
  if (lower.startsWith("copilot-"))  return { provider: "GitHub Copilot",    logoColor: "#24292F", logoText: "GH" };
  if (lower.startsWith("azure-"))    return { provider: "Azure AI Foundry",  logoColor: "#0078D4", logoText: "Az" };
  if (lower.startsWith("github-"))   return { provider: "GitHub Models",     logoColor: "#1A1D31", logoText: "GH" };
  // Azure AI Foundry serverless models — registered without "azure-" prefix
  if (lower.startsWith("phi-"))      return { provider: "Azure AI Foundry",  logoColor: "#0078D4", logoText: "Az" };
  if (lower.startsWith("deepseek-")) return { provider: "Azure AI Foundry",  logoColor: "#0078D4", logoText: "Az" };
  if (lower.startsWith("cohere-"))   return { provider: "Azure AI Foundry",  logoColor: "#0078D4", logoText: "Az" };
  if (lower.startsWith("mistral-"))  return { provider: "Azure AI Foundry",  logoColor: "#0078D4", logoText: "Az" };
  if (lower.startsWith("llama-"))    return { provider: "Azure AI Foundry",  logoColor: "#0078D4", logoText: "Az" };
  if (lower.includes("claude"))      return { provider: "Anthropic",         logoColor: "#D97757", logoText: "A"  };
  if (lower.includes("gemini"))      return { provider: "Google",            logoColor: "#4285F4", logoText: "G"  };
  if (lower.includes("gpt") || lower.includes("o1") || lower.includes("o3")) return { provider: "OpenAI", logoColor: "#10A37F", logoText: "OA" };
  if (lower === "local" || lower.includes("ollama")) return { provider: "Self-hosted", logoColor: "#1D958E", logoText: "Ol" };
  return { provider: "Other", logoColor: "#555", logoText: "?" };
}

export default function ModelsPage() {
  const [models, setModels] = useState<DisplayModel[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [activeProvider, setActiveProvider] = useState<string | null>(null);

  useEffect(() => {
    setLoading(true);

    const litellmFetch = fetch(`${LITELLM_BASE}/v1/models`, {
      headers: { Authorization: `Bearer ${LITELLM_KEY}` },
    })
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error(`LiteLLM HTTP ${r.status}`))))
      .then((data: { data: LiteLLMModel[] }) => data.data)
      .catch(() => [] as LiteLLMModel[]);

    const adminFetch = fetch(`${ADMIN_BASE}/models?enabled_only=true`)
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error(`Admin HTTP ${r.status}`))))
      .then((data: AdminModel[]) => data)
      .catch(() => [] as AdminModel[]);

    Promise.all([litellmFetch, adminFetch])
      .then(([litellmModels, adminModels]) => {
        const litellmIds = new Set(litellmModels.map((m) => m.id));
        // Build display name lookup from admin registry (model_id -> display name)
        const adminNameMap = new Map<string, string>();
        adminModels.forEach((am) => adminNameMap.set(am.model_id, am.name));

        // Models from LiteLLM (fully configured)
        const fromLiteLLM: DisplayModel[] = litellmModels.map((m) => ({
          id: m.id,
          name: adminNameMap.get(m.id) ?? m.id,
          ...detectProvider(m.id),
          inLiteLLM: true,
        }));

        // Models only in admin registry (not yet in LiteLLM config)
        const adminOnly: DisplayModel[] = adminModels
          .filter((am) => !litellmIds.has(am.model_id))
          .map((am) => ({
            id: am.model_id,
            name: am.name,
            ...detectProvider(am.model_id),
            inLiteLLM: false,
          }));

        setModels([...fromLiteLLM, ...adminOnly]);
      })
      .catch((e) => setError(String(e)))
      .finally(() => setLoading(false));
  }, []);

  // Derive unique provider list in stable insertion order
  const providers = Array.from(new Set(models.map((m) => m.provider)));

  const visibleModels = activeProvider
    ? models.filter((m) => m.provider === activeProvider)
    : models;

  // Group visible models by provider
  const grouped = providers
    .filter((p) => !activeProvider || p === activeProvider)
    .map((p) => ({ provider: p, items: visibleModels.filter((m) => m.provider === p) }))
    .filter((g) => g.items.length > 0);

  return (
    <main className="pmain">
      <style>{`
        .mgrid { display:grid; grid-template-columns:repeat(2,1fr); gap:14px; }
        .mcard { background:var(--surface); border:1px solid var(--rule); border-radius:var(--radius-3); padding:18px; display:flex; flex-direction:column; gap:10px; transition:border-color 120ms; }
        .mcard:hover { border-color:var(--accent); }
        .mcard--unconfigured { opacity:0.65; }
        .mcard__h { display:flex; align-items:flex-start; gap:12px; }
        .mcard__logo { width:36px; height:36px; border-radius:8px; flex-shrink:0; display:grid; place-items:center; color:#fff; font-weight:700; font-size:13px; }
        .mcard__name { font-family:var(--font-mono); font-weight:600; font-size:14px; }
        .mcard__prov { font-size:12px; color:var(--fg-3); }
        .mcard__foot { display:flex; gap:6px; align-items:center; padding-top:10px; border-top:1px solid var(--rule); }
        .pfilter { display:flex; gap:8px; flex-wrap:wrap; margin-bottom:20px; }
        .pfilter__btn { padding:5px 12px; border-radius:999px; border:1px solid var(--rule); background:var(--surface); font-size:12px; cursor:pointer; transition:background 120ms,border-color 120ms; }
        .pfilter__btn:hover { border-color:var(--accent); }
        .pfilter__btn--active { background:var(--accent); color:var(--accent-fg); border-color:var(--accent); }
        .pgroup__label { margin:20px 0 10px; }
        .pgroup__label:first-child { margin-top:0; }
      `}</style>

      <div className="phero">
        <div>
          <h1>Models</h1>
          <p>
            {loading
              ? "Loading available models…"
              : error
              ? "Could not load models."
              : `${models.length} model${models.length !== 1 ? "s" : ""} available. All are OpenAI-compatible — same SDK, same code.`}
          </p>
        </div>
      </div>

      {error && (
        <div className="card" style={{ borderColor: "var(--bad)", marginBottom: 16 }}>
          <div className="card__body" style={{ color: "var(--bad)", fontSize: 13 }}>
            Failed to load models: {error}
          </div>
        </div>
      )}

      {loading && (
        <div style={{ padding: 24, textAlign: "center", color: "var(--fg-3)", fontSize: 13 }}>
          Loading models from gateway…
        </div>
      )}

      {!loading && !error && (
        <>
          {providers.length > 1 && (
            <div className="pfilter">
              <button
                className={`pfilter__btn${activeProvider === null ? " pfilter__btn--active" : ""}`}
                onClick={() => setActiveProvider(null)}
              >
                All
              </button>
              {providers.map((p) => (
                <button
                  key={p}
                  className={`pfilter__btn${activeProvider === p ? " pfilter__btn--active" : ""}`}
                  onClick={() => setActiveProvider(p === activeProvider ? null : p)}
                >
                  {p}
                </button>
              ))}
            </div>
          )}

          {grouped.map(({ provider, items }) => (
            <div key={provider}>
              <div className="pgroup__label microlabel">{provider}</div>
              <div className="mgrid">
                {items.map((m) => (
                  <div
                    className={`mcard${m.inLiteLLM ? "" : " mcard--unconfigured"}`}
                    key={m.id}
                  >
                    <div className="mcard__h">
                      <div className="mcard__logo" style={{ background: m.logoColor }}>{m.logoText}</div>
                      <div style={{ flex: 1 }}>
                        <div className="mcard__name">{m.name}</div>
                        <div className="mcard__prov">{m.provider}</div>
                      </div>
                      {m.inLiteLLM ? (
                        <span className="pill pill--good"><span className="dot" />available</span>
                      ) : (
                        <span className="pill pill--warn" style={{ fontSize: 11 }}>not yet configured</span>
                      )}
                    </div>
                    <div className="mcard__foot">
                      {m.inLiteLLM ? (
                        <Link href="/portal/playground" className="btn btn--sm btn--primary">
                          Try in playground
                        </Link>
                      ) : (
                        <span style={{ fontSize: 12, color: "var(--fg-3)" }}>
                          Contact Platform Engineering to enable
                        </span>
                      )}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          ))}
        </>
      )}

      <p style={{ marginTop: 18, color: "var(--fg-3)", fontSize: 12.5 }}>
        Need a model that isn&apos;t here?{" "}
        <a href="#" style={{ color: "var(--accent-text)" }}>Request approval</a> — admins review on Mondays.
      </p>
    </main>
  );
}
