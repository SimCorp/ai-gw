"use client";

import Link from "next/link";
import { useState, useEffect } from "react";

const LITELLM_BASE = "http://localhost:8003";
const LITELLM_KEY = "sk-litellm-local-dev";

interface LiteLLMModel {
  id: string;
  object: string;
  created: number;
  owned_by: string;
}

interface DisplayModel {
  id: string;
  name: string;
  provider: string;
  logoColor: string;
  logoText: string;
}

function detectProvider(id: string): { provider: string; logoColor: string; logoText: string } {
  const lower = id.toLowerCase();
  if (lower.includes("claude")) return { provider: "Anthropic", logoColor: "#D97757", logoText: "A" };
  if (lower.includes("gemini")) return { provider: "Google", logoColor: "#4285F4", logoText: "G" };
  if (lower.includes("gpt") || lower.includes("o1") || lower.includes("o3")) return { provider: "OpenAI", logoColor: "#10A37F", logoText: "Oa" };
  if (lower.includes("local") || lower.includes("ollama") || lower.includes("llama")) return { provider: "Self-hosted", logoColor: "#1D958E", logoText: "Ol" };
  return { provider: "GitHub Models", logoColor: "#0078D4", logoText: "GH" };
}

export default function ModelsPage() {
  const [models, setModels] = useState<DisplayModel[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setLoading(true);
    fetch(`${LITELLM_BASE}/v1/models`, {
      headers: { Authorization: `Bearer ${LITELLM_KEY}` },
    })
      .then((r) => {
        if (!r.ok) throw new Error(`HTTP ${r.status}`);
        return r.json();
      })
      .then((data: { data: LiteLLMModel[] }) => {
        const display: DisplayModel[] = data.data.map((m) => ({
          id: m.id,
          name: m.id,
          ...detectProvider(m.id),
        }));
        setModels(display);
      })
      .catch((e) => setError(String(e)))
      .finally(() => setLoading(false));
  }, []);

  return (
    <main className="pmain">
      <style>{`
        .mgrid { display:grid; grid-template-columns:repeat(2,1fr); gap:14px; }
        .mcard { background:var(--surface); border:1px solid var(--rule); border-radius:var(--radius-3); padding:18px; display:flex; flex-direction:column; gap:10px; transition:border-color 120ms; }
        .mcard:hover { border-color:var(--sc-blue); }
        .mcard__h { display:flex; align-items:flex-start; gap:12px; }
        .mcard__logo { width:36px; height:36px; border-radius:8px; flex-shrink:0; display:grid; place-items:center; color:#fff; font-weight:700; font-size:13px; }
        .mcard__name { font-family:var(--font-mono); font-weight:600; font-size:14px; }
        .mcard__prov { font-size:12px; color:var(--fg-3); }
        .mcard__foot { display:flex; gap:6px; align-items:center; padding-top:10px; border-top:1px solid var(--rule); }
      `}</style>

      <div className="phero">
        <div>
          <h1>Models</h1>
          <p>
            {loading ? "Loading available models…" : error ? "Could not load models." : `${models.length} model${models.length !== 1 ? "s" : ""} available. All are OpenAI-compatible — same SDK, same code.`}
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
        <div className="mgrid">
          {models.map((m) => (
            <div className="mcard" key={m.id}>
              <div className="mcard__h">
                <div className="mcard__logo" style={{ background: m.logoColor }}>{m.logoText}</div>
                <div style={{ flex: 1 }}>
                  <div className="mcard__name">{m.name}</div>
                  <div className="mcard__prov">{m.provider}</div>
                </div>
                <span className="pill pill--good"><span className="dot" />available</span>
              </div>
              <div className="mcard__foot">
                <Link href="/portal/playground" className="btn btn--sm btn--primary">
                  Try in playground
                </Link>
              </div>
            </div>
          ))}
        </div>
      )}

      <p style={{ marginTop: 18, color: "var(--fg-3)", fontSize: 12.5 }}>
        Need a model that isn&apos;t here?{" "}
        <a href="#" style={{ color: "var(--sc-blue)" }}>Request approval</a> — admins review on Mondays.
      </p>
    </main>
  );
}
