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

export default function DocsPage() {
  const [sdkLang, setSdkLang] = useState(0);
  const [activeSection, setActiveSection] = useState("install");
  const [copied, setCopied] = useState<string | null>(null);

  const handleCopy = (id: string) => {
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
      `}</style>

      <div className="phero">
        <div>
          <h1>Quickstart</h1>
          <p>From zero to first call in five minutes. All examples use the OpenAI-compatible base URL.</p>
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
          <h2 id="install">1. Install the SDK</h2>
          <p>
            The gateway speaks the OpenAI protocol, so any OpenAI client works. We publish a thin wrapper
            to the internal package registry that handles auth and retries.
          </p>
          <div className="tabs-pills">
            {["Python", "TypeScript", "Go"].map((l, i) => (
              <button key={l} className={sdkLang === i ? "is-active" : ""} onClick={() => setSdkLang(i)}>{l}</button>
            ))}
          </div>
          <div className="code-block">
            {sdkLang === 0 && (
              <><span className="c"># Internal package registry — already configured in your dev image</span>{"\npip install simcorp-aigw"}</>
            )}
            {sdkLang === 1 && "npm install simcorp-aigw"}
            {sdkLang === 2 && "go get simcorp.internal/aigw"}
            <button className="copy-btn" onClick={() => handleCopy("install")}>
              {copied === "install" ? "Copied!" : "Copy"}
            </button>
          </div>

          <h2 id="auth">2. Get an API key</h2>
          <p>
            Head to <Link href="/portal/keys" style={{ color: "var(--sc-blue)" }}>API keys</Link> and
            click <strong>+ Issue key</strong>. Give it a name like <code>my-laptop</code> and pick
            the <strong>dev</strong> scope while you&apos;re prototyping.
          </p>
          <div className="callout">
            <strong>Don&apos;t paste keys into code.</strong> Export them to your shell, or use Azure Key Vault refs
            in deployed services. Keys are revoked within 30s if you ever leak one.
          </div>
          <div className="code-block">
            {"export AIGW_KEY="}
            <span className="s">&quot;sk_test_...&quot;</span>
            <button className="copy-btn" onClick={() => handleCopy("auth")}>
              {copied === "auth" ? "Copied!" : "Copy"}
            </button>
          </div>

          <h2 id="first">3. Your first call</h2>
          <p>
            Same shape as OpenAI — just a different <code>base_url</code>.
            Pick any model from the <Link href="/portal/models" style={{ color: "var(--sc-blue)" }}>catalog</Link>.
          </p>
          <div className="code-block">
            <pre style={{ margin: 0, fontFamily: "var(--font-mono)", fontSize: 13, lineHeight: 1.6, whiteSpace: "pre-wrap" }}>{`from simcorp_aigw import Client

client = Client()  # reads AIGW_KEY from env

resp = client.chat.completions.create(
    model="claude-sonnet-4.5",
    messages=[
        {"role": "system", "content": "You're concise."},
        {"role": "user", "content": "What's the cap rate on a 4.5% yield, 8x EBITDA?"},
    ],
)
print(resp.choices[0].message.content)`}</pre>
            <button className="copy-btn" onClick={() => handleCopy("first")}>
              {copied === "first" ? "Copied!" : "Copy"}
            </button>
          </div>

          <h2 id="streaming">4. Streaming</h2>
          <p>Set <code>stream=True</code> for token-by-token output. The gateway proxies SSE without buffering.</p>
          <div className="code-block">
            {"stream = client.chat.completions."}<span className="f">create</span>{"(\n"}
            {"    model="}<span className="s">&quot;claude-sonnet-4.5&quot;</span>{",\n"}
            {"    messages=[...],\n    stream="}<span className="k">True</span>{",\n)\n"}
            <span className="k">for</span>{" chunk "}<span className="k">in</span>{" stream:\n"}
            {"    "}<span className="k">if</span>{" chunk.choices["}<span className="v">0</span>{"].delta.content:\n"}
            {"        "}<span className="f">print</span>{"(chunk.choices["}<span className="v">0</span>{"].delta.content, end="}<span className="s">&quot;&quot;</span>{")"}
            <button className="copy-btn" onClick={() => handleCopy("streaming")}>
              {copied === "streaming" ? "Copied!" : "Copy"}
            </button>
          </div>

          <h2 id="tools">5. Tool use</h2>
          <p>Pass standard OpenAI <code>tools</code> definitions. The gateway fans out to the right provider&apos;s tool-call format and normalises the response.</p>
          <div className="code-block">
            {"tools = [{\n    "}<span className="s">&quot;type&quot;</span>{": "}<span className="s">&quot;function&quot;</span>{",\n    "}<span className="s">&quot;function&quot;</span>{": {\n        "}<span className="s">&quot;name&quot;</span>{": "}<span className="s">&quot;get_position&quot;</span>{",\n    },\n}]\nresp = client.chat.completions."}<span className="f">create</span>{"(\n    model="}<span className="s">&quot;claude-sonnet-4.5&quot;</span>{",\n    messages=messages,\n    tools=tools,\n)"}
            <button className="copy-btn" onClick={() => handleCopy("tools")}>
              {copied === "tools" ? "Copied!" : "Copy"}
            </button>
          </div>

          <h2 id="cache">6. Cache hints</h2>
          <p>The semantic cache is on by default. To bypass it for a single call, set the <code>x-cache</code> header:</p>
          <div className="code-block">
            {"resp = client.chat.completions."}<span className="f">create</span>{"(\n    model="}<span className="s">&quot;claude-sonnet-4.5&quot;</span>{",\n    messages=[...],\n    extra_headers={"}<span className="s">&quot;x-cache&quot;</span>{": "}<span className="s">&quot;bypass&quot;</span>{"}\n)\n"}<span className="f">print</span>{"(resp.headers["}<span className="s">&quot;x-cache&quot;</span>{"])  "}<span className="c"># HIT | MISS | BYPASS</span>
            <button className="copy-btn" onClick={() => handleCopy("cache")}>
              {copied === "cache" ? "Copied!" : "Copy"}
            </button>
          </div>

          <h2 id="errors">7. Error handling</h2>
          <ul>
            <li><code>429</code> — you hit a team rate limit. Back off using the <code>retry-after</code> header.</li>
            <li><code>402</code> — team budget cap hit. Talk to your team owner.</li>
            <li><code>403</code> — model not in your team&apos;s allow-list. Check the <Link href="/portal/models" style={{ color: "var(--sc-blue)" }}>catalog</Link>.</li>
            <li><code>5xx</code> — upstream provider issue; the gateway will retry once before bubbling up.</li>
          </ul>

          <h2 id="next">Next steps</h2>
          <ul>
            <li><Link href="/portal/playground" style={{ color: "var(--sc-blue)" }}>Open the Playground</Link> to iterate on prompts before you ship.</li>
            <li><Link href="/portal/agents" style={{ color: "var(--sc-blue)" }}>Build an agent</Link> with tools and scheduled runs.</li>
            <li><Link href="/portal/prompts" style={{ color: "var(--sc-blue)" }}>Browse the prompt library</Link> for vetted starters.</li>
          </ul>
        </article>
      </div>
    </main>
  );
}
