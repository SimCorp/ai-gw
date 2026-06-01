"use client";

import Link from "next/link";
import { useState } from "react";

const TOC = [
  { id: "install",   label: "1. Install the SDK" },
  { id: "auth",      label: "2. Get an API key" },
  { id: "first",     label: "3. First call" },
  { id: "streaming", label: "4. Streaming" },
  { id: "tools",     label: "5. Tool use" },
  { id: "cache",     label: "6. Cache hints" },
  { id: "errors",    label: "7. Error handling" },
  { id: "next",      label: "Next steps" },
];

// Local dev base URL (goes through cache → auth → litellm)
const LOCAL_BASE = "http://localhost:8002/v1";
const PROD_BASE  = "https://aigw.simcorp.internal/v1";

export default function DocsPage() {
  const [sdkLang, setSdkLang] = useState(0);
  const [env, setEnv] = useState<"local" | "prod">("local");
  const [activeSection, setActiveSection] = useState("install");
  const [copied, setCopied] = useState<string | null>(null);

  const baseUrl = env === "local" ? LOCAL_BASE : PROD_BASE;

  const copy = (id: string, text: string) => {
    navigator.clipboard.writeText(text).catch(() => {});
    setCopied(id);
    setTimeout(() => setCopied(null), 2000);
  };

  return (
    <main className="pmain">
      <style>{`
        .toc { position:sticky; top:28px; font-size:12.5px; }
        .toc h5 { font-size:11px; font-weight:600; text-transform:uppercase; letter-spacing:0.04em; color:var(--fg-3); margin:0 0 8px; }
        .toc a { display:block; padding:4px 8px; color:var(--fg-2); text-decoration:none; border-radius:4px; border-left:2px solid transparent; margin-bottom:2px; }
        .toc a:hover { color:var(--fg-1); }
        .toc a.is-active { color:var(--sc-blue); border-left-color:var(--sc-blue); background:var(--sc-blue-soft); }
        .doc { max-width:720px; }
        .doc h2 { font-size:22px; font-weight:600; margin:36px 0 12px; letter-spacing:-0.005em; scroll-margin-top:20px; background:linear-gradient(180deg,#fff 0%,#C7CBE6 100%); -webkit-background-clip:text; background-clip:text; color:transparent; }
        .doc h2:first-child { margin-top:0; }
        .doc h3 { font-size:15px; font-weight:600; margin:22px 0 8px; }
        .doc p, .doc li { font-size:14px; line-height:1.65; color:var(--fg-1); }
        .doc p { margin:0 0 12px; }
        .doc ul { padding-left:20px; margin:0 0 14px; }
        .doc code:not(.code-block code) { background:var(--surface-soft); padding:1px 6px; border-radius:3px; font-size:12.5px; font-family:var(--font-mono); }
        .env-switch { display:inline-flex; border:1px solid var(--rule); border-radius:6px; overflow:hidden; margin-bottom:20px; }
        .env-switch button { padding:5px 14px; font-size:12px; font-weight:500; background:none; border:0; cursor:pointer; color:var(--fg-2); }
        .env-switch button.is-active { background:var(--sc-blue); color:#fff; }
      `}</style>

      <div className="phero">
        <div>
          <h1>Quickstart</h1>
          <p>From zero to first call in five minutes. All examples use the OpenAI-compatible endpoint.</p>
        </div>
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "200px 1fr", gap: 32 }}>
        <aside className="toc">
          <h5>On this page</h5>
          {TOC.map((item) => (
            <a
              key={item.id}
              href={`#${item.id}`}
              className={activeSection === item.id ? "is-active" : ""}
              onClick={() => setActiveSection(item.id)}
            >
              {item.label}
            </a>
          ))}
        </aside>

        <article className="doc">
          {/* Environment toggle */}
          <div className="env-switch">
            <button className={env === "local" ? "is-active" : ""} onClick={() => setEnv("local")}>Local dev</button>
            <button className={env === "prod" ? "is-active" : ""} onClick={() => setEnv("prod")}>Production</button>
          </div>

          <h2 id="install">1. Install the SDK</h2>
          <p>
            The gateway is OpenAI-protocol compatible — use the official OpenAI SDK and point it at the gateway base URL.
            No custom package required.
          </p>
          <div className="tabs-pills">
            {["Python", "TypeScript", "Go"].map((l, i) => (
              <button key={l} className={sdkLang === i ? "is-active" : ""} onClick={() => setSdkLang(i)}>{l}</button>
            ))}
          </div>
          <div className="code-block">
            {sdkLang === 0 && "pip install openai"}
            {sdkLang === 1 && "npm install openai"}
            {sdkLang === 2 && "go get github.com/openai/openai-go"}
            <button className="copy-btn" onClick={() => copy("install", ["pip install openai", "npm install openai", "go get github.com/openai/openai-go"][sdkLang])}>
              {copied === "install" ? "Copied!" : "Copy"}
            </button>
          </div>

          <h2 id="auth">2. Get an API key</h2>
          <p>
            Head to <Link href="/portal/keys" style={{ color: "var(--sc-blue)" }}>API keys</Link> and
            click <strong>+ Issue key</strong>. Give it a name like <code>my-laptop</code>.
            Copy the key immediately — it is only shown once.
          </p>
          <div className="callout">
            <strong>Never paste keys into code.</strong> Use environment variables or a secrets manager.
            Keys are revocable from the portal immediately.
          </div>
          <div className="code-block">
            {"export AIGW_KEY="}
            <span className="s">&quot;sk-…&quot;</span>
            <button className="copy-btn" onClick={() => copy("auth", 'export AIGW_KEY="sk-…"')}>
              {copied === "auth" ? "Copied!" : "Copy"}
            </button>
          </div>

          <h2 id="first">3. Your first call</h2>
          <p>
            Same shape as OpenAI — just a different <code>base_url</code>.
            Current base URL: <code style={{ fontSize: 11 }}>{baseUrl}</code>.
            Pick any model from the <Link href="/portal/models" style={{ color: "var(--sc-blue)" }}>catalog</Link>.
          </p>
          <div className="tabs-pills">
            {["Python", "TypeScript"].map((l, i) => (
              <button key={l} className={sdkLang === i ? "is-active" : ""} onClick={() => setSdkLang(i)}>{l}</button>
            ))}
          </div>
          {sdkLang === 0 && (
            <div className="code-block">
              <pre style={{ margin: 0, fontFamily: "var(--font-mono)", fontSize: 13, lineHeight: 1.6, whiteSpace: "pre-wrap" }}>{`import os
from openai import OpenAI

client = OpenAI(
    base_url="${baseUrl}",
    api_key=os.environ["AIGW_KEY"],
)

resp = client.chat.completions.create(
    model="claude-sonnet-4-6",
    messages=[
        {"role": "system", "content": "You are concise."},
        {"role": "user", "content": "What is a DORA metric?"},
    ],
)
print(resp.choices[0].message.content)`}</pre>
              <button className="copy-btn" onClick={() => copy("first-py", `import os\nfrom openai import OpenAI\n\nclient = OpenAI(\n    base_url="${baseUrl}",\n    api_key=os.environ["AIGW_KEY"],\n)\n\nresp = client.chat.completions.create(\n    model="claude-sonnet-4-6",\n    messages=[{"role": "user", "content": "What is a DORA metric?"}],\n)\nprint(resp.choices[0].message.content)`)}>
                {copied === "first-py" ? "Copied!" : "Copy"}
              </button>
            </div>
          )}
          {sdkLang === 1 && (
            <div className="code-block">
              <pre style={{ margin: 0, fontFamily: "var(--font-mono)", fontSize: 13, lineHeight: 1.6, whiteSpace: "pre-wrap" }}>{`import OpenAI from "openai";

const client = new OpenAI({
  baseURL: "${baseUrl}",
  apiKey: process.env.AIGW_KEY,
});

const resp = await client.chat.completions.create({
  model: "claude-sonnet-4-6",
  messages: [{ role: "user", content: "What is a DORA metric?" }],
});
console.log(resp.choices[0].message.content);`}</pre>
              <button className="copy-btn" onClick={() => copy("first-ts", `import OpenAI from "openai";\n\nconst client = new OpenAI({\n  baseURL: "${baseUrl}",\n  apiKey: process.env.AIGW_KEY,\n});\n\nconst resp = await client.chat.completions.create({\n  model: "claude-sonnet-4-6",\n  messages: [{ role: "user", content: "What is a DORA metric?" }],\n});\nconsole.log(resp.choices[0].message.content);`)}>
                {copied === "first-ts" ? "Copied!" : "Copy"}
              </button>
            </div>
          )}

          <h2 id="streaming">4. Streaming</h2>
          <p>Set <code>stream=True</code> for token-by-token output. The gateway proxies SSE without buffering.</p>
          <div className="code-block">
            <pre style={{ margin: 0, fontFamily: "var(--font-mono)", fontSize: 13, lineHeight: 1.6, whiteSpace: "pre-wrap" }}>{`stream = client.chat.completions.create(
    model="claude-sonnet-4-6",
    messages=[{"role": "user", "content": "Explain CRDT in one paragraph"}],
    stream=True,
)
for chunk in stream:
    if chunk.choices[0].delta.content:
        print(chunk.choices[0].delta.content, end="")`}</pre>
            <button className="copy-btn" onClick={() => copy("streaming", `stream = client.chat.completions.create(
    model="claude-sonnet-4-6",
    messages=[{"role": "user", "content": "Explain CRDT in one paragraph"}],
    stream=True,
)
for chunk in stream:
    if chunk.choices[0].delta.content:
        print(chunk.choices[0].delta.content, end="")`)}>
              {copied === "streaming" ? "Copied!" : "Copy"}
            </button>
          </div>

          <h2 id="tools">5. Tool use</h2>
          <p>Pass standard OpenAI <code>tools</code> definitions. The gateway normalises tool-call format across providers.</p>
          <div className="code-block">
            <pre style={{ margin: 0, fontFamily: "var(--font-mono)", fontSize: 13, lineHeight: 1.6, whiteSpace: "pre-wrap" }}>{`tools = [{
    "type": "function",
    "function": {
        "name": "get_repo_stats",
        "description": "Return commit count for a repo",
        "parameters": {
            "type": "object",
            "properties": {"repo": {"type": "string"}},
            "required": ["repo"],
        },
    },
}]
resp = client.chat.completions.create(
    model="claude-sonnet-4-6",
    messages=messages,
    tools=tools,
)`}</pre>
            <button className="copy-btn" onClick={() => copy("tools", `tools = [{
    "type": "function",
    "function": {
        "name": "get_repo_stats",
        "description": "Return commit count for a repo",
        "parameters": {
            "type": "object",
            "properties": {"repo": {"type": "string"}},
            "required": ["repo"],
        },
    },
}]
resp = client.chat.completions.create(
    model="claude-sonnet-4-6",
    messages=messages,
    tools=tools,
)`)}>
              {copied === "tools" ? "Copied!" : "Copy"}
            </button>
          </div>

          <h2 id="cache">6. Cache hints</h2>
          <p>
            The semantic cache is on by default. Repeated or semantically-similar prompts return in milliseconds.
            To bypass it for a single call, set the <code>x-cache</code> header:
          </p>
          <div className="code-block">
            <pre style={{ margin: 0, fontFamily: "var(--font-mono)", fontSize: 13, lineHeight: 1.6, whiteSpace: "pre-wrap" }}>{`resp = client.chat.completions.create(
    model="claude-sonnet-4-6",
    messages=[...],
    extra_headers={"x-cache": "bypass"},
)
# Response header x-cache: HIT | MISS | BYPASS`}</pre>
            <button className="copy-btn" onClick={() => copy("cache", `resp = client.chat.completions.create(
    model="claude-sonnet-4-6",
    messages=[...],
    extra_headers={"x-cache": "bypass"},
)
# Response header x-cache: HIT | MISS | BYPASS`)}>
              {copied === "cache" ? "Copied!" : "Copy"}
            </button>
          </div>

          <h2 id="errors">7. Error handling</h2>
          <ul>
            <li><code>401</code> — missing or invalid API key. Check <Link href="/portal/keys" style={{ color: "var(--sc-blue)" }}>your keys</Link>.</li>
            <li><code>429</code> — rate limit hit. Back off using the <code>Retry-After</code> header.</li>
            <li><code>402</code> — team monthly budget cap reached. Contact your team owner.</li>
            <li><code>403</code> — model not in your team&apos;s allow-list. Check the <Link href="/portal/models" style={{ color: "var(--sc-blue)" }}>catalog</Link>.</li>
            <li><code>5xx</code> — upstream provider error; the gateway retries once before surfacing.</li>
          </ul>
          <div className="callout" style={{ marginTop: 16 }}>
            <strong>Local dev tip:</strong> Start all services with{" "}
            <code>docker compose -f infra/docker-compose.yml up</code> before making requests.
            The playground at <Link href="/portal/playground" style={{ color: "var(--sc-blue)" }}>Playground</Link> is
            the fastest way to verify your key works.
          </div>

          <h2 id="next">Next steps</h2>
          <ul>
            <li><Link href="/portal/playground" style={{ color: "var(--sc-blue)" }}>Open the Playground</Link> — iterate on prompts in the browser before writing code.</li>
            <li><Link href="/portal/agents" style={{ color: "var(--sc-blue)" }}>Build an agent</Link> — compose tool-using agents with MCP servers.</li>
            <li><Link href="/portal/usage" style={{ color: "var(--sc-blue)" }}>View your usage</Link> — cost breakdown by model, session, and day.</li>
            <li><Link href="/portal/models" style={{ color: "var(--sc-blue)" }}>Browse the model catalog</Link> — see available models and their capabilities.</li>
          </ul>
        </article>
      </div>
    </main>
  );
}
