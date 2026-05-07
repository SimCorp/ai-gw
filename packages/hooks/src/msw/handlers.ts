import { http, HttpResponse } from "msw";
import type {
  Team,
  ApiKey,
  Model,
  McpServer,
  Skill,
  Plugin,
  Request,
  AuditEvent,
  Alert,
  AlertRule,
  Guardrail,
  ApprovalRequest,
} from "@aigw/contracts";

// ---------------------------------------------------------------------------
// Seed IDs — all must be valid UUIDs to satisfy IDSchema (z.string().uuid())
// ---------------------------------------------------------------------------

/** Team IDs */
const T = {
  devex:    "01900000-0000-7000-b000-000000000001",
  equity:   "01900000-0000-7000-b000-000000000002",
  risk:     "01900000-0000-7000-b000-000000000003",
  data:     "01900000-0000-7000-b000-000000000004",
  platform: "01900000-0000-7000-b000-000000000005",
} as const;

/** Key IDs */
const K = {
  k01: "01900000-0000-7000-c000-000000000001",
  k02: "01900000-0000-7000-c000-000000000002",
  k03: "01900000-0000-7000-c000-000000000003",
  k04: "01900000-0000-7000-c000-000000000004",
  k05: "01900000-0000-7000-c000-000000000005",
  k06: "01900000-0000-7000-c000-000000000006",
  k07: "01900000-0000-7000-c000-000000000007",
  k08: "01900000-0000-7000-c000-000000000008",
  k09: "01900000-0000-7000-c000-000000000009",
  k10: "01900000-0000-7000-c000-000000000010",
  k11: "01900000-0000-7000-c000-000000000011",
  k12: "01900000-0000-7000-c000-000000000012",
  k13: "01900000-0000-7000-c000-000000000013",
  k14: "01900000-0000-7000-c000-000000000014",
  k15: "01900000-0000-7000-c000-000000000015",
} as const;

/** MCP server IDs */
const M = {
  m01: "01900000-0000-7000-d000-000000000001",
  m02: "01900000-0000-7000-d000-000000000002",
  m03: "01900000-0000-7000-d000-000000000003",
  m04: "01900000-0000-7000-d000-000000000004",
  m05: "01900000-0000-7000-d000-000000000005",
  m06: "01900000-0000-7000-d000-000000000006",
  m07: "01900000-0000-7000-d000-000000000007",
  m08: "01900000-0000-7000-d000-000000000008",
  m09: "01900000-0000-7000-d000-000000000009",
  m10: "01900000-0000-7000-d000-000000000010",
} as const;

/** Skill IDs */
const S = {
  s01: "01900000-0000-7000-e000-000000000001",
  s02: "01900000-0000-7000-e000-000000000002",
  s03: "01900000-0000-7000-e000-000000000003",
  s04: "01900000-0000-7000-e000-000000000004",
  s05: "01900000-0000-7000-e000-000000000005",
  s06: "01900000-0000-7000-e000-000000000006",
  s07: "01900000-0000-7000-e000-000000000007",
  s08: "01900000-0000-7000-e000-000000000008",
  s09: "01900000-0000-7000-e000-000000000009",
  s10: "01900000-0000-7000-e000-000000000010",
  s11: "01900000-0000-7000-e000-000000000011",
  s12: "01900000-0000-7000-e000-000000000012",
} as const;

/** Plugin IDs */
const P = {
  p01: "01900000-0000-7000-f000-000000000001",
  p02: "01900000-0000-7000-f000-000000000002",
  p03: "01900000-0000-7000-f000-000000000003",
  p04: "01900000-0000-7000-f000-000000000004",
  p05: "01900000-0000-7000-f000-000000000005",
  p06: "01900000-0000-7000-f000-000000000006",
  p07: "01900000-0000-7000-f000-000000000007",
  p08: "01900000-0000-7000-f000-000000000008",
} as const;

/** Alert IDs */
const AL = {
  al01: "01900000-0000-7001-a000-000000000001",
  al02: "01900000-0000-7001-a000-000000000002",
  al03: "01900000-0000-7001-a000-000000000003",
  al04: "01900000-0000-7001-a000-000000000004",
  al05: "01900000-0000-7001-a000-000000000005",
} as const;

/** Alert rule IDs */
const AR = {
  ar01: "01900000-0000-7001-b000-000000000001",
  ar02: "01900000-0000-7001-b000-000000000002",
  ar03: "01900000-0000-7001-b000-000000000003",
  ar04: "01900000-0000-7001-b000-000000000004",
  ar05: "01900000-0000-7001-b000-000000000005",
} as const;

/** Guardrail IDs */
const G = {
  g01: "01900000-0000-7001-c000-000000000001",
  g02: "01900000-0000-7001-c000-000000000002",
  g03: "01900000-0000-7001-c000-000000000003",
  g04: "01900000-0000-7001-c000-000000000004",
  g05: "01900000-0000-7001-c000-000000000005",
  g06: "01900000-0000-7001-c000-000000000006",
} as const;

/** Approval IDs */
const AP = {
  ap01: "01900000-0000-7001-d000-000000000001",
  ap02: "01900000-0000-7001-d000-000000000002",
  ap03: "01900000-0000-7001-d000-000000000003",
  ap04: "01900000-0000-7001-d000-000000000004",
  ap05: "01900000-0000-7001-d000-000000000005",
} as const;

/** Audit event IDs */
const AE = {
  ae01: "01900000-0000-7001-e000-000000000001",
  ae02: "01900000-0000-7001-e000-000000000002",
  ae03: "01900000-0000-7001-e000-000000000003",
  ae04: "01900000-0000-7001-e000-000000000004",
  ae05: "01900000-0000-7001-e000-000000000005",
  ae06: "01900000-0000-7001-e000-000000000006",
  ae07: "01900000-0000-7001-e000-000000000007",
  ae08: "01900000-0000-7001-e000-000000000008",
  ae09: "01900000-0000-7001-e000-000000000009",
  ae10: "01900000-0000-7001-e000-000000000010",
  ae11: "01900000-0000-7001-e000-000000000011",
  ae12: "01900000-0000-7001-e000-000000000012",
  ae13: "01900000-0000-7001-e000-000000000013",
  ae14: "01900000-0000-7001-e000-000000000014",
  ae15: "01900000-0000-7001-e000-000000000015",
  ae16: "01900000-0000-7001-e000-000000000016",
  ae17: "01900000-0000-7001-e000-000000000017",
  ae18: "01900000-0000-7001-e000-000000000018",
  ae19: "01900000-0000-7001-e000-000000000019",
  ae20: "01900000-0000-7001-e000-000000000020",
} as const;

/** Request trace IDs */
const R = {
  r01: "01900000-0000-7001-f000-000000000001",
  r02: "01900000-0000-7001-f000-000000000002",
  r03: "01900000-0000-7001-f000-000000000003",
  r04: "01900000-0000-7001-f000-000000000004",
  r05: "01900000-0000-7001-f000-000000000005",
} as const;

// ---------------------------------------------------------------------------
// Teams
// ---------------------------------------------------------------------------

const seedTeams: Team[] = [
  {
    id: T.devex,
    name: "developer-experience",
    ownerEmail: "i.koivisto@simcorp.com",
    members: 9,
    keys: 7,
    tier: "team",
    budget: {
      capCents: 1_000_00,
      usedCents: 38_000,
      periodStart: "2026-05-01T00:00:00Z",
    },
    status: "good",
    alerts: [],
  },
  {
    id: T.equity,
    name: "equity-trading",
    ownerEmail: "a.kowalski@simcorp.com",
    members: 18,
    keys: 14,
    tier: "enterprise",
    budget: {
      capCents: 10_000_00,
      usedCents: 8_420_00,
      periodStart: "2026-05-01T00:00:00Z",
    },
    status: "warn",
    alerts: ["budget"],
  },
  {
    id: T.risk,
    name: "risk-engineering",
    ownerEmail: "p.fontaine@simcorp.com",
    members: 15,
    keys: 11,
    tier: "enterprise",
    budget: {
      capCents: 5_000_00,
      usedCents: 2_750_00,
      periodStart: "2026-05-01T00:00:00Z",
    },
    status: "good",
    alerts: [],
  },
  {
    id: T.data,
    name: "data-platform",
    ownerEmail: "l.gunnarsson@simcorp.com",
    members: 22,
    keys: 16,
    tier: "enterprise",
    budget: {
      capCents: 3_000_00,
      usedCents: 2_730_00,
      periodStart: "2026-05-01T00:00:00Z",
    },
    status: "warn",
    alerts: ["rate"],
  },
  {
    id: T.platform,
    name: "platform-research",
    ownerEmail: "mira.rasmussen@simcorp.com",
    members: 24,
    keys: 18,
    tier: "enterprise",
    budget: {
      capCents: 12_000_00,
      usedCents: 10_080_00,
      periodStart: "2026-05-01T00:00:00Z",
    },
    status: "good",
    alerts: ["budget"],
  },
];

// ---------------------------------------------------------------------------
// API Keys
// ---------------------------------------------------------------------------

function makeKey(
  id: string,
  teamId: string,
  label: string,
  prefix: string,
  status: ApiKey["status"] = "active"
): ApiKey {
  return {
    id,
    teamId,
    label,
    prefix,
    createdAt: "2026-03-15T09:00:00Z",
    lastUsedAt: "2026-05-07T14:42:00Z",
    createdBy: "i.koivisto@simcorp.com",
    scopes: ["inference:*"],
    rateLimit: { rpm: 60, tpm: 100_000 },
    status,
  };
}

const seedKeys: ApiKey[] = [
  makeKey(K.k01, T.devex, "prod-rag-service", "sk_live_d3a9"),
  makeKey(K.k02, T.devex, "eval-runner", "sk_live_e21b"),
  makeKey(K.k03, T.devex, "jupyter-notebook", "sk_live_f48c"),
  makeKey(K.k04, T.equity, "trading-algo", "sk_live_a11f"),
  makeKey(K.k05, T.equity, "risk-dashboard", "sk_live_b22e"),
  makeKey(K.k06, T.equity, "agent-prod", "sk_live_c33d"),
  makeKey(K.k07, T.equity, "backtest-runner", "sk_live_d44c"),
  makeKey(K.k08, T.risk, "quant-research", "sk_live_e55b", "active"),
  makeKey(K.k09, T.risk, "compliance-bot", "sk_live_f66a"),
  makeKey(K.k10, T.data, "pipeline-ingester", "sk_live_g77f"),
  makeKey(K.k11, T.data, "ml-training", "sk_live_h88e"),
  makeKey(K.k12, T.data, "feature-store", "sk_live_i99d"),
  makeKey(K.k13, T.platform, "research-agent", "sk_live_j10c"),
  makeKey(K.k14, T.platform, "benchmark-suite", "sk_live_k11b"),
  makeKey(K.k15, T.platform, "prod", "sk_live_8a4f", "rotating"),
];

// ---------------------------------------------------------------------------
// Models
// ---------------------------------------------------------------------------

const seedModels: Model[] = [
  {
    id: "anthropic/claude-sonnet-4.5",
    provider: "anthropic",
    family: "claude",
    displayName: "Claude Sonnet 4.5",
    capabilities: { vision: true, tools: true, thinking: false, context: 200_000 },
    pricing: { inputCpm: 300, outputCpm: 1500 },
    fallbacks: ["google/gemini-2.5-pro"],
    status: "active",
    region: ["us", "eu"],
  },
  {
    id: "anthropic/claude-haiku-4.5",
    provider: "anthropic",
    family: "claude",
    displayName: "Claude Haiku 4.5",
    capabilities: { vision: false, tools: true, thinking: false, context: 200_000 },
    pricing: { inputCpm: 80, outputCpm: 400 },
    fallbacks: [],
    status: "active",
    region: ["us", "eu"],
  },
  {
    id: "anthropic/claude-opus-4.5",
    provider: "anthropic",
    family: "claude",
    displayName: "Claude Opus 4.5",
    capabilities: { vision: true, tools: true, thinking: true, context: 200_000 },
    pricing: { inputCpm: 1500, outputCpm: 7500 },
    fallbacks: ["anthropic/claude-sonnet-4.5"],
    status: "active",
    region: ["us"],
  },
  {
    id: "google/gemini-2.5-pro",
    provider: "google",
    family: "gemini",
    displayName: "Gemini 2.5 Pro",
    capabilities: { vision: true, tools: true, thinking: false, context: 2_000_000 },
    pricing: { inputCpm: 125, outputCpm: 500 },
    fallbacks: ["anthropic/claude-sonnet-4.5"],
    status: "active",
    region: ["us", "eu"],
  },
  {
    id: "google/gemini-2.5-flash",
    provider: "google",
    family: "gemini",
    displayName: "Gemini 2.5 Flash",
    capabilities: { vision: true, tools: true, thinking: false, context: 1_000_000 },
    pricing: { inputCpm: 30, outputCpm: 120 },
    fallbacks: [],
    status: "active",
    region: ["us", "eu", "global"],
  },
  {
    id: "azure/gpt-5",
    provider: "azure",
    family: "gpt",
    displayName: "GPT-5 (BYO Azure)",
    capabilities: { vision: true, tools: true, thinking: false, context: 400_000 },
    pricing: { inputCpm: 500, outputCpm: 2000 },
    fallbacks: ["anthropic/claude-sonnet-4.5"],
    status: "active",
    region: ["eu"],
  },
  {
    id: "azure/gpt-5-mini",
    provider: "azure",
    family: "gpt",
    displayName: "GPT-5 Mini (BYO Azure)",
    capabilities: { vision: false, tools: true, thinking: false, context: 400_000 },
    pricing: { inputCpm: 30, outputCpm: 120 },
    fallbacks: [],
    status: "active",
    region: ["eu"],
  },
  {
    id: "openai/text-embedding-3-small",
    provider: "openai",
    family: "embedding",
    displayName: "text-embedding-3-small",
    capabilities: { vision: false, tools: false, thinking: false, context: 8_192 },
    pricing: { inputCpm: 2, outputCpm: 0 },
    fallbacks: [],
    status: "active",
    region: ["us", "eu", "global"],
  },
  {
    id: "openai/text-embedding-3-large",
    provider: "openai",
    family: "embedding",
    displayName: "text-embedding-3-large",
    capabilities: { vision: false, tools: false, thinking: false, context: 8_192 },
    pricing: { inputCpm: 13, outputCpm: 0 },
    fallbacks: [],
    status: "active",
    region: ["us", "eu"],
  },
  {
    id: "internal/llama-3.1-70b",
    provider: "internal",
    family: "llama",
    displayName: "Llama 3.1 70B (ollama-eu-1)",
    capabilities: { vision: false, tools: true, thinking: false, context: 128_000 },
    pricing: { inputCpm: 0, outputCpm: 0 },
    fallbacks: [],
    status: "active",
    region: ["eu"],
  },
];

// ---------------------------------------------------------------------------
// MCP Servers
// ---------------------------------------------------------------------------

const seedMcpServers: McpServer[] = [
  {
    id: M.m01,
    name: "portfolio-mcp",
    version: "2.4.1",
    transport: "stdio",
    source: "internal",
    ownerTeamId: T.platform,
    tools: [
      { name: "getPositions", scope: "positions:read", write: false },
      { name: "getWeights", scope: "weights:read", write: false },
      { name: "rebalance", scope: "portfolio:write", write: true },
    ],
    health: "good",
    latencyP50Ms: 74,
    errorRate: 0.0002,
    calls24h: 4218,
    approvalState: "approved",
  },
  {
    id: M.m02,
    name: "market-data-mcp",
    version: "1.9.0",
    transport: "http+sse",
    source: "internal",
    ownerTeamId: T.equity,
    tools: [
      { name: "getQuote", scope: "market:read", write: false },
      { name: "getHistorical", scope: "market:read", write: false },
    ],
    health: "good",
    latencyP50Ms: 42,
    errorRate: 0.001,
    calls24h: 3102,
    approvalState: "approved",
  },
  {
    id: M.m03,
    name: "jira-mcp",
    version: "3.1.2",
    transport: "http",
    source: "vendored",
    ownerTeamId: T.devex,
    tools: [
      { name: "createIssue", scope: "jira:write", write: true },
      { name: "searchIssues", scope: "jira:read", write: false },
    ],
    health: "good",
    latencyP50Ms: 120,
    errorRate: 0.002,
    calls24h: 1840,
    approvalState: "approved",
  },
  {
    id: M.m04,
    name: "confluence-mcp",
    version: "1.2.0",
    transport: "http",
    source: "vendored",
    ownerTeamId: T.devex,
    tools: [
      { name: "searchPages", scope: "confluence:read", write: false },
    ],
    health: "bad",
    latencyP50Ms: null,
    errorRate: 0.92,
    calls24h: 12,
    approvalState: "blocked",
  },
  {
    id: M.m05,
    name: "risk-calc-mcp",
    version: "4.0.0",
    transport: "stdio",
    source: "internal",
    ownerTeamId: T.risk,
    tools: [
      { name: "calcVaR", scope: "risk:compute", write: false },
      { name: "runStressTest", scope: "risk:compute", write: false },
    ],
    health: "good",
    latencyP50Ms: 88,
    errorRate: 0.0001,
    calls24h: 920,
    approvalState: "approved",
  },
  {
    id: M.m06,
    name: "data-catalog-mcp",
    version: "2.1.0",
    transport: "http+sse",
    source: "internal",
    ownerTeamId: T.data,
    tools: [
      { name: "searchDatasets", scope: "catalog:read", write: false },
      { name: "registerDataset", scope: "catalog:write", write: true },
    ],
    health: "good",
    latencyP50Ms: 55,
    errorRate: 0.003,
    calls24h: 640,
    approvalState: "approved",
  },
  {
    id: M.m07,
    name: "github-mcp",
    version: "1.5.0",
    transport: "http",
    source: "community",
    ownerTeamId: T.devex,
    tools: [
      { name: "searchCode", scope: "repo:read", write: false },
      { name: "createPR", scope: "repo:write", write: true },
    ],
    health: "warn",
    latencyP50Ms: 210,
    errorRate: 0.018,
    calls24h: 380,
    approvalState: "pending",
  },
  {
    id: M.m08,
    name: "order-mgmt-mcp",
    version: "3.2.1",
    transport: "stdio",
    source: "internal",
    ownerTeamId: T.equity,
    tools: [
      { name: "getOrders", scope: "orders:read", write: false },
      { name: "submitOrder", scope: "orders:write", write: true },
      { name: "cancelOrder", scope: "orders:write", write: true },
    ],
    health: "good",
    latencyP50Ms: 32,
    errorRate: 0.0005,
    calls24h: 2240,
    approvalState: "approved",
  },
  {
    id: M.m09,
    name: "docs-search-mcp",
    version: "1.0.3",
    transport: "http",
    source: "internal",
    ownerTeamId: T.devex,
    tools: [
      { name: "searchDocs", scope: "docs:read", write: false },
    ],
    health: "good",
    latencyP50Ms: 28,
    errorRate: 0.0008,
    calls24h: 1120,
    approvalState: "approved",
  },
  {
    id: M.m10,
    name: "compliance-checker-mcp",
    version: "2.0.0",
    transport: "stdio",
    source: "internal",
    ownerTeamId: T.risk,
    tools: [
      { name: "checkTrade", scope: "compliance:read", write: false },
      { name: "flagViolation", scope: "compliance:write", write: true },
    ],
    health: "good",
    latencyP50Ms: 48,
    errorRate: 0.001,
    calls24h: 780,
    approvalState: "approved",
  },
];

// ---------------------------------------------------------------------------
// Skills
// ---------------------------------------------------------------------------

const seedSkills: Skill[] = [
  {
    id: S.s01,
    name: "portfolio-summariser",
    description: "Generates natural language summaries of portfolio positions and performance.",
    ownerTeamId: T.equity,
    version: "1.3.0",
    modelId: "anthropic/claude-sonnet-4.5",
    tools: 2,
    visibility: "org",
    status: "published",
    uses7d: 480,
  },
  {
    id: S.s02,
    name: "risk-report-writer",
    description: "Produces structured risk narrative from quant data for regulatory submissions.",
    ownerTeamId: T.risk,
    version: "2.1.0",
    modelId: "anthropic/claude-opus-4.5",
    tools: 3,
    visibility: "org",
    status: "published",
    uses7d: 210,
  },
  {
    id: S.s03,
    name: "code-review-agent",
    description: "Reviews PRs for security issues, style, and performance with inline comments.",
    ownerTeamId: T.devex,
    version: "0.9.2",
    modelId: "anthropic/claude-sonnet-4.5",
    tools: 4,
    visibility: "org",
    status: "review",
    uses7d: 124,
  },
  {
    id: S.s04,
    name: "trade-explanation-skill",
    description: "Explains complex trade executions in plain language for compliance officers.",
    ownerTeamId: T.equity,
    version: "1.0.1",
    modelId: "anthropic/claude-haiku-4.5",
    tools: 1,
    visibility: "team",
    status: "published",
    uses7d: 340,
  },
  {
    id: S.s05,
    name: "data-quality-checker",
    description: "Identifies anomalies and data quality issues in financial datasets.",
    ownerTeamId: T.data,
    version: "1.2.0",
    modelId: "google/gemini-2.5-pro",
    tools: 2,
    visibility: "org",
    status: "published",
    uses7d: 180,
  },
  {
    id: S.s06,
    name: "market-commentary",
    description: "Generates daily market commentary from live price feeds and news.",
    ownerTeamId: T.equity,
    version: "3.0.0",
    modelId: "anthropic/claude-sonnet-4.5",
    tools: 3,
    visibility: "org",
    status: "frozen",
    uses7d: 0,
  },
  {
    id: S.s07,
    name: "incident-classifier",
    description: "Classifies incoming incidents by severity and routes to the right team.",
    ownerTeamId: T.platform,
    version: "1.1.0",
    modelId: "anthropic/claude-haiku-4.5",
    tools: 0,
    visibility: "org",
    status: "published",
    uses7d: 92,
  },
  {
    id: S.s08,
    name: "doc-assistant",
    description: "Answers questions about internal documentation using RAG over Confluence.",
    ownerTeamId: T.devex,
    version: "2.0.0",
    modelId: "anthropic/claude-sonnet-4.5",
    tools: 2,
    visibility: "org",
    status: "published",
    uses7d: 620,
  },
  {
    id: S.s09,
    name: "alpha-research-agent",
    description: "Explores alpha signals from alternative data sources. Experimental.",
    ownerTeamId: T.platform,
    version: "0.3.1",
    modelId: "anthropic/claude-opus-4.5",
    tools: 5,
    visibility: "private",
    status: "draft",
    uses7d: 8,
  },
  {
    id: S.s10,
    name: "sql-generator",
    description: "Converts natural language questions into optimised SQL queries.",
    ownerTeamId: T.data,
    version: "1.4.0",
    modelId: "google/gemini-2.5-flash",
    tools: 1,
    visibility: "org",
    status: "published",
    uses7d: 890,
  },
  {
    id: S.s11,
    name: "earnings-call-parser",
    description: "Extracts key guidance and metrics from earnings call transcripts.",
    ownerTeamId: T.equity,
    version: "1.0.0",
    modelId: "anthropic/claude-sonnet-4.5",
    tools: 0,
    visibility: "org",
    status: "published",
    uses7d: 145,
  },
  {
    id: S.s12,
    name: "pii-redactor",
    description: "Removes PII from documents before ingestion into RAG pipelines.",
    ownerTeamId: T.platform,
    version: "2.2.0",
    modelId: "anthropic/claude-haiku-4.5",
    tools: 0,
    visibility: "org",
    status: "published",
    uses7d: 1840,
  },
];

// ---------------------------------------------------------------------------
// Plugins
// ---------------------------------------------------------------------------

const seedPlugins: Plugin[] = [
  {
    id: P.p01,
    name: "Datadog LLM Observability",
    description: "Streams traces, tokens, and cost metrics to Datadog.",
    category: "Observability",
    source: "first-party",
    scope: "required",
    policyGate: "none",
    status: "enabled",
    teamsUsing: 42,
    teamsTotal: 42,
  },
  {
    id: P.p02,
    name: "Lakera Guard",
    description: "Real-time prompt injection and jailbreak detection.",
    category: "Safety",
    source: "vendored",
    scope: "required",
    policyGate: "none",
    status: "enabled",
    teamsUsing: 42,
    teamsTotal: 42,
  },
  {
    id: P.p03,
    name: "VS Code AI Extension",
    description: "GitHub Copilot-style inline completion via the gateway.",
    category: "Editor",
    source: "first-party",
    scope: "per-user",
    policyGate: "none",
    status: "available",
    teamsUsing: 18,
    teamsTotal: 42,
  },
  {
    id: P.p04,
    name: "LLM Eval Suite",
    description: "Automated evals with RAGAs + custom rubrics.",
    category: "Eval",
    source: "first-party",
    scope: "opt-in",
    policyGate: "cost-cap",
    status: "conditional",
    teamsUsing: 11,
    teamsTotal: 42,
  },
  {
    id: P.p05,
    name: "Semantic Router",
    description: "Routes requests to cheapest model meeting quality threshold.",
    category: "Routing",
    source: "first-party",
    scope: "opt-in",
    policyGate: "none",
    status: "enabled",
    teamsUsing: 27,
    teamsTotal: 42,
  },
  {
    id: P.p06,
    name: "Prompt Shield",
    description: "Microsoft Prompt Shield for multi-modal PII and injection.",
    category: "Safety",
    source: "vendored",
    scope: "opt-in",
    policyGate: "review",
    status: "conditional",
    teamsUsing: 6,
    teamsTotal: 42,
  },
  {
    id: P.p07,
    name: "JetBrains AI Gateway Plugin",
    description: "Inline code assistance for IntelliJ-based IDEs.",
    category: "Editor",
    source: "vendored",
    scope: "per-user",
    policyGate: "none",
    status: "available",
    teamsUsing: 9,
    teamsTotal: 42,
  },
  {
    id: P.p08,
    name: "OpenAI-compatible Proxy Router",
    description: "Allows legacy OpenAI SDK calls to route through the gateway.",
    category: "Routing",
    source: "first-party",
    scope: "required",
    policyGate: "none",
    status: "enabled",
    teamsUsing: 42,
    teamsTotal: 42,
  },
];

// ---------------------------------------------------------------------------
// Requests (live explorer seed)
// ---------------------------------------------------------------------------

const seedRequests: Request[] = [
  {
    traceId: R.r01,
    ts: "2026-05-07T14:42:08Z",
    teamId: T.platform,
    userEmail: "j.larsen@simcorp.com",
    keyPrefix: "sk_live_8a4f",
    modelId: "anthropic/claude-sonnet-4.5",
    route: "direct",
    promptTokens: 1240,
    completionTokens: 380,
    costCents: 8,
    latencyMs: 1840,
    ttftMs: 210,
    status: "ok",
    guardrailHits: [],
  },
  {
    traceId: R.r02,
    ts: "2026-05-07T14:41:55Z",
    teamId: T.data,
    userEmail: "l.gunnarsson@simcorp.com",
    keyPrefix: "sk_live_g77f",
    modelId: "google/gemini-2.5-pro",
    route: "direct",
    promptTokens: 8420,
    completionTokens: 1120,
    costCents: 16,
    latencyMs: 2210,
    ttftMs: 310,
    status: "ok",
    guardrailHits: [],
  },
  {
    traceId: R.r03,
    ts: "2026-05-07T14:40:12Z",
    teamId: T.equity,
    userEmail: "a.kowalski@simcorp.com",
    keyPrefix: "sk_live_a11f",
    modelId: "azure/gpt-5",
    route: "direct",
    promptTokens: 2100,
    completionTokens: 540,
    costCents: 21,
    latencyMs: 4820,
    ttftMs: 820,
    status: "error",
    guardrailHits: [],
  },
  {
    traceId: R.r04,
    ts: "2026-05-07T14:39:08Z",
    teamId: T.risk,
    userEmail: "p.fontaine@simcorp.com",
    keyPrefix: "sk_live_e55b",
    modelId: "anthropic/claude-opus-4.5",
    route: "cache",
    promptTokens: 3200,
    completionTokens: 0,
    costCents: 0,
    latencyMs: 48,
    ttftMs: 48,
    status: "ok",
    guardrailHits: [],
  },
  {
    traceId: R.r05,
    ts: "2026-05-07T14:38:30Z",
    teamId: T.devex,
    userEmail: "i.koivisto@simcorp.com",
    keyPrefix: "sk_live_d3a9",
    modelId: "anthropic/claude-sonnet-4.5",
    route: "direct",
    promptTokens: 580,
    completionTokens: 120,
    costCents: 3,
    latencyMs: 940,
    ttftMs: 124,
    status: "blocked",
    guardrailHits: [{ name: "PII detector", action: "block" }],
  },
];

// ---------------------------------------------------------------------------
// Audit events
// ---------------------------------------------------------------------------

const seedAuditEvents: AuditEvent[] = [
  {
    id: AE.ae01,
    ts: "2026-05-07T14:42:08Z",
    actor: { email: "j.larsen@simcorp.com", role: "gateway-admin" },
    action: "key.rotate",
    resource: "team/platform-research/keys/k15",
    outcome: "success",
    traceId: R.r01,
  },
  {
    id: AE.ae02,
    ts: "2026-05-07T14:38:55Z",
    actor: { system: "rate-limiter" },
    action: "team.throttle",
    resource: "team/data-platform",
    outcome: "blocked",
    traceId: R.r02,
  },
  {
    id: AE.ae03,
    ts: "2026-05-07T14:21:11Z",
    actor: { email: "m.rasmussen@simcorp.com", role: "gateway-admin" },
    action: "policy.update",
    resource: "policy/org/cache_threshold",
    outcome: "success",
    traceId: R.r03,
    diffUrl: "https://admin.example.com/diff/policy-ae03",
  },
  {
    id: AE.ae04,
    ts: "2026-05-07T13:58:02Z",
    actor: { email: "k.haukur@simcorp.com", role: "gateway-admin" },
    action: "team.create",
    resource: "team/nordic-research",
    outcome: "success",
    traceId: R.r04,
  },
  {
    id: AE.ae05,
    ts: "2026-05-07T13:44:30Z",
    actor: { system: "failover-controller" },
    action: "provider.failover",
    resource: "provider/anthropic",
    outcome: "success",
    traceId: R.r05,
  },
  {
    id: AE.ae06,
    ts: "2026-05-07T13:12:04Z",
    actor: { email: "a.silva@simcorp.com", role: "gateway-admin" },
    action: "key.revoke",
    resource: "team/client-services-ai/keys/sk_live_••••a31f",
    outcome: "success",
    traceId: R.r01,
  },
  {
    id: AE.ae07,
    ts: "2026-05-07T12:55:40Z",
    actor: { email: "i.koivisto@simcorp.com", role: "gateway-auditor" },
    action: "guardrail.update",
    resource: "guardrail/pii-detector",
    outcome: "success",
    traceId: R.r02,
  },
  {
    id: AE.ae08,
    ts: "2026-05-07T12:31:18Z",
    actor: { email: "p.fontaine@simcorp.com", role: "gateway-admin" },
    action: "model.register",
    resource: "model/internal/llama-3.1-70b",
    outcome: "success",
    traceId: R.r03,
  },
  {
    id: AE.ae09,
    ts: "2026-05-07T11:48:22Z",
    actor: { email: "mira.rasmussen@simcorp.com", role: "gateway-admin" },
    action: "skill.freeze",
    resource: "skill/market-commentary",
    outcome: "success",
    traceId: R.r04,
  },
  {
    id: AE.ae10,
    ts: "2026-05-07T11:22:05Z",
    actor: { email: "a.kowalski@simcorp.com", role: "gateway-admin" },
    action: "team.budget.update",
    resource: "team/equity-trading/budget",
    outcome: "success",
    traceId: R.r05,
    diffUrl: "https://admin.example.com/diff/budget-ae10",
  },
  {
    id: AE.ae11,
    ts: "2026-05-07T10:55:12Z",
    actor: { system: "guardrail-engine" },
    action: "request.block",
    resource: "guardrail/pii-detector",
    outcome: "blocked",
    traceId: R.r05,
  },
  {
    id: AE.ae12,
    ts: "2026-05-07T10:18:44Z",
    actor: { email: "l.gunnarsson@simcorp.com", role: "gateway-admin" },
    action: "key.create",
    resource: "team/data-platform/keys/k12",
    outcome: "success",
    traceId: R.r01,
  },
  {
    id: AE.ae13,
    ts: "2026-05-07T09:42:33Z",
    actor: { email: "i.koivisto@simcorp.com", role: "gateway-admin" },
    action: "plugin.enable",
    resource: "plugin/semantic-router",
    outcome: "success",
    traceId: R.r02,
  },
  {
    id: AE.ae14,
    ts: "2026-05-07T09:10:08Z",
    actor: { email: "mira.rasmussen@simcorp.com", role: "gateway-admin" },
    action: "policy.promote",
    resource: "policy/research-eu/v3",
    outcome: "pending",
    traceId: R.r03,
    diffUrl: "https://admin.example.com/diff/policy-ae14",
  },
  {
    id: AE.ae15,
    ts: "2026-05-07T08:38:50Z",
    actor: { system: "drift-detector" },
    action: "model.drift",
    resource: "model/azure/gpt-5",
    outcome: "drift",
    traceId: R.r04,
  },
  {
    id: AE.ae16,
    ts: "2026-05-07T08:02:14Z",
    actor: { email: "k.haukur@simcorp.com", role: "gateway-admin" },
    action: "mcp.register",
    resource: "mcp/compliance-checker-mcp",
    outcome: "success",
    traceId: R.r05,
  },
  {
    id: AE.ae17,
    ts: "2026-05-07T07:44:22Z",
    actor: { email: "j.larsen@simcorp.com", role: "gateway-admin" },
    action: "skill.publish",
    resource: "skill/sql-generator/v1.4.0",
    outcome: "success",
    traceId: R.r01,
  },
  {
    id: AE.ae18,
    ts: "2026-05-07T07:20:00Z",
    actor: { email: "a.silva@simcorp.com", role: "gateway-auditor" },
    action: "audit.export",
    resource: "audit/export/2026-05-06",
    outcome: "success",
    traceId: R.r02,
  },
  {
    id: AE.ae19,
    ts: "2026-05-07T06:55:18Z",
    actor: { system: "budget-monitor" },
    action: "team.alert",
    resource: "team/equity-trading/budget",
    outcome: "success",
    traceId: R.r03,
  },
  {
    id: AE.ae20,
    ts: "2026-05-07T06:30:42Z",
    actor: { email: "p.fontaine@simcorp.com", role: "gateway-admin" },
    action: "guardrail.reorder",
    resource: "guardrail/pipeline",
    outcome: "success",
    traceId: R.r04,
  },
];

// ---------------------------------------------------------------------------
// Alerts
// ---------------------------------------------------------------------------

const seedAlerts: Alert[] = [
  {
    id: AL.al01,
    severity: "P1",
    ruleId: AR.ar01,
    ruleName: "Azure 5xx surge",
    triggeredAt: "2026-05-07T14:20:00Z",
    firstSeen: "2026-05-07T14:20:00Z",
    ownerTeamId: T.equity,
    status: "firing",
  },
  {
    id: AL.al02,
    severity: "P2",
    ruleId: AR.ar02,
    ruleName: "Team rate-limit spike",
    triggeredAt: "2026-05-07T14:30:00Z",
    firstSeen: "2026-05-07T14:30:00Z",
    ownerTeamId: T.data,
    status: "firing",
  },
  {
    id: AL.al03,
    severity: "P2",
    ruleId: AR.ar03,
    ruleName: "Budget 80% threshold",
    triggeredAt: "2026-05-07T12:00:00Z",
    firstSeen: "2026-05-07T12:00:00Z",
    ownerTeamId: T.equity,
    status: "acked",
    ackBy: "a.kowalski@simcorp.com",
    ackAt: "2026-05-07T12:15:00Z",
  },
  {
    id: AL.al04,
    severity: "P3",
    ruleId: AR.ar04,
    ruleName: "MCP latency p95 elevated",
    triggeredAt: "2026-05-07T10:00:00Z",
    firstSeen: "2026-05-07T10:00:00Z",
    ownerTeamId: T.platform,
    status: "firing",
  },
  {
    id: AL.al05,
    severity: "P2",
    ruleId: AR.ar05,
    ruleName: "PII guardrail hits spike",
    triggeredAt: "2026-05-07T09:40:00Z",
    firstSeen: "2026-05-07T09:40:00Z",
    ownerTeamId: null,
    status: "firing",
  },
];

const seedAlertRules: AlertRule[] = [
  {
    id: AR.ar01,
    name: "Azure 5xx surge",
    severity: "P1",
    metric: "provider.error_rate",
    comparator: ">",
    threshold: 0.05,
    window: "5m",
    scope: "org",
    channels: [],
    active: true,
  },
  {
    id: AR.ar02,
    name: "Team rate-limit spike",
    severity: "P2",
    metric: "team.rate_limit.429_count",
    comparator: ">",
    threshold: 100,
    window: "10m",
    scope: "org",
    channels: [],
    active: true,
  },
  {
    id: AR.ar03,
    name: "Budget 80% threshold",
    severity: "P2",
    metric: "budget.team.monthly",
    comparator: ">=",
    threshold: 0.8,
    window: "1h",
    scope: "org",
    channels: [],
    active: true,
  },
  {
    id: AR.ar04,
    name: "MCP latency p95 elevated",
    severity: "P3",
    metric: "latency.p95",
    comparator: ">",
    threshold: 500,
    window: "15m",
    scope: { teamIds: [T.platform, T.data] },
    channels: [],
    active: true,
  },
  {
    id: AR.ar05,
    name: "PII guardrail hits spike",
    severity: "P2",
    metric: "guardrail.pii.hits",
    comparator: ">",
    threshold: 50,
    window: "5m",
    scope: "org",
    channels: [],
    active: true,
  },
];

// ---------------------------------------------------------------------------
// Guardrails
// ---------------------------------------------------------------------------

const seedGuardrails: Guardrail[] = [
  {
    id: G.g01,
    name: "PII detector · names + accounts",
    description: "Presidio + custom EU client-ID regex. Blocks EU client IDs, names, IBANs.",
    stage: "input",
    action: "block",
    scope: { include: "org" },
    config: { model: "presidio", languages: ["en", "de", "da"], threshold: 0.85 },
    order: 1,
    hits24h: 87,
    enabled: true,
  },
  {
    id: G.g02,
    name: "Prompt injection shield",
    description: "Lakera Guard + custom heuristics for jailbreak and injection.",
    stage: "input",
    action: "block",
    scope: { include: "org" },
    config: { provider: "lakera", sensitivity: "high" },
    order: 2,
    hits24h: 24,
    enabled: true,
  },
  {
    id: G.g03,
    name: "Token budget enforcer",
    description: "Truncates prompts exceeding per-team context budget.",
    stage: "input",
    action: "truncate",
    scope: { include: "org" },
    config: { maxTokens: 100_000 },
    order: 3,
    hits24h: 12,
    enabled: true,
  },
  {
    id: G.g04,
    name: "Competitor mention flag",
    description: "Flags responses mentioning competitor products for review.",
    stage: "output",
    action: "flag",
    scope: { include: "org" },
    config: { competitors: ["Bloomberg Terminal", "FactSet", "Refinitiv"] },
    order: 4,
    hits24h: 31,
    enabled: true,
  },
  {
    id: G.g05,
    name: "Output PII redactor",
    description: "Redacts PII in model completions before returning to caller.",
    stage: "output",
    action: "redact",
    scope: { include: "org" },
    config: { model: "presidio", entities: ["PERSON", "EMAIL_ADDRESS", "IBAN_CODE"] },
    order: 5,
    hits24h: 42,
    enabled: true,
  },
  {
    id: G.g06,
    name: "Hallucination rewriter",
    description: "Rewrites responses with unverifiable financial figures with disclaimers.",
    stage: "output",
    action: "rewrite",
    scope: { include: [T.equity, T.risk] },
    config: { model: "anthropic/claude-haiku-4.5", maxRetries: 2 },
    order: 6,
    hits24h: 18,
    enabled: true,
  },
];

// ---------------------------------------------------------------------------
// Approvals
// ---------------------------------------------------------------------------

const seedApprovals: ApprovalRequest[] = [
  {
    id: AP.ap01,
    type: "skill.publish",
    subject: "code-review-agent v0.9.2",
    requestedBy: "i.koivisto@simcorp.com",
    requestedAt: "2026-05-07T08:00:00Z",
    teamId: T.devex,
    status: "pending",
    slaHours: 6,
  },
  {
    id: AP.ap02,
    type: "mcp.scope",
    subject: "github-mcp · repo:write",
    requestedBy: "i.koivisto@simcorp.com",
    requestedAt: "2026-05-06T12:00:00Z",
    teamId: T.devex,
    status: "pending",
    slaHours: 26,
  },
  {
    id: AP.ap03,
    type: "plugin.install",
    subject: "Prompt Shield (JetBrains)",
    requestedBy: "a.kowalski@simcorp.com",
    requestedAt: "2026-05-05T09:00:00Z",
    teamId: T.equity,
    status: "pending",
    slaHours: 53,
  },
  {
    id: AP.ap04,
    type: "policy.promote",
    subject: "policy/research-eu/v3 → org",
    requestedBy: "mira.rasmussen@simcorp.com",
    requestedAt: "2026-05-07T09:14:00Z",
    teamId: T.platform,
    status: "pending",
    slaHours: 5,
  },
  {
    id: AP.ap05,
    type: "skill.publish",
    subject: "alpha-research-agent v0.3.1",
    requestedBy: "mira.rasmussen@simcorp.com",
    requestedAt: "2026-05-03T14:00:00Z",
    teamId: T.platform,
    status: "rejected",
    slaHours: 100,
  },
];

// ---------------------------------------------------------------------------
// Me (current user)
// ---------------------------------------------------------------------------

const seedMe = {
  user: {
    email: "bntp@simcorp.com",
    name: "B. Nielsen",
    avatar: null,
  },
  roles: ["gateway-admin"],
  teams: [T.platform],
};

// ---------------------------------------------------------------------------
// Usage (current user)
// ---------------------------------------------------------------------------

const seedUsageMe = {
  range: "30d",
  totalCostCents: 28410,
  requestCount: 38412,
  promptTokens: 42_000_000,
  completionTokens: 8_100_000,
  cacheHitRate: 0.38,
  cacheSavingsCents: 9800,
  byDate: Array.from({ length: 30 }, (_, i) => ({
    date: new Date(Date.UTC(2026, 3, 7 + i)).toISOString().slice(0, 10),
    sonnet: Math.round(600 + Math.random() * 400),
    haiku: Math.round(100 + Math.random() * 200),
    gemini: Math.round(80 + Math.random() * 150),
    cacheSavings: -Math.round(50 + Math.random() * 100),
  })),
};

// ---------------------------------------------------------------------------
// Cache config
// ---------------------------------------------------------------------------

const seedCacheConfig = {
  enabled: true,
  semanticThreshold: 0.94,
  ttlSeconds: 3600,
  maxSizeMb: 32768,
  exactMatchEnabled: true,
  semanticMatchEnabled: true,
  embeddingModel: "openai/text-embedding-3-small",
};

// ---------------------------------------------------------------------------
// Providers
// ---------------------------------------------------------------------------

const seedProviders = [
  { id: "prov01", name: "Anthropic", status: "good", latencyMs: 28, errorRate: 0.001 },
  { id: "prov02", name: "Google Gemini", status: "good", latencyMs: 41, errorRate: 0.0008 },
  { id: "prov03", name: "Azure OpenAI (BYO)", status: "bad", latencyMs: null, errorRate: 0.082 },
  { id: "prov04", name: "GitHub Models", status: "warn", latencyMs: 187, errorRate: 0.014 },
  { id: "prov05", name: "Ollama (eu-1)", status: "good", latencyMs: 12, errorRate: 0.0002 },
];

// ---------------------------------------------------------------------------
// Prompts
// ---------------------------------------------------------------------------

const seedPrompts = [
  { id: "pr01", name: "Trade summariser", description: "Concise trade execution summary", teamId: T.equity, version: "1.0", uses7d: 240 },
  { id: "pr02", name: "Code review assistant", description: "Review code for issues", teamId: T.devex, version: "2.1", uses7d: 180 },
  { id: "pr03", name: "Risk narrative", description: "Generate risk reports", teamId: T.risk, version: "1.2", uses7d: 120 },
  { id: "pr04", name: "Data quality check", description: "Identify data anomalies", teamId: T.data, version: "1.0", uses7d: 90 },
];

// ---------------------------------------------------------------------------
// Agents
// ---------------------------------------------------------------------------

const seedAgents = [
  { id: "ag01", name: "portfolio-rebalancer", status: "active", teamId: T.equity, lastRunAt: "2026-05-07T13:00:00Z", runsToday: 4 },
  { id: "ag02", name: "doc-assistant", status: "active", teamId: T.devex, lastRunAt: "2026-05-07T14:30:00Z", runsToday: 28 },
  { id: "ag03", name: "risk-monitor", status: "idle", teamId: T.risk, lastRunAt: "2026-05-07T10:00:00Z", runsToday: 1 },
];

// ---------------------------------------------------------------------------
// Policies (minimal seed)
// ---------------------------------------------------------------------------

const seedPolicies = [
  {
    id: "pol01",
    name: "org/default",
    version: "v4",
    updatedAt: "2026-05-07T14:21:11Z",
    updatedBy: "m.rasmussen@simcorp.com",
    scope: "org",
    status: "active",
  },
  {
    id: "pol02",
    name: "team/equity-trading",
    version: "v2",
    updatedAt: "2026-05-07T11:22:05Z",
    updatedBy: "a.kowalski@simcorp.com",
    scope: "team",
    status: "active",
  },
  {
    id: "pol03",
    name: "policy/research-eu",
    version: "v3",
    updatedAt: "2026-05-07T09:14:00Z",
    updatedBy: "mira.rasmussen@simcorp.com",
    scope: "team",
    status: "pending",
  },
];

// ---------------------------------------------------------------------------
// Quotas
// ---------------------------------------------------------------------------

const seedQuotas = seedTeams.map((team) => ({
  teamId: team.id,
  teamName: team.name,
  rpmCap: 60,
  tpmCap: 100_000,
  monthlyCostCapCents: team.budget.capCents,
  usedCostCents: team.budget.usedCents,
  usedRpm: Math.round(Math.random() * 50),
  forecastCents: Math.round(team.budget.usedCents * 1.15),
}));

// ---------------------------------------------------------------------------
// Handlers
// ---------------------------------------------------------------------------

export const handlers = [
  // ------ Auth ------
  http.get("/api/v1/me", () => HttpResponse.json(seedMe)),

  // ------ Teams ------
  http.get("/api/v1/teams", () => HttpResponse.json(seedTeams)),

  http.get("/api/v1/teams/:id", ({ params }) => {
    const team = seedTeams.find((t) => t.id === params.id);
    if (!team) return new HttpResponse(null, { status: 404 });
    return HttpResponse.json(team);
  }),

  http.post("/api/v1/teams", async ({ request }) => {
    const body = (await request.json()) as Partial<Team>;
    return HttpResponse.json({ id: crypto.randomUUID(), etag: "v1", ...body }, { status: 201 });
  }),

  http.patch("/api/v1/teams/:id", async ({ params, request }) => {
    const body = (await request.json()) as Partial<Team>;
    return HttpResponse.json({ id: params.id, etag: "v2", ...body });
  }),

  // ------ Team members ------
  http.get("/api/v1/teams/:id/members", ({ params }) => {
    const team = seedTeams.find((t) => t.id === params.id);
    if (!team) return new HttpResponse(null, { status: 404 });
    return HttpResponse.json([
      { email: team.ownerEmail, role: "Owner", joinedAt: "2026-01-01T00:00:00Z" },
      { email: "dev1@simcorp.com", role: "Editor", joinedAt: "2026-02-01T00:00:00Z" },
    ]);
  }),

  http.post("/api/v1/teams/:id/members", async ({ request }) => {
    const body = (await request.json()) as { email: string; role: string };
    return HttpResponse.json({ id: crypto.randomUUID(), etag: "v1", ...body }, { status: 201 });
  }),

  http.delete("/api/v1/teams/:id/members/:email", () =>
    new HttpResponse(null, { status: 204 })
  ),

  // ------ Keys ------
  http.get("/api/v1/teams/:id/keys", ({ params }) => {
    const keys = seedKeys.filter((k) => k.teamId === params.id);
    return HttpResponse.json(keys);
  }),

  http.post("/api/v1/teams/:id/keys", async ({ params, request }) => {
    const body = (await request.json()) as Partial<ApiKey>;
    const newKey: ApiKey & { secret: string } = {
      id: crypto.randomUUID(),
      teamId: params.id as string,
      label: body.label ?? "new-key",
      prefix: "sk_live_" + Math.random().toString(36).slice(2, 6),
      createdAt: new Date().toISOString(),
      lastUsedAt: null,
      createdBy: "bntp@simcorp.com",
      scopes: body.scopes ?? ["inference:*"],
      rateLimit: body.rateLimit ?? { rpm: 60, tpm: 100_000 },
      status: "active",
      secret: "sk_live_" + crypto.randomUUID().replace(/-/g, ""),
    };
    return HttpResponse.json(newKey, { status: 201 });
  }),

  http.post("/api/v1/teams/:id/keys/:kid/rotate", ({ params }) =>
    HttpResponse.json({ id: params.kid, etag: "v2", status: "rotating" })
  ),

  http.delete("/api/v1/teams/:id/keys/:kid", () =>
    new HttpResponse(null, { status: 204 })
  ),

  // ------ Policies ------
  http.get("/api/v1/policies", () => HttpResponse.json(seedPolicies)),

  http.get("/api/v1/policies/:id", ({ params }) => {
    const policy = seedPolicies.find((p) => p.id === params.id);
    if (!policy) return new HttpResponse(null, { status: 404 });
    return HttpResponse.json(policy);
  }),

  http.patch("/api/v1/policies/:id", async ({ params, request }) => {
    const body = (await request.json()) as object;
    return HttpResponse.json({ id: params.id, etag: "v5", ...body });
  }),

  http.post("/api/v1/policies/:id/version", ({ params }) =>
    HttpResponse.json({ id: params.id, etag: "v_new", version: "v5" }, { status: 201 })
  ),

  // ------ Guardrails ------
  http.get("/api/v1/guardrails", () => HttpResponse.json(seedGuardrails)),

  http.patch("/api/v1/guardrails/order", async ({ request }) => {
    const body = (await request.json()) as { order: string[] };
    return HttpResponse.json({ updated: body.order.length });
  }),

  http.post("/api/v1/guardrails/test", async ({ request }) => {
    const body = (await request.json()) as { prompt: string };
    return HttpResponse.json({
      input: [{ guardrailId: G.g01, name: "PII detector", action: "block", hit: body.prompt.includes("@") }],
      output: [],
    });
  }),

  // ------ Quotas ------
  http.get("/api/v1/quotas", () => HttpResponse.json(seedQuotas)),

  http.patch("/api/v1/quotas/:teamId", async ({ params, request }) => {
    const body = (await request.json()) as object;
    return HttpResponse.json({ teamId: params.teamId, etag: "v2", ...body });
  }),

  // ------ Approvals ------
  http.get("/api/v1/approvals", ({ request }) => {
    const url = new URL(request.url);
    const status = url.searchParams.get("status");
    const filtered = status
      ? seedApprovals.filter((a) => a.status === status)
      : seedApprovals;
    return HttpResponse.json(filtered);
  }),

  http.post("/api/v1/approvals/:id/approve", ({ params }) =>
    HttpResponse.json({ id: params.id, etag: "v2", status: "approved" })
  ),

  http.post("/api/v1/approvals/:id/reject", ({ params }) =>
    HttpResponse.json({ id: params.id, etag: "v2", status: "rejected" })
  ),

  // ------ Models ------
  http.get("/api/v1/models", () => HttpResponse.json(seedModels)),

  http.get("/api/v1/models/:id/health", ({ params }) => {
    const model = seedModels.find((m) => m.id === params.id);
    const status = model?.status === "active" ? "good" : "bad";
    return HttpResponse.json({ id: params.id, health: status, latencyMs: 38 });
  }),

  // ------ MCP servers ------
  http.get("/api/v1/mcp", () => HttpResponse.json(seedMcpServers)),

  http.get("/api/v1/mcp/:id/health", ({ params }) => {
    const server = seedMcpServers.find((s) => s.id === params.id);
    return HttpResponse.json({ id: params.id, health: server?.health ?? "bad", latencyP50Ms: server?.latencyP50Ms ?? null });
  }),

  http.post("/api/v1/mcp/:id/reconnect", ({ params }) =>
    HttpResponse.json({ id: params.id, etag: "v2", health: "good" })
  ),

  // ------ Skills ------
  http.get("/api/v1/skills", () => HttpResponse.json(seedSkills)),

  http.post("/api/v1/skills", async ({ request }) => {
    const body = (await request.json()) as Partial<Skill>;
    return HttpResponse.json({ id: crypto.randomUUID(), etag: "v1", ...body }, { status: 201 });
  }),

  http.post("/api/v1/skills/:id/freeze", ({ params }) =>
    HttpResponse.json({ id: params.id, etag: "v2", status: "frozen" })
  ),

  // ------ Plugins ------
  http.get("/api/v1/plugins", () => HttpResponse.json(seedPlugins)),

  http.post("/api/v1/plugins/:id/install", ({ params }) =>
    HttpResponse.json({ id: params.id, etag: "v2", status: "enabled" })
  ),

  http.post("/api/v1/plugins/:id/uninstall", ({ params }) =>
    HttpResponse.json({ id: params.id, etag: "v2", status: "available" })
  ),

  // ------ Cache ------
  http.get("/api/v1/cache/config", () => HttpResponse.json(seedCacheConfig)),

  http.patch("/api/v1/cache/config", async ({ request }) => {
    const body = (await request.json()) as object;
    return HttpResponse.json({ etag: "v2", ...seedCacheConfig, ...body });
  }),

  // ------ Providers ------
  http.get("/api/v1/providers", () => HttpResponse.json(seedProviders)),

  http.patch("/api/v1/providers/:id", async ({ params, request }) => {
    const body = (await request.json()) as object;
    return HttpResponse.json({ id: params.id, etag: "v2", ...body });
  }),

  // ------ Requests ------
  http.get("/api/v1/requests", ({ request }) => {
    const url = new URL(request.url);
    const teamId = url.searchParams.get("team");
    const filtered = teamId
      ? seedRequests.filter((r) => r.teamId === teamId)
      : seedRequests;
    return HttpResponse.json({
      data: filtered,
      cursor: null,
      total: filtered.length,
    });
  }),

  // SSE stream — returns a small fixed event batch
  http.get("/api/v1/requests/stream", () => {
    const encoder = new TextEncoder();
    const events = seedRequests
      .map((r) => `data: ${JSON.stringify(r)}\n\n`)
      .join("");

    const stream = new ReadableStream({
      start(controller) {
        controller.enqueue(encoder.encode(events));
        // Keep the stream open but don't add more data in the mock
        // (real server would push indefinitely)
        controller.close();
      },
    });

    return new HttpResponse(stream, {
      headers: {
        "Content-Type": "text/event-stream",
        "Cache-Control": "no-cache",
        Connection: "keep-alive",
      },
    });
  }),

  // ------ Alerts ------
  http.get("/api/v1/alerts", () => HttpResponse.json(seedAlerts)),
  http.get("/api/v1/alert-rules", () => HttpResponse.json(seedAlertRules)),

  http.post("/api/v1/alerts/:id/ack", async ({ params, request }) => {
    const body = (await request.json()) as { comment?: string };
    return HttpResponse.json({
      id: params.id,
      etag: "v2",
      status: "acked",
      ackBy: seedMe.user.email,
      ackAt: new Date().toISOString(),
      comment: body.comment,
    });
  }),

  // ------ Audit ------
  http.get("/api/v1/audit", ({ request }) => {
    const url = new URL(request.url);
    const limit = parseInt(url.searchParams.get("limit") ?? "20", 10);
    const data = seedAuditEvents.slice(0, limit);
    return HttpResponse.json({ data, cursor: null, total: seedAuditEvents.length });
  }),

  http.get("/api/v1/audit/export", () =>
    HttpResponse.json({ jobId: crypto.randomUUID(), status: "queued" })
  ),

  // ------ Playground ------
  http.post("/api/v1/playground/run", () => {
    const encoder = new TextEncoder();
    const tokens = ["This ", "is ", "a ", "mock ", "streaming ", "response ", "from ", "the ", "gateway."];
    const stream = new ReadableStream({
      start(controller) {
        for (const token of tokens) {
          controller.enqueue(
            encoder.encode(`data: ${JSON.stringify({ token, done: false })}\n\n`)
          );
        }
        controller.enqueue(
          encoder.encode(`data: ${JSON.stringify({ token: "", done: true })}\n\n`)
        );
        controller.close();
      },
    });
    return new HttpResponse(stream, {
      headers: {
        "Content-Type": "text/event-stream",
        "Cache-Control": "no-cache",
      },
    });
  }),

  // ------ Portal usage ------
  http.get("/api/v1/usage/me", () => HttpResponse.json(seedUsageMe)),

  // ------ Prompts ------
  http.get("/api/v1/prompts", () => HttpResponse.json(seedPrompts)),

  // ------ Agents ------
  http.get("/api/v1/agents", () => HttpResponse.json(seedAgents)),
];
