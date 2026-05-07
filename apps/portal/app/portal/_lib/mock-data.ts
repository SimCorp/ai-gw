"use client";

import type { ApiKey, Request, Session, Model, PromptTemplate, Agent, McpServer, Skill, Plugin } from "./types";

export const MOCK_KEYS: ApiKey[] = [
  { id: "k1", name: "prod-rag-service", prefix: "sk_live_••••8a31f", scope: "prod", calls7d: 38210, lastUsed: "2 min ago", status: "active" },
  { id: "k2", name: "eval-runner",       prefix: "sk_test_••••c41d8", scope: "dev",  calls7d: 9114,  lastUsed: "11 min ago", status: "active" },
  { id: "k3", name: "jupyter-notebook",  prefix: "sk_test_••••3a982", scope: "dev",  calls7d: 4288,  lastUsed: "1 h ago",    status: "expiring", daysToExpiry: 22 },
];

export const MOCK_REQUESTS: Request[] = [
  { time: "14:42:08", model: "claude-sonnet-4.5", status: "200", tokensIn: 2108, tokensOut: 412, cost: 0.0124 },
  { time: "14:38:55", model: "claude-sonnet-4.5", status: "200", tokensIn: 2108, tokensOut: 412, cost: 0, cached: true },
  { time: "14:31:14", model: "gemini-2.5-pro",    status: "200", tokensIn: 3884, tokensOut: 1210, cost: 0.0109 },
  { time: "14:28:02", model: "claude-haiku-4.5",  status: "200", tokensIn: 820,  tokensOut: 188,  cost: 0.0014 },
  { time: "14:14:48", model: "claude-sonnet-4.5", status: "429", tokensIn: 0,    tokensOut: 0,    cost: null },
];

export const MOCK_SESSIONS: Session[] = [
  { id: "s1", type: "playground", label: "Playground · 2h ago",  timeAgo: "2h ago",      description: "claude-sonnet-4.5 · 14 turns · monorepo retrieval tool", tool: "monorepo retrieval tool",    turns: 14, model: "claude-sonnet-4.5" },
  { id: "s2", type: "agent",      label: "Agent · yesterday",    timeAgo: "yesterday",   description: "3 tools · last run 18 min · 4 PRs reviewed" },
  { id: "s3", type: "prompt",     label: "Prompt · 3d ago",      timeAgo: "3d ago",      description: "v3 · forked from platform-shared · 142 uses" },
];

export const MOCK_MODELS: Model[] = [
  {
    id: "claude-sonnet-4.5", name: "claude-sonnet-4.5", provider: "Anthropic", providerShort: "Anthropic · production · default for agent-platform",
    logoColor: "#D97757", logoText: "A", description: "Best general-purpose model. Strong at long context, tool use, and structured output. Sweet spot for agentic workflows.",
    context: "200K", priceIn: "$3.00", priceOut: "$15.00", caps: ["chat","tools","vision","streaming"],
    status: "healthy", fallback: "gemini-2.5-pro",
  },
  {
    id: "claude-haiku-4.5", name: "claude-haiku-4.5", provider: "Anthropic", providerShort: "Anthropic · production",
    logoColor: "#D97757", logoText: "A", description: "Cheap and fast. Use for high-volume classification, routing, and short-form generation. 4× cheaper than Sonnet.",
    context: "200K", priceIn: "$0.80", priceOut: "$4.00", caps: ["chat","tools","streaming"],
    status: "healthy",
  },
  {
    id: "claude-opus-4.5", name: "claude-opus-4.5", provider: "Anthropic", providerShort: "Anthropic · production · approval required",
    logoColor: "#D97757", logoText: "A", description: "Frontier reasoning. Reach for it on novel problems where Sonnet isn't enough. Expensive — ask before defaulting to it.",
    context: "200K", priceIn: "$15.00", priceOut: "$75.00", caps: ["chat","tools","vision","extended-thinking"],
    status: "healthy", requiresScope: "opus-tier",
  },
  {
    id: "gemini-2.5-pro", name: "gemini-2.5-pro", provider: "Google", providerShort: "Google Vertex AI · production",
    logoColor: "#4285F4", logoText: "G", description: "2M context window — drop in entire codebases or quarterly filings. Strong audio + video understanding.",
    context: "2M", priceIn: "$1.25", priceOut: "$5.00", caps: ["chat","tools","vision","audio"],
    status: "healthy", note: "region europe-north1",
  },
  {
    id: "gemini-2.5-flash", name: "gemini-2.5-flash", provider: "Google", providerShort: "Google Vertex AI · production",
    logoColor: "#4285F4", logoText: "G", description: "Lightweight Gemini. Multimodal at low cost. Great for image classification batches.",
    context: "1M", priceIn: "$0.30", priceOut: "$1.20", caps: ["chat","tools","vision"],
    status: "healthy",
  },
  {
    id: "gpt-5", name: "gpt-5", provider: "Azure OpenAI", providerShort: "Azure OpenAI · BYO deployment · degraded",
    logoColor: "#0078D4", logoText: "Az", description: "Available, but provider is currently failing over to Anthropic. Expect higher latency and occasional reroutes.",
    context: "400K", priceIn: "$5.00", priceOut: "$20.00", caps: ["chat","tools","vision"],
    status: "degraded", errorRate: "5xx 8.2%",
  },
  {
    id: "text-embedding-3-small", name: "text-embedding-3-small", provider: "OpenAI", providerShort: "OpenAI · production · embeddings only",
    logoColor: "#10A37F", logoText: "Oa", description: "Default for retrieval. The semantic cache uses this internally — your embed calls are cached too.",
    context: "8K", priceFlat: "$0.02", caps: ["embed","1536-dim"],
    status: "healthy",
  },
  {
    id: "ollama/llama-3.1-70b", name: "ollama/llama-3.1-70b", provider: "Self-hosted", providerShort: "Self-hosted · ollama-eu-1 · dev only",
    logoColor: "#1D958E", logoText: "Ol", description: "Internal cluster. Free to use, but capacity is shared and not for production traffic.",
    context: "128K", priceFlat: "$0", caps: ["chat","tools","no-egress"],
    status: "healthy", note: "scope dev",
  },
];

export const MOCK_PROMPTS: PromptTemplate[] = [
  { id: "p1", title: "PR review · Python style", version: "v3", versionPill: "pill--info", description: "Reviews a unified diff for style guide violations. Returns structured JSON with file, line, severity, and suggested fix.", preview: "You are a senior reviewer. For each violation in the diff, return JSON with: file, line, rule_id, severity (block/warn/nit), suggested_fix…", author: "p.fontaine", uses: 142, model: "claude-sonnet-4.5", stars: 28 },
  { id: "p2", title: "EM debt flow summariser", version: "draft", versionPill: "", description: "Answers questions about the SimCorp monorepo. Pairs with the retrieval.search tool.", preview: "You answer questions about the SimCorp monorepo. Cite source files with line ranges. Prefer code examples over prose…", author: "m.weber", lastEdited: "2h ago", mine: true },
  { id: "p3", title: "Code review · Python style guide", version: "v2.1", versionPill: "pill--info", description: "Reviews diffs against the SimCorp Python style guide. Flags violations, suggests fixes, ignores nits.", preview: "Review the unified diff below against our Python style guide. For each violation, output: file, line, rule_id, severity (block/warn/nit), suggested_fix…", author: "i.koivisto", uses: 418, model: "claude-haiku-4.5", stars: 64 },
  { id: "p4", title: "SQL → natural language", version: "v1", versionPill: "pill--info", description: "Explain a SQL query in plain English for a non-SQL teammate. Highlights joins, filters, and windowing.", preview: "Given this SQL, write a 3-paragraph explanation that a backend engineer who doesn't use SQL daily could understand…", author: "l.gunnarsson", uses: 92, stars: 18 },
  { id: "p5", title: "Incident postmortem draft", version: "v4", versionPill: "pill--info", description: "Turns an incident timeline into a one-page postmortem draft. Tone is calm, factual, no blame.", preview: "You write the postmortem draft. Audience: engineering. Tone: calm, factual. No blame. Lead with impact and root cause…", author: "p.fontaine", uses: 62 },
  { id: "p6", title: "Support ticket classifier", version: "v2.1", versionPill: "pill--info", description: "Classifies inbound support tickets into one of 14 categories with confidence scores. Optimised for haiku-tier latency.", preview: "Classify this customer message into exactly one of: account_access, billing, data_quality, integration, performance, feature_request, bug, training_request, other. Return JSON…", author: "a.silva", uses: 1820, model: "claude-haiku-4.5", stars: 31 },
];

export const MOCK_AGENTS: Agent[] = [
  { id: "a1", name: "pr-review-bot",  description: "Reviews open pull requests against the engineering style guide. Posts inline comments and a summary to GitHub.", tools: 3, model: "claude-sonnet-4.5", status: "running",   lastRun: "18 min ago", successRate: "14/14 success this week" },
  { id: "a2", name: "bug-triage",     description: "Triages incoming bug reports overnight. Deduplicates against existing issues, labels by severity, and assigns to on-call.", tools: 5, model: "claude-sonnet-4.5", status: "scheduled", lastRun: "this morning", successRate: "34/35 success" },
  { id: "a3", name: "pre-merge-guard",description: "Pre-merge security check. Scans diffs for hardcoded secrets, risky deps, and missing tests before CI lets them merge.", tools: 4, model: "claude-sonnet-4.5", status: "draft" },
];

export const MOCK_MCP: McpServer[] = [
  {
    id: "portfolio-mcp", name: "portfolio-mcp", description: "Read-only access to current positions, target weights, and rebalance proposals across all SimCorp Dimension funds. Backed by the canonical book-of-record.",
    type: "internal", version: "v2.4.1", maintainer: "platform-data", tools: 9, calls24h: 4218, p50: "74 ms", transport: "stdio", status: "healthy",
    markBg: "linear-gradient(135deg,#818CF8 0%,#C084FC 100%)", markText: "#fff", logoLetters: "PF",
    endpoint: "stdio://portfolio-mcp@2.4.1", image: "registry.simcorp/mcp/portfolio:2.4.1", auth: "mTLS · cert from platform-pki", scopes: "positions:read · weights:read", owners: "platform-data · #ai-platform",
    toolList: [
      { name: "positions.get",       args: "(fund_id: string, as_of?: date) → Position[]",       description: "Returns current holdings for a fund. Honors entitlement filters per caller.", cap: "read" },
      { name: "target_weights.fetch",args: "(fund_id: string, model_version?: string) → Weights", description: "Latest model-portfolio target weights. Falls back to most recent approved version.", cap: "read" },
      { name: "drift.calculate",     args: "(fund_id: string) → DriftReport",                    description: "Per-sleeve drift in basis points vs target weights. Uses end-of-day NAV.", cap: "read" },
      { name: "rebalance.propose",   args: "(fund_id: string, target?: Weights) → Proposal",      description: "Generates a draft trade list to bring drift inside policy bands. Does NOT submit.", cap: "read" },
    ],
  },
  {
    id: "market-data-mcp", name: "market-data-mcp", description: "Real-time and historical quotes, FX rates, and reference data via Bloomberg + Refinitiv aggregator. Per-symbol entitlement enforced.",
    type: "internal", version: "v1.9.0", maintainer: "trading", tools: 14, calls24h: 3841, p50: "48 ms", transport: "http+sse", status: "healthy",
    markBg: "linear-gradient(135deg,#2DD4BF 0%,#34D399 100%)", markText: "#052E22", logoLetters: "MD",
  },
  {
    id: "filings-mcp", name: "filings-mcp", description: "SEC EDGAR + EU regulatory filings ingest with semantic search. Returns citations + PDF page anchors.",
    type: "internal", version: "v0.8.3", maintainer: "research", tools: 6, calls24h: 1108, p50: "312 ms", transport: "http", status: "degraded",
    markBg: "linear-gradient(135deg,#F472B6 0%,#FB923C 100%)", markText: "#fff", logoLetters: "FL",
  },
  {
    id: "github-mcp", name: "github-mcp", description: "Repo browsing, PR diff fetch, comment posting. Scoped to org:simcorp · 142 repos. Token-rotation managed by platform.",
    type: "vendored", version: "v0.6.0", maintainer: "github.com/anthropic/mcp-servers", tools: 11, calls24h: 1684, p50: "128 ms", transport: "stdio", status: "healthy",
    markBg: "linear-gradient(135deg,#3B82F6 0%,#A855F7 100%)", markText: "#fff", logoLetters: "GH",
  },
  {
    id: "confluence-mcp", name: "confluence-mcp", description: "Search and read internal Confluence spaces. Currently failing OAuth refresh — token expired 14 min ago.",
    type: "vendored", version: "v0.3.1", maintainer: "third-party", tools: 5, calls24h: 0, p50: "91% errors", transport: "http", status: "auth failing",
    markBg: "linear-gradient(135deg,#FBBF24 0%,#FB7185 100%)", markText: "#2A0E10", logoLetters: "CN",
  },
];

export const MOCK_SKILLS: Skill[] = [
  { id: "sk1", name: "Portfolio analyst", version: "v3.2", model: "sonnet-4.5", description: "Reads positions, computes drift, proposes rebalances within policy bands. Cites the trade rationale per sleeve and outputs a CSV-ready trade list.", tools: 4, usesPerWeek: 418, stars: 4.8, variant: "s-purple", iconPath: "M2 14h12M4 11V7M7 11V4M10 11V8M13 11V6" },
  { id: "sk2", name: "PR reviewer · Python", version: "v5.1", model: "sonnet-4.5", description: "Reviews PRs against the SimCorp Python style guide. Flags type-hint gaps, missing tests, and risky deps. Posts inline comments via the github-mcp tool.", tools: 3, usesPerWeek: 284, stars: 4.7, variant: "s-teal", iconPath: "M2.5 3.5h11v9h-11zM5.5 6.5l2 2 4-4" },
  { id: "sk3", name: "Filing summarizer", version: "v2.0", model: "haiku-4.5", description: "Summarizes 10-K, 10-Q and EU prospectus filings into a 6-bullet brief with citations to PDF page anchors. Routes long docs through hierarchical chunking.", tools: 2, usesPerWeek: 192, stars: 4.6, variant: "s-pink", iconPath: "M8 5v3l2 1.5" },
  { id: "sk4", name: "Anomaly explainer", version: "v1.4", model: "sonnet-4.5", description: "Given a flagged data point, pulls surrounding context, neighbours, and history to draft a plain-English explanation an analyst can verify in 30 seconds.", tools: 5, usesPerWeek: 148, stars: 4.5, variant: "s-blue", iconPath: "M3 13l3-3 2 2 5-5M11 5h2v2" },
  { id: "sk5", name: "SQL → narrative", version: "v2.7", model: "haiku-4.5", description: "Takes a SQL result set and writes a 2-paragraph narrative explaining what changed week-over-week. Flags the three biggest movers automatically.", tools: 1, usesPerWeek: 318, stars: 4.7, variant: "s-amber", iconPath: "M2 4h12v8H2zM2 7h12M5 4v8" },
  { id: "sk6", name: "Ticket triage", version: "v4.0", model: "haiku-4.5", description: "Classifies incoming Jira tickets into the right project + component, assigns severity, and dedupes against the last 60 days of similar reports.", tools: 3, usesPerWeek: 89, stars: 4.4, variant: "s-purple", iconPath: "M3 3h10v3H3zM3 8h10v5H3zM5 10h2M5 11.5h4" },
];

export const MOCK_RECENT_SKILLS: Skill[] = [
  { id: "sk7", name: "Email drafter · client", version: "v1.2", model: "sonnet-4.5", description: "Drafts client-facing emails using the firm voice guide. Pulls the contact's recent thread for tone matching.", tools: 2, usesPerWeek: 0, stars: 4.6, variant: "s-teal", iconPath: "M2 4l6 4 6-4M2 4v8h12V4z" },
  { id: "sk8", name: "Meeting recap", version: "v0.9", model: "haiku-4.5", description: "Converts Teams meeting transcripts into a brief (decisions, owners, dates). 30-second runs at $0.003.", tools: 1, usesPerWeek: 0, stars: 4.3, variant: "s-pink", iconPath: "M8 4v4l2.5 1.5" },
  { id: "sk9", name: "Data quality check", version: "v3.1", model: "sonnet-4.5", description: "Inspects a DataFrame schema and sample for nulls, distribution anomalies, and referential integrity. Returns a markdown report.", tools: 2, usesPerWeek: 0, stars: 4.5, variant: "s-blue", iconPath: "M2 5h12v8H2zM2 9h12" },
];

export const MOCK_PLUGINS: Plugin[] = [
  { id: "pl1", name: "Datadog tracing",           by: "platform-observability · Observability", category: "Observability", description: "Emits OpenTelemetry spans for every gateway request, model call, tool invocation, and cache lookup. Pre-wired to the firm Datadog account.", stars: 4.8, installs: 1284, logoLetters: "DT", logoCss: "linear-gradient(135deg,#818CF8 0%,#C084FC 100%)", installed: true },
  { id: "pl2", name: "Semantic cache",             by: "platform-data · Routing", category: "Routing", description: "Embedding-backed cache with cosine threshold. Cuts identical-intent re-asks before they hit a model. Currently saves the org ~$1.2k/day.", stars: 4.9, installs: 892, logoLetters: "SM", logoCss: "linear-gradient(135deg,#2DD4BF 0%,#34D399 100%)", installed: true },
  { id: "pl3", name: "Guardrails · PII",           by: "platform-safety · Safety", category: "Safety", description: "Pre-flight scan of every prompt for PII, MNPI markers, and SimCorp customer identifiers. Redacts in place or blocks the call per policy.", stars: 4.7, installs: 1108, logoLetters: "GR", logoCss: "linear-gradient(135deg,#F472B6 0%,#FB923C 100%)", installed: true },
  { id: "pl4", name: "Postgres conversation store",by: "anthropic · Storage", category: "Storage", description: "Persists Playground threads + agent runs to a Postgres you own. Drops the dependency on the platform-managed transient store.", stars: 4.6, installs: 418, logoLetters: "PG", logoCss: "linear-gradient(135deg,#3B82F6 0%,#818CF8 100%)", installed: false },
  { id: "pl5", name: "Eval harness · Inspect",     by: "anthropic-evals · Eval", category: "Eval", description: "Run Inspect-style evals against any model from the registry on a schedule. Emits a regression diff to the team channel when a metric drops 2σ.", stars: 4.8, installs: 284, logoLetters: "EV", logoCss: "linear-gradient(135deg,#FBBF24 0%,#FB7185 100%)", installed: false },
  { id: "pl6", name: "VS Code · Inline complete",  by: "editor-tools · Editor", category: "Editor", description: "Routes Copilot-style inline completions through the gateway. Inherits per-user cost caps and the safety guardrails plugin if installed.", stars: 4.5, installs: 2148, logoLetters: "VS", logoCss: "linear-gradient(135deg,#A855F7 0%,#EC4899 100%)", installed: false },
  { id: "pl7", name: "Jenkins gate",               by: "platform-ci · CI/CD", category: "CI/CD", description: "Adds an LLM-powered review gate to Jenkins pipelines. Blocks merges whose diff fails the configured skill (default: PR reviewer · Python).", stars: 4.4, installs: 92, logoLetters: "JK", logoCss: "linear-gradient(135deg,#818CF8 0%,#C084FC 100%)", installed: false },
  { id: "pl8", name: "Slack digest",               by: "platform-collab · Observability", category: "Observability", description: "Posts a daily LLM-generated digest of cost anomalies, new models, and security alerts to your chosen Slack channel.", stars: 4.3, installs: 614, logoLetters: "SL", logoCss: "linear-gradient(135deg,#4ADE80 0%,#22D3EE 100%)", installed: false },
  { id: "pl9", name: "Token budget enforcer",      by: "platform-finance · Routing", category: "Routing", description: "Hard-stops requests once a per-day token budget is exhausted. Sends a Slack nudge when 80% consumed.", stars: 4.6, installs: 748, logoLetters: "TB", logoCss: "linear-gradient(135deg,#FBBF24 0%,#34D399 100%)", installed: true },
];
