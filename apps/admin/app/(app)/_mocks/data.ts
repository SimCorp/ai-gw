// Mock seed data — values match prototype HTML files exactly

export const TEAMS_DATA = [
  { id: 'tm_platfo_1001', name: 'platform-research',    ownerEmail: 'mira.rasmussen@simcorp.com',  members: 24, keys: 18, req24h: '248,210', spendMtd: '$8,421.40', budgetPct: 84, cacheHit: 38, status: 'good' as const,  alert: 'budget' },
  { id: 'tm_agentP_2002', name: 'agent-platform',       ownerEmail: 'a.kowalski@simcorp.com',      members: 18, keys: 14, req24h: '192,884', spendMtd: '$6,485.55', budgetPct: 71, cacheHit: 42, status: 'good' as const },
  { id: 'tm_client_3003', name: 'client-services-ai',   ownerEmail: 'a.silva@simcorp.com',         members: 31, keys: 22, req24h: '168,440', spendMtd: '$4,962.20', budgetPct: 62, cacheHit: 34, status: 'good' as const },
  { id: 'tm_posttr_4004', name: 'post-trade-ops',       ownerEmail: 'k.haukur@simcorp.com',        members: 12, keys: 9,  req24h: '124,780', spendMtd: '$3,789.05', budgetPct: 48, cacheHit: 29, status: 'good' as const },
  { id: 'tm_risken_5005', name: 'risk-engineering',     ownerEmail: 'p.fontaine@simcorp.com',      members: 15, keys: 11, req24h: '108,302', spendMtd: '$3,114.20', budgetPct: 55, cacheHit: 31, status: 'good' as const },
  { id: 'tm_datapl_6006', name: 'data-platform',        ownerEmail: 'l.gunnarsson@simcorp.com',    members: 22, keys: 16, req24h: '96,114',  spendMtd: '$2,291.80', budgetPct: 91, cacheHit: 18, status: 'warn' as const,  alert: 'rate' },
  { id: 'tm_devexp_7007', name: 'developer-experience', ownerEmail: 'i.koivisto@simcorp.com',      members: 9,  keys: 7,  req24h: '72,408',  spendMtd: '$1,820.40', budgetPct: 38, cacheHit: 51, status: 'good' as const },
  { id: 'tm_design_8008', name: 'design-systems',       ownerEmail: 'r.engstrom@simcorp.com',      members: 6,  keys: 5,  req24h: '48,920',  spendMtd: '$1,186.20', budgetPct: 24, cacheHit: 44, status: 'good' as const },
  { id: 'tm_nordic_9009', name: 'nordic-research',      ownerEmail: 'k.haukur@simcorp.com',        members: 11, keys: 6,  req24h: '31,205',  spendMtd: '$842.10',   budgetPct: 18, cacheHit: 22, status: 'good' as const,  isNew: true },
  { id: 'tm_compl_1010',  name: 'compliance-automation',ownerEmail: 'h.berg@simcorp.com',          members: 8,  keys: 6,  req24h: '28,400',  spendMtd: '$719.85',   budgetPct: 31, cacheHit: 36, status: 'good' as const },
  { id: 'tm_mobil_1011',  name: 'mobile-apps',          ownerEmail: 't.osipova@simcorp.com',       members: 14, keys: 9,  req24h: '24,118',  spendMtd: '$612.30',   budgetPct: 27, cacheHit: 48, status: 'good' as const },
  { id: 'tm_sandb_1012',  name: 'sandbox-experiments',  ownerEmail: 'mira.rasmussen@simcorp.com',  members: 42, keys: 18, req24h: '18,410',  spendMtd: '$418.60',   budgetPct: 42, cacheHit: 9,  status: 'warn' as const,  alert: 'low_hit' },
  { id: 'tm_archi_1013',  name: 'archived-legacy-ai',   ownerEmail: '—',                           members: 0,  keys: 1,  req24h: '12',      spendMtd: '$0.18',     budgetPct: 0,  cacheHit: 0,  status: 'bad' as const,   alert: 'frozen' },
];

export const AGENT_PLATFORM_TEAM = {
  id: 'tm_agentP_2002',
  name: 'agent-platform',
  idLabel: 'tm_tradin_8421',
  owner: 'a.kowalski@simcorp.com',
  memberCount: 18,
  createdAt: 'Mar 4, 2026',
  spendMtd: '$6,485.55',
  budgetPct: 71,
  budgetCap: '$9,150',
  req24h: '192K',
  cacheHit: 42,
  p99: '41ms',
  errorRate: '0.18%',
  keys: [
    { name: 'prod-rag-service',  key: 'sk_live_••••••8a31f', scope: 'prod · models: claude-*, gemini-*',  createdBy: 'a.kowalski', lastUsed: '2 min ago',  calls7d: '38,210', expires: 'Aug 12, 2026', status: 'active' as const },
    { name: 'pr-review-bot',     key: 'sk_live_••••••f02b1', scope: 'prod · models: claude-sonnet-4.5',  createdBy: 'a.kowalski', lastUsed: '4 min ago',  calls7d: '21,408', expires: 'Aug 12, 2026', status: 'active' as const },
    { name: 'eval-runner',       key: 'sk_test_••••••c41d8', scope: 'dev · models: any',                 createdBy: 'm.weber',     lastUsed: '11 min ago', calls7d: '9,114',  expires: 'May 28, 2026', status: 'expiring' as const },
    { name: 'jupyter-notebook',  key: 'sk_test_••••••3a982', scope: 'dev · models: any · rate 30/min',   createdBy: 'p.fontaine',  lastUsed: '1 h ago',    calls7d: '4,288',  expires: 'Sep 1, 2026',  status: 'active' as const },
    { name: 'ci-tests',          key: 'sk_test_••••••b921a', scope: 'ci · models: claude-haiku-4.5 only',createdBy: 'i.koivisto', lastUsed: '3 h ago',    calls7d: '2,418',  expires: 'Jul 4, 2026',  status: 'active' as const },
    { name: 'legacy-classifier', key: 'sk_live_••••••0181c', scope: 'prod · DEPRECATED',                createdBy: 'j.larsen',    lastUsed: '14 d ago',   calls7d: '12',     expires: 'May 18, 2026', status: 'revoke_pending' as const },
  ],
  members: [
    { name: 'Anya Kowalski',    email: 'a.kowalski@simcorp.com',  initials: 'AK', color: '#083EA7', role: 'Owner',      joined: 'Mar 4, 2026',  lastActive: '2 min ago' },
    { name: 'Maja Weber',       email: 'm.weber@simcorp.com',     initials: 'MW', color: '#1D958E', role: 'Maintainer', joined: 'Mar 11, 2026', lastActive: '11 min ago' },
    { name: 'Paul Fontaine',    email: 'p.fontaine@simcorp.com',  initials: 'PF', color: '#4B17B6', role: 'Maintainer', joined: 'Mar 11, 2026', lastActive: '1 h ago' },
    { name: 'Iida Koivisto',    email: 'i.koivisto@simcorp.com',  initials: 'IK', color: '#FB9B2A', role: 'Member',     joined: 'Mar 22, 2026', lastActive: '3 h ago' },
    { name: 'Tatiana Osipova',  email: 't.osipova@simcorp.com',   initials: 'TO', color: '#9D2E7B', role: 'Member',     joined: 'Apr 2, 2026',  lastActive: '7 h ago' },
    { name: 'Hans Berg',        email: 'h.berg@simcorp.com',      initials: 'HB', color: '#0A7BD7', role: 'Member',     joined: 'Apr 14, 2026', lastActive: '1 d ago' },
  ],
};

export const POLICIES_DATA = [
  { name: 'Allowed models',               desc: 'sonnet-4.5, haiku-4.5 · vendor allowlist', domain: 'model',     scope: 'org',          owner: 'jbach',        version: 'v8',       hits7d: '14,208', status: 'active' as const },
  { name: 'Rate limits · per-key',        desc: '60 RPM dev · 600 RPM prod',                domain: 'rate',      scope: 'org',          owner: 'platform-eng', version: 'v3',       hits7d: '412',    status: 'active' as const },
  { name: 'Cache TTL · semantic',         desc: '24h default · research-eu 1h override',    domain: 'cache',     scope: 'org + 1 team', owner: 'platform-data',version: 'v2',       hits7d: '—',      status: 'active' as const },
  { name: 'Tool-scope grants',            desc: 'orders:write → compliance only · pr:write → dev-ex', domain: 'tool', scope: '2 teams',   owner: 'security',     version: 'v5',       hits7d: '68',     status: 'active' as const },
  { name: 'Retention · prompts',          desc: '30d · client-services-eu = 0d (immediate purge)', domain: 'retention', scope: 'org + 1 team', owner: 'legal',  version: 'v4',       hits7d: '—',      status: 'active' as const },
  { name: 'Region pinning · EU residency',desc: 'routes to eu-central deployments',         domain: 'routing',   scope: '2 teams',      owner: 'legal',        version: 'v2',       hits7d: '5,108',  status: 'active' as const },
  { name: 'Per-call token cap',           desc: '80k input · 8k output',                    domain: 'rate',      scope: 'org',          owner: 'finance-ops',  version: 'v1',       hits7d: '9',      status: 'active' as const },
  { name: 'External egress · vendor allowlist', desc: 'Anthropic, Bedrock-EU only',         domain: 'routing',   scope: 'org',          owner: 'security',     version: 'v6',       hits7d: '2',      status: 'active' as const },
  { name: 'Approver matrix · skill publish', desc: 'team lead + security for org-wide',     domain: 'workflow',  scope: 'org',          owner: 'jbach',        version: 'v3-draft', hits7d: '—',      status: 'draft' as const },
];

export const GUARDRAILS_DATA = [
  { order: '01', name: 'PII detector · names + accounts',    desc: 'Presidio + custom EU client-ID regex',           stage: 'input'  as const, action: 'block' as const,    scope: 'org · all',                        hits24h: 87 },
  { order: '02', name: 'Secrets scanner',                    desc: 'API keys, JWTs, .pem fragments',                  stage: 'input'  as const, action: 'block' as const,    scope: 'org · all',                        hits24h: 12 },
  { order: '03', name: 'Prompt-injection heuristics',        desc: 'classifier · threshold 0.78',                    stage: 'input'  as const, action: 'flag' as const,     scope: 'org · all',                        hits24h: 31 },
  { order: '04', name: 'Topic block · trading recs',         desc: 'advice flagged outside compliance team',          stage: 'input'  as const, action: 'block' as const,    scope: 'except: compliance',               hits24h: 4 },
  { order: '05', name: 'Output PII redactor',               desc: 'redact-with-tag · «[REDACTED]»',                  stage: 'output' as const, action: 'redact' as const,   scope: 'org · all',                        hits24h: 18 },
  { order: '06', name: 'Hallucinated-citation check',        desc: 'verifies URLs/docs cited exist in source',        stage: 'output' as const, action: 'flag' as const,     scope: 'research · client-services',       hits24h: 22 },
  { order: '07', name: 'Toxicity / harassment',              desc: 'multilingual · da, sv, en, de, fr',               stage: 'output' as const, action: 'block' as const,    scope: 'org · all',                        hits24h: 2 },
  { order: '08', name: 'Confidence floor on numbers',        desc: 'strip / qualify low-confidence figures',          stage: 'output' as const, action: 'rewrite' as const,  scope: 'research',                         hits24h: 28 },
  { order: '09', name: 'Token-budget cap · per call',        desc: 'truncate prompts > 80k tokens',                   stage: 'input'  as const, action: 'truncate' as const, scope: 'org · all',                        hits24h: 9 },
  { order: '10', name: 'Geo-fenced model · EU residency',    desc: 'routes to eu-central deployments only',           stage: 'input'  as const, action: 'route' as const,    scope: 'research-eu · client-services-eu', hits24h: 5 },
];

export const QUOTAS_DATA = [
  { name: 'research-eu',          members: 17, cap: '$12,750', mtd: '$10,200', projected: '$13,420', pct: 80,  pctLabel: '80% of cap',  warn: true,  rpm: '42', tpm: '18k' },
  { name: 'platform-engineering', members: 28, cap: '$8,500',  mtd: '$3,180',  projected: '$5,820',  pct: 37,  pctLabel: '37% of cap',  warn: false, rpm: '88', tpm: '24k' },
  { name: 'trading',              members: 12, cap: '$6,000',  mtd: '$2,490',  projected: '$4,210',  pct: 42,  pctLabel: '42% of cap',  warn: false, rpm: '28', tpm: '12k' },
  { name: 'client-services-ai',   members: 22, cap: '$5,500',  mtd: '$1,820',  projected: '$3,140',  pct: 33,  pctLabel: '33% of cap',  warn: false, rpm: '38', tpm: '14k' },
  { name: 'developer-experience', members: 9,  cap: '$4,200',  mtd: '$1,210',  projected: '$2,090',  pct: 29,  pctLabel: '29% of cap',  warn: false, rpm: '19', tpm: '8k' },
  { name: 'compliance-automation',members: 6,  cap: '$2,500',  mtd: '$420',    projected: '$720',    pct: 17,  pctLabel: '17% of cap',  warn: false, rpm: '12', tpm: '4k' },
  { name: 'risk-engineering',     members: 8,  cap: '$2,500',  mtd: '$480',    projected: '$830',    pct: 19,  pctLabel: '19% of cap',  warn: false, rpm: '14', tpm: '5k' },
];

export const APPROVALS_DATA = [
  { type: 'tool scope',    typePill: 'bad'  as const, subject: 'Grant orders:write to trade-mcp',      desc: 'justification: pre-trade ticket validator agent (rc.2)',   requester: 'g.olsen@simcorp',   team: 'trading',             age: '2h 18m',  sla: false, risk: 'high' as const },
  { type: 'skill publish', typePill: 'warn' as const, subject: 'Anomaly explainer · v2.0',              desc: 'adds Datadog tool · diff +118 / -42',                     requester: 'k.weiss@simcorp',   team: 'risk-engineering',    age: '5h 04m',  sla: false, risk: 'med'  as const },
  { type: 'budget raise',  typePill: 'warn' as const, subject: 'research-eu · +$3,500 May cap',         desc: 'projected overrun $13.4k vs $12.75k cap',                 requester: 'r.holm@simcorp',    team: 'research-eu',         age: '7h 41m',  sla: true,  risk: 'med'  as const },
  { type: 'plugin install',typePill: 'default' as const, subject: 'Slack notifier · per-team',          desc: 'scope: agent + budget alerts → #ai-gw-trading',           requester: 'g.olsen@simcorp',   team: 'trading',             age: '12h 02m', sla: true,  risk: 'low'  as const },
  { type: 'model deploy',  typePill: 'default' as const, subject: 'sonnet-4.5 · eu-west deployment',    desc: 'capacity addition · +200 RPM',                            requester: 'n.persson@simcorp', team: 'platform-engineering',age: '14h 21m', sla: true,  risk: 'low'  as const },
  { type: 'mcp register',  typePill: 'warn' as const, subject: 'trade-mcp · v1.0-rc.2',                desc: 'scopes: orders:read, orders:write',                        requester: 'g.olsen@simcorp',   team: 'trading',             age: '1d 03h',  sla: false, risk: 'med'  as const },
  { type: 'key issue',     typePill: 'default' as const, subject: 'Production key · client-services-eu',desc: 'rate 600 RPM · region eu-central only',                  requester: 'm.larsen@simcorp',  team: 'client-services-ai',  age: '1d 14h',  sla: false, risk: 'low'  as const },
  { type: 'team add',      typePill: 'default' as const, subject: 'New team · nordic-research-quant',   desc: '5 members · region eu-central · cap $4,000/mo',           requester: 'a.singh@simcorp',   team: '(new)',               age: '2d 08h',  sla: false, risk: 'low'  as const },
];

export const MODELS_DATA = [
  { name: 'claude-sonnet-4.5',          provider: 'Anthropic',        tier: 'prod'    as const, caps: ['chat','tools','vision'],        ctx: '200K', cin: '$3.00',  cout: '$15.00', fb: 'gemini-2.5-pro',     usage: 1240, usageMax: 1240, status: 'good' as const },
  { name: 'claude-haiku-4.5',           provider: 'Anthropic',        tier: 'prod'    as const, caps: ['chat','tools'],                 ctx: '200K', cin: '$0.80',  cout: '$4.00',  fb: '—',                  usage: 740,  usageMax: 1240, status: 'good' as const },
  { name: 'claude-opus-4.5',            provider: 'Anthropic',        tier: 'prod'    as const, caps: ['chat','tools','vision'],        ctx: '200K', cin: '$15.00', cout: '$75.00', fb: 'claude-sonnet-4.5',  usage: 88,   usageMax: 1240, status: 'good' as const },
  { name: 'gemini-2.5-pro',             provider: 'Google',           tier: 'prod'    as const, caps: ['chat','tools','vision','audio'],ctx: '2M',   cin: '$1.25',  cout: '$5.00',  fb: 'claude-sonnet-4.5',  usage: 920,  usageMax: 1240, status: 'good' as const },
  { name: 'gemini-2.5-flash',           provider: 'Google',           tier: 'prod'    as const, caps: ['chat','tools','vision'],        ctx: '1M',   cin: '$0.30',  cout: '$1.20',  fb: '—',                  usage: 480,  usageMax: 1240, status: 'good' as const },
  { name: 'gpt-5',                      provider: 'Azure OpenAI',     tier: 'prod'    as const, caps: ['chat','tools','vision'],        ctx: '400K', cin: '$5.00',  cout: '$20.00', fb: 'claude-sonnet-4.5',  usage: 210,  usageMax: 1240, status: 'bad'  as const, note: 'errors' },
  { name: 'gpt-5-mini',                 provider: 'Azure OpenAI',     tier: 'prod'    as const, caps: ['chat','tools'],                 ctx: '400K', cin: '$0.30',  cout: '$1.20',  fb: '—',                  usage: 140,  usageMax: 1240, status: 'good' as const },
  { name: 'github-models/copilot-x',    provider: 'GitHub',           tier: 'preview' as const, caps: ['chat','tools'],                ctx: '128K', cin: '$2.00',  cout: '$8.00',  fb: 'claude-sonnet-4.5',  usage: 64,   usageMax: 1240, status: 'warn' as const, note: 'degraded' },
  { name: 'text-embedding-3-small',     provider: 'OpenAI',           tier: 'embed'   as const, caps: ['embed'],                       ctx: '8K',   cin: '$0.02',  cout: '—',      fb: '—',                  usage: 1820, usageMax: 1820, status: 'good' as const },
  { name: 'text-embedding-3-large',     provider: 'OpenAI',           tier: 'embed'   as const, caps: ['embed'],                       ctx: '8K',   cin: '$0.13',  cout: '—',      fb: '—',                  usage: 110,  usageMax: 1820, status: 'good' as const },
  { name: 'ollama/llama-3.1-70b',       provider: 'BYO · ollama-eu-1',tier: 'dev'     as const, caps: ['chat','tools'],                ctx: '128K', cin: '—',      cout: '—',      fb: '—',                  usage: 38,   usageMax: 1240, status: 'good' as const },
  { name: 'ollama/qwen-2.5-coder-32b',  provider: 'BYO · ollama-eu-1',tier: 'dev'     as const, caps: ['chat','code'],                 ctx: '128K', cin: '—',      cout: '—',      fb: '—',                  usage: 22,   usageMax: 1240, status: 'good' as const },
];

export const MCP_DATA = [
  { name: 'portfolio-mcp',   version: 'v2.4.1',      transport: 'stdio',    owner: 'platform-data',       source: 'internal' as const, tools: 9,  scopes: ['positions:read','weights:read'],  calls24h: '4,218', p50: '74 ms',  err: '0.02%', status: 'good' as const,    btn: 'Inspect' },
  { name: 'market-data-mcp', version: 'v1.9.0',      transport: 'http+sse', owner: 'trading',             source: 'internal' as const, tools: 14, scopes: ['quotes:read','refdata:read'],    calls24h: '3,841', p50: '48 ms',  err: '0.01%', status: 'good' as const,    btn: 'Inspect' },
  { name: 'filings-mcp',     version: 'v0.8.3',      transport: 'http',     owner: 'research',            source: 'internal' as const, tools: 6,  scopes: ['filings:read'],                  calls24h: '1,108', p50: '312 ms', err: '2.1%',  status: 'warn' as const,    btn: 'Inspect' },
  { name: 'github-mcp',      version: 'v0.6.0',      transport: 'stdio',    owner: 'platform-engineering',source: 'vendored' as const, tools: 11, scopes: ['repo:read','pr:write'],           calls24h: '1,684', p50: '128 ms', err: '0.04%', status: 'good' as const,    btn: 'Inspect' },
  { name: 'confluence-mcp',  version: 'v0.3.1',      transport: 'http',     owner: '(third-party)',       source: 'vendored' as const, tools: 5,  scopes: ['space:read'],                    calls24h: '0',     p50: '—',      err: '91%',   status: 'bad' as const,     btn: 'Reconnect' },
  { name: 'trade-mcp',       version: 'v1.0.0-rc.2', transport: 'stdio',    owner: 'trading',             source: 'internal' as const, tools: 4,  scopes: ['orders:write','orders:read'],    calls24h: '—',     p50: '—',      err: '—',     status: 'pending' as const, btn: 'Review' },
];

export const SKILLS_DATA = [
  { name: 'Portfolio analyst',    desc: 'portfolio rebalance + drift narrative',         owner: 'platform-research',    version: 'v3.2',      model: 'sonnet-4.5', tools: 4, uses7d: '418', visibility: 'org'   as const, status: 'published' as const },
  { name: 'PR reviewer · Python', desc: 'enforces SimCorp Python style guide',           owner: 'developer-experience', version: 'v5.1',      model: 'sonnet-4.5', tools: 3, uses7d: '284', visibility: 'org'   as const, status: 'published' as const },
  { name: 'Filing summarizer',    desc: '10-K, 10-Q, EU prospectus → 6-bullet brief',   owner: 'nordic-research',      version: 'v2.0',      model: 'haiku-4.5',  tools: 2, uses7d: '192', visibility: 'org'   as const, status: 'published' as const },
  { name: 'Trade ticket validator',desc: 'pre-submit checks against compliance rules',   owner: 'compliance-automation',version: 'v1.0',      model: 'sonnet-4.5', tools: 3, uses7d: '88',  visibility: 'team'  as const, status: 'frozen'    as const },
  { name: 'SQL → narrative',      desc: 'turns query result into 2-paragraph summary',  owner: 'data-platform',        version: 'v2.7',      model: 'haiku-4.5',  tools: 1, uses7d: '318', visibility: 'org'   as const, status: 'published' as const },
  { name: 'Anomaly explainer',    desc: 'v2.0-draft — adds Datadog tool',               owner: 'risk-engineering',     version: 'v2.0-draft', model: 'sonnet-4.5', tools: 5, uses7d: '—',  visibility: 'draft' as const, status: 'review'    as const },
  { name: 'Email drafter · client',desc: 'pulls thread for tone match — flagged: PII risk', owner: 'client-services-ai',version: 'v1.2',   model: 'sonnet-4.5', tools: 2, uses7d: '142', visibility: 'team'  as const, status: 'blocked'   as const },
];

export const PLUGINS_DATA = [
  { name: 'Datadog tracing',        desc: 'OTel spans — gateway / model / tool',           category: 'Observability', source: 'first-party' as const, scope: 'required' as const,  teamsUsing: '42 / 42',  policyGate: 'none',          status: 'enabled'     as const },
  { name: 'Guardrails · PII',       desc: 'redact / block per policy',                     category: 'Safety',        source: 'first-party' as const, scope: 'required' as const,  teamsUsing: '42 / 42',  policyGate: 'always-on',     status: 'enabled'     as const },
  { name: 'Semantic cache',         desc: 'embedding-backed dedupe',                       category: 'Routing',       source: 'first-party' as const, scope: 'opt-in'   as const,  teamsUsing: '31 / 42',  policyGate: 'none',          status: 'enabled'     as const },
  { name: 'VS Code · Inline complete',desc: 'routes Copilot-style completions',            category: 'Editor',        source: 'first-party' as const, scope: 'per-user' as const,  teamsUsing: '348 users', policyGate: 'cost-cap',     status: 'enabled'     as const },
  { name: 'Eval harness · Inspect', desc: 'scheduled regression evals',                   category: 'Eval',          source: 'first-party' as const, scope: 'opt-in'   as const,  teamsUsing: '8 / 42',   policyGate: 'none',          status: 'enabled'     as const },
  { name: 'Smart router',           desc: 'complexity-classifier model picker',            category: 'Routing',       source: 'first-party' as const, scope: 'opt-in'   as const,  teamsUsing: '6 / 42',   policyGate: 'cost-cap',      status: 'enabled'     as const },
  { name: 'Slack notifier',         desc: 'community/oren — agent + budget alerts',        category: 'Observability', source: 'community'   as const, scope: 'opt-in'   as const,  teamsUsing: '14 / 42',  policyGate: 'review · 30d',  status: 'conditional' as const },
  { name: 'External LLM router',    desc: 'community/x — routes to non-vendor APIs',       category: 'Routing',       source: 'community'   as const, scope: '—'        as const,  teamsUsing: '0 / 42',   policyGate: 'blocked',       status: 'blocked'     as const },
];

export const CACHE_STATS = {
  hitRate: '31.4%',
  tokensSaved: '187M',
  saved: '$1,209',
  memory: '14.2/32 GB',
  vectorIndex: '2.41M',
  opsP99: '4,810',
};

export const CACHE_POLICY = {
  status: 'Enabled (org-wide)',
  ttl: '12 hours',
  threshold: '0.92',
  embeddingModel: 'text-embedding-3-small',
  embeddingCache: '24 hours · separate Redis prefix',
  streamCaching: 'Assemble before store · streaming passthrough unaffected',
  onFailure: 'Fail open (request proceeds, miss recorded)',
};

export const CACHE_TEAM_OVERRIDES = [
  { team: 'agent-platform',        threshold: '0.94', ttl: '24h', hit: '42%', note: 'stricter' as const },
  { team: 'platform-research',     threshold: '0.90', ttl: '6h',  hit: '38%', note: 'looser'   as const },
  { team: 'client-services-ai',    threshold: '0.92', ttl: '48h', hit: '34%', note: 'long-ttl' as const },
  { team: 'compliance-automation', threshold: '—',    ttl: '—',   hit: '—',   note: 'opted-out' as const },
  { team: 'sandbox-experiments',   threshold: '0.96', ttl: '1h',  hit: '9%',  note: 'low value' as const },
];

export const CACHE_TOP_PROMPTS = [
  { fingerprint: '"You are a trading research assistant…" + Q1 EM debt summary', team: 'agent-platform',      model: 'claude-sonnet-4.5', hits: '218', avgSim: '0.961', tokensSaved: '1.2M', lastHit: '2 min ago' },
  { fingerprint: 'SDK changelog summarisation prompt template',                   team: 'developer-experience', model: 'claude-haiku-4.5',  hits: '184', avgSim: '0.948', tokensSaved: '412K', lastHit: '4 min ago' },
  { fingerprint: 'Support ticket classifier · v2.1',                              team: 'client-services-ai',   model: 'gemini-2.5-pro',    hits: '142', avgSim: '0.931', tokensSaved: '820K', lastHit: '6 min ago' },
  { fingerprint: 'Code review prompt · python style guide',                       team: 'platform-research',    model: 'claude-sonnet-4.5', hits: '98',  avgSim: '0.918', tokensSaved: '512K', lastHit: '11 min ago' },
  { fingerprint: 'Incident postmortem draft · weekly',                            team: 'risk-engineering',     model: 'claude-sonnet-4.5', hits: '62',  avgSim: '0.974', tokensSaved: '388K', lastHit: '28 min ago' },
];

export const PROVIDERS_DATA = [
  { abbr: 'A',  name: 'Anthropic',         desc: 'Claude family · native LiteLLM adapter',             color: '#D97757', status: 'good' as const, endpoint: 'api.anthropic.com',            region: 'us-east-1',         p99: '28ms',    success: '99.94%', models: '3 active', spend: '$48,210', authLabel: 'Key',            authValue: 'kv://anthropic/prod-2026-q2',     rotated: 'rotated 14 d ago' },
  { abbr: 'G',  name: 'Google Gemini',     desc: 'Vertex AI · OAuth service-account auth',             color: '#4285F4', status: 'good' as const, endpoint: 'europe-north1-aiplatform',     region: 'europe-north1',     p99: '41ms',    success: '99.88%', models: '2 active', spend: '$22,480', authLabel: 'Service account', authValue: 'aigw-vertex@simcorp-ai.iam',     rotated: 'rotated 6 d ago' },
  { abbr: 'GH', name: 'GitHub Models',     desc: 'via Copilot Enterprise · preview',                   color: '#1A1A1A', status: 'warn' as const, endpoint: 'models.github.ai',             region: 'us-east-1',         p99: '187ms',   success: '98.21%', models: '1 active', spend: '$1,840',  authLabel: 'Token',          authValue: 'kv://github/copilot-ent',        rotated: 'rotated 31 d ago · due' },
  { abbr: 'Az', name: 'Azure OpenAI · BYO',desc: 'Internal deployment · simcorp-ai-east subscription', color: '#0078D4', status: 'bad' as const,  endpoint: 'simcorp-ai-east.openai.azure.com', region: 'eastus2',       p99: 'timing out', success: '91.84%', models: '2 active', spend: '$11,028', failover: true, failoverMsg: 'Failover engaged', failoverTo: '→ Anthropic since 13:44' },
  { abbr: 'Ol', name: 'Ollama (eu-1)',      desc: 'Self-hosted · 4× A100 · llama.cpp',                  color: '#1D958E', status: 'good' as const, endpoint: 'ollama-eu-1.svc:11434',        region: 'eu-north-1 (internal)', p99: '12ms', success: '99.99%', models: '2 active', spend: '$0 (BYO)', authLabel: 'Auth',           authValue: 'mTLS · cluster-internal',         rotated: 'scope: dev only' },
  { abbr: 'Oa', name: 'OpenAI',            desc: 'Embeddings only · cache engine bypasses recursion',  color: '#10A37F', status: 'good' as const, endpoint: 'api.openai.com',               region: 'global',            p99: '22ms',    success: '99.97%', models: '2 (embed)', spend: '$3,862', authLabel: 'Key',            authValue: 'kv://openai/embeddings-only',    rotated: 'rotated 9 d ago' },
];

export const ALERTS_DATA = [
  { severity: 'P1' as const, ruleName: 'filings-mcp · err-rate > 2%',           desc: 'current 91% · auth credentials rotated upstream', triggered: '14:32 UTC', owner: 'platform-data',       status: 'firing'          as const, btn: 'Ack' },
  { severity: 'P1' as const, ruleName: 'trade-mcp · drift on validator',         desc: 'eval pass-rate dropped 92% → 78% on v1.0-rc.2',   triggered: '13:08 UTC', owner: 'compliance-automation',status: 'firing'          as const, btn: 'Ack' },
  { severity: 'P2' as const, ruleName: 'research-eu · 80% of monthly budget',    desc: '$10,200 / $12,750 — projected $13.4k',             triggered: '11:55 UTC', owner: 'finance-ops',         status: 'acked'           as const, ackedBy: 'ANV', btn: 'View' },
  { severity: 'P2' as const, ruleName: 'PII guardrail · 12 hits / hour',         desc: 'team: client-services-ai · skill: email-drafter v1.2', triggered: '10:12 UTC', owner: 'security',        status: 'acked'           as const, ackedBy: 'MOC', btn: 'View' },
  { severity: 'P3' as const, ruleName: 'P95 latency · sonnet-4.5',               desc: '12 min spike — recovered',                         triggered: '06:48 UTC', owner: 'platform-engineering', status: 'acked_resolved'  as const, ackedBy: 'resolved', btn: 'View' },
];

export const ALERT_RULES = [
  { name: 'Budget · team monthly > 80%',      scope: '7 teams',   severity: 'P2' },
  { name: 'Budget · org daily > $1,200',       scope: 'org',       severity: 'P1' },
  { name: 'Latency · model P95 > 4s · 5m',    scope: 'all models',severity: 'P3' },
  { name: 'Error-rate · MCP > 2% · 5m',       scope: '14 servers',severity: 'P1' },
  { name: 'Drift · eval pass-rate Δ > 10%',   scope: '38 evals',  severity: 'P1' },
  { name: 'Guardrail · PII hits > 5/h',       scope: 'org',       severity: 'P2' },
  { name: 'Policy · denied tool-call > 10/h', scope: 'org',       severity: 'P2' },
  { name: 'Cache · hit-rate < 30% · 1h',      scope: 'opt-in',    severity: 'P3' },
];

export const ALERT_CHANNELS = [
  { name: '#ai-gw-incidents',          type: 'Slack · P1, P2' },
  { name: '#ai-gw-budget',             type: 'Slack · budget rules' },
  { name: 'PagerDuty · gateway-oncall',type: 'P1 only' },
  { name: 'security@simcorp.com',      type: 'guardrail violations' },
];

export const AUDIT_DATA = [
  { ts: '14:42:11', actor: 'jbach@simcorp',            role: 'Admin · platform',            action: 'policy.update',     resource: 'policy/research-eu/budget',    outcome: 'success'       as const, trace: 'a91f…3c', btn: 'Diff' },
  { ts: '14:38:02', actor: 'guardrail.system',          role: 'internal',                    action: 'request.blocked',   resource: 'guardrail/pii-detector',       outcome: 'blocked'       as const, trace: '1f04…b2', btn: 'Open' },
  { ts: '14:31:48', actor: 'm.larsen@simcorp',          role: 'Engineer · client-services',  action: 'key.create',        resource: 'key/dev/sk_live_…42',          outcome: 'success'       as const, trace: '7e21…aa', btn: 'Open' },
  { ts: '14:27:33', actor: 'guardrail.system',          role: 'internal',                    action: 'output.redacted',   resource: 'guardrail/output-pii-redactor',outcome: 'redacted'      as const, trace: '2c87…41', btn: 'Open' },
  { ts: '14:18:09', actor: 'a.singh@simcorp',           role: 'PM · research',               action: 'request.blocked',   resource: 'guardrail/topic-trading-recs', outcome: 'blocked'       as const, trace: '5b03…7c', btn: 'Open' },
  { ts: '14:09:12', actor: 'r.holm@simcorp',            role: 'Analyst · research-eu',       action: 'skill.invoke',      resource: 'skill/filing-summarizer@v2.0', outcome: 'success'       as const, trace: '0d12…aa', btn: 'Open' },
  { ts: '13:58:44', actor: 'jbach@simcorp',             role: 'Admin · platform',            action: 'team.member.add',   resource: 'team/risk-engineering',        outcome: 'success'       as const, trace: '8b34…01', btn: 'Diff' },
  { ts: '13:42:18', actor: 'g.olsen@simcorp',           role: 'Engineer · trading',          action: 'tool.scope.request',resource: 'tool/orders.write',            outcome: 'pending'       as const, trace: '3d77…12', btn: 'Review' },
  { ts: '13:08:45', actor: 'eval.scheduler',            role: 'internal',                    action: 'eval.regress',      resource: 'eval/trade-validator-v1',      outcome: 'drift'         as const, trace: 'b915…4d', btn: 'Open' },
  { ts: '12:51:02', actor: 'n.persson@simcorp',         role: 'Lead · platform-engineering', action: 'model.deploy',      resource: 'model/sonnet-4.5/eu-central',  outcome: 'success'       as const, trace: 'e224…77', btn: 'Diff' },
  { ts: '12:33:18', actor: 'jbach@simcorp',             role: 'Admin · platform',            action: 'plugin.block',      resource: 'plugin/external-llm-router',   outcome: 'blocked'       as const, trace: 'cc12…99', btn: 'Diff' },
  { ts: '11:55:02', actor: 'budget.system',             role: 'internal',                    action: 'budget.threshold',  resource: 'team/research-eu',             outcome: 'pending'       as const, trace: 'd501…3a', btn: 'Open' },
];

// Deterministic RNG for request generation (same seed as prototype)
function makeRng(seed: number) {
  let s = seed;
  return () => { s = (s * 1103515245 + 12345) & 0x7fffffff; return s / 0x7fffffff; };
}

const TEAMS_LIST = ['agent-platform','platform-research','client-services-ai','post-trade-ops','risk-engineering','data-platform','developer-experience','design-systems'];
const MODEL_LIST = [
  ['claude-sonnet-4.5','Anthropic',1.0],
  ['claude-haiku-4.5','Anthropic',0.18],
  ['gemini-2.5-pro','Google',0.7],
  ['gpt-5','Azure OpenAI',1.4],
  ['ollama/llama-3.1-70b','BYO',0],
  ['text-embedding-3-small','OpenAI',0.02],
] as [string,string,number][];
const KEYS_LIST = ['sk_live_••••8a31f','sk_live_••••f02b1','sk_test_••••c41d8','sk_test_••••3a982','sk_test_••••b921a','sk_live_••••0181c'];

function pad(n: number) { return n < 10 ? '0'+n : ''+n; }
function ago(s: number) {
  const d = new Date(Date.now() - s * 1000);
  return `${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`;
}

export type RequestRow = {
  t: string; status: number; model: string; provider: string; team: string;
  key: string; cache: 'exact'|'semantic'|'miss'; similarity: number|null;
  tokIn: number; tokOut: number; latency: number; cost: number; streaming: boolean; reqId: string;
};

export function generateRequests(): RequestRow[] {
  const rng = makeRng(1234567);
  const pick = <T>(a: T[]): T => a[Math.floor(rng() * a.length)];
  const rows: RequestRow[] = [];
  let elapsed = 0;
  for (let i = 0; i < 28; i++) {
    elapsed += 1 + Math.floor(rng() * 8);
    const [model, provider, costMul] = pick(MODEL_LIST);
    const isCacheHit = rng() < 0.34;
    const isExact = isCacheHit && rng() < 0.4;
    const isError = !isCacheHit && rng() < 0.04;
    const status = isError ? (rng() < 0.5 ? 429 : (rng() < 0.5 ? 502 : 401)) : 200;
    const tokIn = isCacheHit ? Math.floor(200 + rng() * 1200) : Math.floor(400 + rng() * 4500);
    const tokOut = isError ? 0 : Math.floor(80 + rng() * 1800);
    const latency = isCacheHit ? Math.floor(20 + rng() * 60) : status === 429 ? Math.floor(8 + rng() * 20) : Math.floor(280 + rng() * 4200);
    const cost = (isCacheHit || status !== 200) ? 0 : ((tokIn * 0.000003 + tokOut * 0.000015) * costMul);
    rows.push({
      t: ago(elapsed), status, model, provider,
      team: pick(TEAMS_LIST), key: pick(KEYS_LIST),
      cache: isCacheHit ? (isExact ? 'exact' : 'semantic') : 'miss',
      similarity: isCacheHit && !isExact ? (0.92 + rng() * 0.07) : null,
      tokIn, tokOut, latency, cost,
      streaming: !isCacheHit && status === 200 && rng() < 0.5,
      reqId: `req_${Math.abs(Math.floor(rng() * 1e12)).toString(36).slice(0, 10)}`,
    });
  }
  return rows;
}
