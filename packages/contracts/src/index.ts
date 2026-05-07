import { z } from "zod";

// ---------------------------------------------------------------------------
// Primitive scalars
// ---------------------------------------------------------------------------

export const IDSchema = z.string().uuid();
export type ID = z.infer<typeof IDSchema>;

export const ISODateSchema = z.string().datetime({ offset: true });
export type ISODate = z.infer<typeof ISODateSchema>;

export const MoneySchema = z.object({
  cents: z.number().int(),
  currency: z.enum(["USD", "EUR", "DKK"]),
});
export type Money = z.infer<typeof MoneySchema>;

export const SeveritySchema = z.enum(["P1", "P2", "P3"]);
export type Severity = z.infer<typeof SeveritySchema>;

export const StatusSchema = z.enum(["good", "warn", "bad", "info"]);
export type Status = z.infer<typeof StatusSchema>;

// ---------------------------------------------------------------------------
// Team
// ---------------------------------------------------------------------------

export const TeamSchema = z.object({
  id: IDSchema,
  name: z.string(),
  ownerEmail: z.string().email(),
  members: z.number().int().nonnegative(),
  keys: z.number().int().nonnegative(),
  tier: z.enum(["free", "team", "enterprise"]),
  budget: z.object({
    capCents: z.number().int(),
    usedCents: z.number().int(),
    periodStart: ISODateSchema,
  }),
  status: StatusSchema,
  alerts: z.array(z.enum(["budget", "rate", "drift", "policy"])),
});
export type Team = z.infer<typeof TeamSchema>;

// ---------------------------------------------------------------------------
// ApiKey
// ---------------------------------------------------------------------------

export const ApiKeySchema = z.object({
  id: IDSchema,
  teamId: IDSchema,
  label: z.string(),
  prefix: z.string(), // "sk_live_8a4f"
  createdAt: ISODateSchema,
  lastUsedAt: ISODateSchema.nullable(),
  createdBy: z.string(),
  scopes: z.array(z.string()),
  rateLimit: z.object({
    rpm: z.number().int().nonnegative(),
    tpm: z.number().int().nonnegative(),
  }),
  status: z.enum(["active", "rotating", "revoked"]),
});
export type ApiKey = z.infer<typeof ApiKeySchema>;

// ---------------------------------------------------------------------------
// Model
// ---------------------------------------------------------------------------

export const ModelSchema = z.object({
  id: z.string(), // "anthropic/claude-sonnet-4.5"
  provider: z.enum(["anthropic", "openai", "azure", "google", "internal"]),
  family: z.string(),
  displayName: z.string(),
  capabilities: z.object({
    vision: z.boolean(),
    tools: z.boolean(),
    thinking: z.boolean(),
    context: z.number().int().positive(),
  }),
  pricing: z.object({
    inputCpm: z.number().nonnegative(), // cents per million tokens
    outputCpm: z.number().nonnegative(),
  }),
  fallbacks: z.array(z.string()),
  status: z.enum(["active", "deprecated", "preview"]),
  region: z.array(z.enum(["us", "eu", "global"])),
});
export type Model = z.infer<typeof ModelSchema>;

// ---------------------------------------------------------------------------
// McpServer
// ---------------------------------------------------------------------------

export const McpServerSchema = z.object({
  id: IDSchema,
  name: z.string(),
  version: z.string(),
  transport: z.enum(["stdio", "http", "http+sse"]),
  source: z.enum(["internal", "vendored", "community"]),
  ownerTeamId: IDSchema,
  tools: z.array(
    z.object({
      name: z.string(),
      scope: z.string(),
      write: z.boolean(),
    })
  ),
  health: StatusSchema,
  latencyP50Ms: z.number().nullable(),
  errorRate: z.number().nonnegative(),
  calls24h: z.number().int().nonnegative(),
  approvalState: z.enum(["approved", "pending", "blocked"]),
});
export type McpServer = z.infer<typeof McpServerSchema>;

// ---------------------------------------------------------------------------
// Skill
// ---------------------------------------------------------------------------

export const SkillSchema = z.object({
  id: IDSchema,
  name: z.string(),
  description: z.string(),
  ownerTeamId: IDSchema,
  version: z.string(),
  modelId: z.string(),
  tools: z.number().int().nonnegative(),
  visibility: z.enum(["private", "team", "org"]),
  status: z.enum(["draft", "review", "published", "frozen", "blocked"]),
  uses7d: z.number().int().nonnegative(),
});
export type Skill = z.infer<typeof SkillSchema>;

// ---------------------------------------------------------------------------
// Plugin
// ---------------------------------------------------------------------------

export const PluginSchema = z.object({
  id: IDSchema,
  name: z.string(),
  description: z.string(),
  category: z.enum(["Observability", "Safety", "Routing", "Editor", "Eval"]),
  source: z.enum(["first-party", "vendored", "community"]),
  scope: z.enum(["required", "opt-in", "per-user"]),
  policyGate: z.enum(["none", "cost-cap", "review", "blocked"]),
  status: z.enum(["enabled", "available", "conditional", "blocked"]),
  teamsUsing: z.number().int().nonnegative(),
  teamsTotal: z.number().int().nonnegative(),
});
export type Plugin = z.infer<typeof PluginSchema>;

// ---------------------------------------------------------------------------
// Request (live explorer)
// ---------------------------------------------------------------------------

export const RequestSchema = z.object({
  traceId: IDSchema,
  ts: ISODateSchema,
  teamId: IDSchema,
  userEmail: z.string(),
  keyPrefix: z.string(),
  modelId: z.string(),
  route: z.enum(["direct", "fallback", "cache"]),
  promptTokens: z.number().int().nonnegative(),
  completionTokens: z.number().int().nonnegative(),
  costCents: z.number().nonnegative(),
  latencyMs: z.number().nonnegative(),
  ttftMs: z.number().nonnegative(),
  status: z.enum(["ok", "blocked", "error", "rate-limited"]),
  guardrailHits: z.array(
    z.object({
      name: z.string(),
      action: z.enum(["block", "flag", "redact"]),
    })
  ),
});
export type Request = z.infer<typeof RequestSchema>;

// ---------------------------------------------------------------------------
// AuditEvent
// ---------------------------------------------------------------------------

const ActorHumanSchema = z.object({
  email: z.string().email(),
  role: z.string(),
});
const ActorSystemSchema = z.object({
  system: z.string(),
});

export const AuditEventSchema = z.object({
  id: IDSchema,
  ts: ISODateSchema,
  actor: z.union([ActorHumanSchema, ActorSystemSchema]),
  action: z.string(), // "policy.update", "key.create", ...
  resource: z.string(), // "policy/research-eu/budget"
  outcome: z.enum(["success", "blocked", "redacted", "pending", "drift"]),
  traceId: IDSchema,
  diffUrl: z.string().url().optional(),
});
export type AuditEvent = z.infer<typeof AuditEventSchema>;

// ---------------------------------------------------------------------------
// Alert & AlertRule
// ---------------------------------------------------------------------------

export const AlertSchema = z.object({
  id: IDSchema,
  severity: SeveritySchema,
  ruleId: IDSchema,
  ruleName: z.string(),
  triggeredAt: ISODateSchema,
  firstSeen: ISODateSchema,
  ownerTeamId: IDSchema.nullable(),
  status: z.enum(["firing", "acked", "resolved"]),
  ackBy: z.string().optional(),
  ackAt: ISODateSchema.optional(),
});
export type Alert = z.infer<typeof AlertSchema>;

export const AlertRuleSchema = z.object({
  id: IDSchema,
  name: z.string(),
  severity: SeveritySchema,
  metric: z.string(), // "budget.team.monthly", "latency.p95", "guardrail.pii.hits"
  comparator: z.enum([">", "<", ">=", "<="]),
  threshold: z.number(),
  window: z.string(), // "5m"
  scope: z.union([
    z.literal("org"),
    z.object({ teamIds: z.array(IDSchema) }),
  ]),
  channels: z.array(IDSchema),
  active: z.boolean(),
});
export type AlertRule = z.infer<typeof AlertRuleSchema>;

// ---------------------------------------------------------------------------
// Guardrail
// ---------------------------------------------------------------------------

export const GuardrailSchema = z.object({
  id: IDSchema,
  name: z.string(),
  description: z.string(),
  stage: z.enum(["input", "output"]),
  action: z.enum(["block", "flag", "redact", "rewrite", "truncate", "route"]),
  scope: z.object({
    include: z.union([z.literal("org"), z.array(IDSchema)]),
    exclude: z.array(IDSchema).optional(),
  }),
  config: z.record(z.string(), z.unknown()),
  order: z.number().int().nonnegative(),
  hits24h: z.number().int().nonnegative(),
  enabled: z.boolean(),
});
export type Guardrail = z.infer<typeof GuardrailSchema>;

// ---------------------------------------------------------------------------
// UI-only helper types (no Zod required — not API-bound primitives)
// ---------------------------------------------------------------------------

export type PagedResponse<T> = {
  data: T[];
  cursor: string | null;
  total: number;
};

export type ApiError = {
  message: string;
  code: string;
  status: number;
};

export type NavItem = {
  id: string;
  label: string;
  href: string;
  icon?: string;
};

export type NavGroup = {
  label: string;
  items: NavItem[];
};

export type Crumb = {
  label: string;
  href?: string;
};

// ---------------------------------------------------------------------------
// ApprovalRequest (API-bound; include Zod schema)
// ---------------------------------------------------------------------------

export const ApprovalRequestSchema = z.object({
  id: IDSchema,
  type: z.enum([
    "skill.publish",
    "mcp.scope",
    "plugin.install",
    "policy.promote",
  ]),
  subject: z.string(),
  requestedBy: z.string(),
  requestedAt: ISODateSchema,
  teamId: IDSchema,
  status: z.enum(["pending", "approved", "rejected"]),
  slaHours: z.number().nonnegative(), // hours since requestedAt
});
export type ApprovalRequest = z.infer<typeof ApprovalRequestSchema>;
