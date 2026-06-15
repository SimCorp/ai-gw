# AI Gateway Research Synthesis: Agentic Cache, Gamification, and Market Landscape

> **Generated:** 2026-06-12  
> **Method:** 112-agent deep research harness — 6 search angles, 29 sources fetched, 140 claims extracted, 25 adversarially verified (3-vote); 4 confirmed, 21 killed  
> **Prior art:** Builds on [2026-06-11 codebase audit](../superpowers/specs/) — read that first for internal architecture details  
> **Confidence note:** All quantitative specifics (hit rates, latency breakdowns, improvement multipliers, β coefficients) failed adversarial verification and are excluded. Directional findings are robust; numbers require production measurement against ai-gw traffic.

---

## Executive Summary

The ai-gw codebase has **three critical gaps** against the 2024-2025 state of the art:

1. **Cache architecture**: The O(N) `redis.keys()` semantic scan must be replaced with HNSW-indexed vector search. The hardcoded **0.95 cosine threshold is stricter than any threshold tested in published research** — valid cache hits are systematically missed. An async LLM-judge tier for near-threshold candidates is the current state-of-the-art for expanding coverage without adding critical-path latency.

2. **Gamification design**: The AI League's 7-dimensional scoring is architecturally sound, but **SDT research confirms competence feedback only sustains intrinsic motivation when autonomy is also perceived**. Fixed mandatory scoring dimensions undermine engagement even when they accurately measure skill. Opt-in framing and player-adjustable weights are the highest-leverage design changes.

3. **Gateway market position**: The market has converged on table-stakes features where ai-gw is already competitive (provider routing, rate limiting, auth, basic caching, observability). Differentiators at 2000-engineer scale are **distributed tracing, cost anomaly alerting, and agentic workflow primitives** — gaps the existing roadmap already identifies.

---

## Topic 1: Semantic / Agentic Caching

### 1.1 The O(N) Scan Problem

The cache service performs `redis.keys("sem:{team}:{project}:*:emb")` — a full Redis keyspace scan — for every semantic cache lookup. This is well understood internally as the highest-priority cache debt (§8.1 of the codebase audit). The research confirms this is not a performance edge case: it is architecturally wrong for any scale beyond a handful of teams.

**Correct replacement** (medium confidence — architectural inference, no primary source needed):

The memory service already demonstrates the right approach: **pgvector HNSW** with the `<=>` cosine distance operator and an index. Using pgvector for the semantic cache is the **lowest-friction path** because:
- PostgreSQL Flexible Server already runs in the deployment
- No new managed dependency (vs. Redis Stack RediSearch, which requires upgrading the Redis tier or adding a new service)
- Consistent with the existing memory service pattern
- HNSW reduces per-query search from O(N) scan to O(log N) ANN

Redis Stack RediSearch (`FT.CREATE` with HNSW vector index + `FT.SEARCH ... KNN`) is a viable alternative and keeps cache logic in Redis, but requires either a Redis Stack subscription or migrating to a compatible tier.

The open question (see §4) is whether adding vector workload to the primary DB server is acceptable given it currently runs on a `Standard_B2ms` Burstable SKU with HA disabled.

### 1.2 The 0.95 Threshold Problem

**Finding (3-0 adversarially confirmed):** The hardcoded 0.95 cosine threshold is **stricter than any threshold empirically tested in published semantic caching research**.

- arXiv 2603.03301 tested L2 thresholds of 0.5, 0.7, 0.9 — corresponding to cosine similarities of ~0.88, ~0.75, and ~0.60 respectively
- A 0.95 cosine threshold maps to L2 ≈ 0.316, strictly smaller (stricter) than the paper's tightest tested value
- Production AI gateway vendors (Portkey, Kong AI) use 0.90–0.97, with 0.95 reserved for highly conservative deployments where false positive cost is extreme — **not as a default**

The practical implication: the cache is systematically refusing to serve responses for queries that are semantically identical by any reasonable definition. The 0.95 threshold is functioning as "almost identical character-for-character" rather than "same intent."

**Threshold recommendation** (directional only — calibrate against production traffic):
- Start at 0.88–0.90 for general queries
- Consider per-team or per-category overrides (policy.similarity_threshold already exists in the data model)
- Instrument cache near-miss rate (similarity 0.85–0.95) to measure the opportunity

### 1.3 Adaptive Thresholds (State of the Art)

**Finding (3-0 confirmed):** Static single-valued similarity thresholds are **fundamentally suboptimal** for production semantic caching. This is not a tuning problem — different query categories, domains, and embedding density regimes require different thresholds. The correct and incorrect hit distributions overlap in embedding space in category-specific ways.

Sources: arXiv 2602.13165 (Krites, Apple ML Research, ACM EuroMLSys 2026) + arXiv 2603.03301

The right direction: per-category or per-region adaptive thresholds. The ai-gw policy model already supports per-team overrides (`similarity_threshold` in the policy hash). This can be extended to:
- Per-model-type thresholds (code queries may need stricter thresholds than conversational queries)
- Learned thresholds based on team-specific cache performance feedback

### 1.4 Async LLM-Judge for Near-Threshold Candidates (State of the Art)

**Finding (3-0 confirmed):** Async LLM-judge verification for near-threshold semantic cache candidates is the **current state-of-the-art** approach to expanding cache coverage without changing critical-path latency.

Architecture (from arXiv 2602.13165, Krites):
1. Serving path: identical to static threshold — fast, low latency
2. When similarity falls just below threshold (e.g. 0.82–0.95 "grey zone"): queue prompt pair for async evaluation
3. Offline LLM judge evaluates whether the pair is safe to cache
4. Approved pairs are promoted to the static cache, serving future requests

Key property: **the triggering request is not affected** — no added latency. Only future requests benefit from the promotion. Caveat: false approvals from the judge can corrupt promoted entries, so judge accuracy matters for cache correctness.

Implementation fit for ai-gw: the cache service already has `asyncio.create_task` for the observability emit path. The same pattern can drive async judge evaluation. The LiteLLM proxy (internal, cheap) can serve as the judge model.

**Specific quantitative claims about improvement magnitude (3.9x, 99% accuracy) were refuted 0-3 and are excluded.** Adopt the architecture; measure actual improvement against production traffic.

### 1.5 Agentic Cache Specifics

One paper (arXiv 2602.18922) explored caching for agentic (tool-calling) workloads, arguing that semantically similar queries can require completely different tool sequences, making embedding-similarity caching unreliable for tool call prediction. The specific numerical claims from this paper were refuted 0-3, but the qualitative concern is architecturally sound: **the cache's bypass logic (§7.6 in the codebase audit) already handles this partially** via the conversation turn limit and PII pattern detection. For tool-calling cache correctness, the response stored in cache should include the tool calls themselves, not just the text — this is worth verifying in the cache write path.

### 1.6 Summary: Cache Upgrade Priority

| Priority | Change | Confidence | Effort |
|---|---|---|---|
| P0 | Replace O(N) `redis.keys()` with HNSW vector index (pgvector or Redis Stack) | High | Medium |
| P1 | Lower default cosine threshold from 0.95 to ~0.88–0.90 | High | Low |
| P2 | Instrument near-miss rate (similarity 0.85–threshold) | High | Low |
| P3 | Add async LLM-judge promotion for near-threshold candidates | High | High |
| P4 | Per-category/model adaptive thresholds | Medium | High |

---

## Topic 2: Gamification of Developer AI Adoption

### 2.1 The AI League Architecture Is Directionally Sound

The 7-dimensional scoring engine (quality 35%, robustness 20%, token_efficiency 15%, speed 10%, cost_efficiency 10%, improvement_rate 5%, creativity 5%) is more sophisticated than anything found in public competitor documentation. The season-level weight overrides and creativity scoring via centroid cosine distance are novel. No primary research was found that validates or invalidates these specific dimensions — calibration must come from internal feedback.

### 2.2 The Critical Design Risk: Autonomy, Not Competence

**Finding (3-0 adversarially confirmed):** Competence-boosting scoring mechanics alone are **insufficient to sustain intrinsic motivation** in enterprise gamification programs. Autonomy must also be perceived.

Source: TechTrends 2024 (Springer, peer-reviewed, DOI 10.1007/s11528-024-00968-9), applying Ryan & Deci's Self-Determination Theory:

> "Competence is necessary but not sufficient for high-quality motivation... perceptions of competence increase intrinsic motivation only with perceived autonomy."

**Applied to the AI League:**
- Mandatory leaderboard visibility undermines engagement for engineers who are not competing to win
- Fixed scoring weight dimensions that participants cannot adjust feel imposed rather than chosen
- Mandatory participation (usage metrics tied to performance reviews) is the highest-risk pattern — but this is a program design choice, not a League design choice

**Highest-leverage design changes:**
1. **Opt-in participation** — the League should feel like an opportunity, not a report card
2. **Player-adjustable scoring weights** — let engineers declare their season focus (e.g. "I'm optimizing for token efficiency this month"), unlocking a personalized dimension weighting that still contributes to the global leaderboard
3. **Private mode** — allow engineers to participate without appearing on the public leaderboard; their scores still count for self-improvement tracking

These changes preserve the scoring architecture while shifting the motivational framing from controlled to autonomous.

### 2.3 What Competitors Do

Based on secondary sources (not adversarially verified — treat as directional):

**Microsoft 365 Copilot (internal):** Gamification program tracked "Copilot champions" (named advocates, office hours, contribution feed) — functionally identical to the champion community in ai-gw. Microsoft's internal rollout blog emphasizes **social learning and peer visibility** over points/leaderboards as the primary engagement driver.

**GitHub Copilot adoption programs:** Focus on usage metrics and team-level dashboards rather than individual competition. No evidence of prompt-engineering competitions or multi-dimensional scoring.

**Generic enterprise AI adoption programs:** SHRM research suggests the most durable engagement comes from **embedding AI tools into existing workflows** (workflow integration > gamification). No enterprise AI tool was found to use 7-dimensional competitive scoring — the AI League appears to be a novel approach in this space.

**Assessment:** The AI League occupies an underexplored niche. The risk is not that competitors are doing this better; the risk is that the approach itself requires careful autonomy design to avoid backfiring.

### 2.4 Open Questions on Gamification

- What is the current participation rate? Opt-in vs. total eligible engineers?
- Are scoring weights ever discussed in team retrospectives? This is the signal that the dimensions resonate.
- Is the creativity dimension (centroid cosine distance) perceived as meaningful by participants, or gamed by prompt noise? No primary source validates cosine distance from centroid as a measure of creative AI use.
- Does the cosmetic store have meaningful item turnover? If items are purely cosmetic with no status signal, the store may have lower retention effect than expected.

---

## Topic 3: AI Gateway Market Landscape (2024-2025)

### 3.1 Table-Stakes Features (Where ai-gw Is Competitive)

Based on cross-vendor comparison of Kong AI Gateway, Portkey, Helicone, LiteLLM proxy, Cloudflare AI Gateway, and open-source alternatives:

| Feature | ai-gw | Market |
|---|---|---|
| Multi-provider routing | ✅ 26+ models via LiteLLM | Standard |
| API key + JWT auth | ✅ Dual credential, JWKS 3-tier | Standard |
| Rate limiting (per team/model) | ✅ Fixed-window | Standard (most use sliding window) |
| Semantic + exact cache | ✅ (broken O(N) — upgrade needed) | Premium tier / paid feature |
| Budget enforcement | ✅ 3-tier (key/team/org) | Standard |
| Cost observability | ✅ Per-session cost tracking | Standard |
| Guardrails (PII, injection) | ✅ 10 platform rules + custom | Standard at enterprise tier |
| Fallback routing | ⚠️ Only claude-sonnet→gemini-1.5-pro | Standard (more comprehensive) |

### 3.2 Differentiators at 2000-Engineer Scale (Where ai-gw Has Gaps)

| Feature | ai-gw | Market |
|---|---|---|
| Distributed tracing (OTel) | ❌ Missing | Differentiator — Portkey, Kong offer this |
| Prometheus /metrics | ❌ Missing | Standard at enterprise |
| Horizontal agent relay | ❌ Single-instance limit | Unique to ai-gw's agentic features |
| PostgreSQL HA | ❌ Burstable B2ms, HA disabled | Infrastructure gap, not gateway gap |
| Semantic cache with vector index | ❌ O(N) scan | Portkey has HNSW-backed semantic cache |
| Workflow DAG execution | ✅ Unique — no competitor match | **True differentiator** |
| AI League / gamification | ✅ Unique — no competitor match | **True differentiator** |
| Security scanner (garak + nuclei) | ✅ Unique depth | **True differentiator** |
| Per-developer memory palace | ✅ Unique — no competitor match | **True differentiator** |
| Champion community | ✅ Unique | **True differentiator** |

### 3.3 LiteLLM Supply Chain Note

One source (Trend Micro, March 2026) reported a LiteLLM supply chain compromise. This source was flagged as `unreliable` by the research harness (claims were not adversarially verified) and is included only as a flag: the ai-gw deployment uses `ghcr.io/berriai/litellm:main-latest` (floating tag, §9.10 of codebase audit). Pinning to a specific version is P0 from a supply chain perspective regardless of whether the specific incident is verified.

### 3.4 Open-Source Gateway Architecture Patterns

The market has converged on two architectural patterns for enterprise AI gateways:

**Pattern A (Kong/Nginx style):** Single high-performance proxy layer, plugins for auth/rate-limiting/caching, observability via sidecar. Optimized for throughput and low added latency. Less suited for agentic workloads.

**Pattern B (FastAPI microservices style):** ai-gw's current pattern. Higher operational complexity, but enables the agentic primitives (workflow worker, relay, identity service) that Pattern A gateways cannot provide without bespoke extension.

The market is moving toward Pattern B for agentic workloads. Cloudflare AI Gateway and AWS Bedrock are building toward agentic primitives but are 12-18 months behind the ai-gw feature set.

**Assessment:** ai-gw's Pattern B microservices approach is architecturally ahead of the market for agentic enterprise use cases. The technical debt items (OTel, Prometheus, horizontal relay, vector cache) are real but not architectural rethinks.

---

## Open Questions

1. **Cache hit rate baseline**: What is the current semantic cache hit rate in production? What fraction of misses are near-threshold (0.85–0.95 similarity) vs. genuinely non-repetitive queries? This determines whether threshold relaxation or async judge promotion is the higher-ROI first step.

2. **pgvector vs. Redis Stack for semantic cache**: Should the semantic cache be migrated to pgvector (reusing existing PostgreSQL Flexible Server) or Redis Stack RediSearch? pgvector avoids a new managed dependency but adds vector workload to the primary B2ms database server. This is a DB sizing question before it is an architecture question.

3. **AI League participation health**: What is the opt-in vs. total eligible ratio? SDT predicts opt-in outperforms mandatory, but the threshold at which a mostly-opt-in league loses competitive tension is organization-specific.

4. **Creativity dimension validity**: Is centroid cosine distance a defensible measure of creative AI use, or does it primarily reward prompt novelty that correlates weakly with actual output quality? No primary source validates this approach.

---

## Caveats and Research Limitations

1. **Quantitative specifics excluded**: All numerical claims about cache hit rates, latency breakdowns, recall loss percentages, and burnout coefficients failed adversarial verification (0-3 votes). Specific numbers must come from production measurement.

2. **Krites paper scope**: The async LLM-judge finding comes from a single February 2026 preprint (Apple ML Research, ACM EuroMLSys). The architecture is sound; specific improvement multipliers were refuted. Do not plan capacity around claimed improvement factors.

3. **Gamification research gap**: No primary research was found on AI-tool-specific gamification at enterprise scale (2000+ engineers). The SDT findings apply to gamification broadly; the AI League operates in an underresearched domain.

4. **Market landscape not primary-source verified**: Claims about Kong AI, Portkey, Helicone, and Cloudflare AI Gateway feature sets are based on secondary sources (product documentation, marketing). Treat competitive feature comparisons as directionally correct but not audited.

---

## Sources (Confirmed Claims Only)

| Source | Type | Finding |
|---|---|---|
| [arXiv 2603.03301](https://arxiv.org/html/2603.03301v1) | Primary (academic) | 0.95 cosine threshold is stricter than any tested threshold |
| [arXiv 2602.13165](https://arxiv.org/abs/2602.13165) | Primary (ACM EuroMLSys 2026) | Static thresholds suboptimal; async LLM-judge architecture |
| [TechTrends 2024 (Springer)](https://link.springer.com/article/10.1007/s11528-024-00968-9) | Primary (peer-reviewed) | SDT: competence + autonomy required for intrinsic motivation |

All other 26 sources contributed to scope and context but did not survive adversarial verification for specific claims.
