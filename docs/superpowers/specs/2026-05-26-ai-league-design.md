# AI-League — Design Spec

**Date:** 2026-05-26  
**Author:** benjamin  
**Status:** Approved for implementation planning

---

## Overview

AI-League is a gamified competition platform for the ~2000 SimCorp engineers on the AI gateway. Engineers design agent configurations (system prompt + tool setup) to solve curated challenges. Their agents are evaluated against hidden test harnesses and scored across multiple dimensions. Points accumulate toward a cosmetic store. Seasons run quarterly with rolling weekly/bi-weekly challenges.

**Goals:**
- Build AI-first skills across the engineering population
- Surface high-quality agent designs and best practices the platform team can standardise
- Drive engagement and cultural adoption of the AI gateway

**Non-goals:** Real-work ticket scoring, team competition, pay-to-win mechanics.

---

## Architecture

A dedicated `league` FastAPI service runs at port **8010**, added to `infra/docker-compose.yml`. It owns all league logic and is the only new service introduced. Existing services are consumers or dependencies, not modified.

```
admin-portal :3001  ──┐
                       ├─► league :8010 ──► litellm :8003  (agent execution)
developer-portal :3002 ┘         │      ──► auth :8001     (JWT validation)
                                  │      ──► observability :8004 (run event log)
                                  └──────► postgres         (league schema)
```

**Service responsibilities:**
- Challenge registry — CRUD for challenge definitions and seasons
- Submission executor — calls litellm with the engineer's agent config against hidden test inputs
- Scoring engine — computes multi-dimensional scores from run results
- Leaderboard — per-season rankings, updated after each challenge closes
- Season manager — lifecycle (upcoming → active → closed), weight config
- Store & economy — point ledger, item catalogue, purchase history
- Challenge proposals — community submission queue with admin review workflow

---

## Data Model

All tables live in the shared Postgres instance under a `league` schema.

### seasons
| column | type | notes |
|---|---|---|
| id | uuid PK | |
| name | text | e.g. "Q2 2026" |
| status | enum | upcoming / active / closed |
| starts_at | timestamptz | |
| ends_at | timestamptz | |
| scoring_weights | jsonb | dimension → weight (must sum to 1.0); locked once status = active |
| season_multiplier | numeric | default 1.0; applied to point earnings |

### challenges
| column | type | notes |
|---|---|---|
| id | uuid PK | |
| season_id | uuid FK | |
| title | text | |
| goal | text | always visible to engineers |
| training_inputs | jsonb | array of {input, expected_output}; visible in training mode |
| hidden_test_suite | jsonb | array of {input, expected_output, weight}; never exposed |
| allowed_models | text[] | models engineers may use for this challenge |
| max_tokens_budget | int | hard cap per run |
| max_league_attempts | int | default 3 |
| scores_revealed_at | timestamptz | when league scores become visible (on challenge close) |
| status | enum | draft / active / closed |
| proposed_by | uuid FK users | null for admin-created |

### submissions
| column | type | notes |
|---|---|---|
| id | uuid PK | |
| challenge_id | uuid FK | |
| engineer_id | uuid FK users | |
| mode | enum | training / league |
| system_prompt | text | the agent design |
| tool_config | jsonb | tool names + descriptions + schemas |
| attempt_number | int | monotonic per engineer per challenge per mode |
| run_results | jsonb | per-test-case outputs, tokens, latency, cost |
| prompt_hash | text | sha256 of system_prompt; used for copy-paste detection |
| submitted_at | timestamptz | |

### scores
| column | type | notes |
|---|---|---|
| id | uuid PK | |
| submission_id | uuid FK | |
| quality | numeric | 0–100 |
| robustness | numeric | 0–100 |
| token_efficiency | numeric | 0–100 (normalised against season median) |
| speed | numeric | 0–100 (normalised against season median) |
| cost_efficiency | numeric | 0–100 (normalised against season median) |
| improvement_rate | numeric | delta vs personal season best, capped at +50% |
| creativity | numeric | 0–100; cosine distance from submission centroid |
| composite | numeric | weighted sum, scaled 0–1000 |

### leaderboard_entries
| column | type | notes |
|---|---|---|
| season_id | uuid FK | |
| engineer_id | uuid FK | |
| composite_score | numeric | best composite across all league submissions this season |
| rank | int | recomputed on challenge close |
| points_earned | int | floor(composite × season_multiplier) |

### points_ledger
| column | type | notes |
|---|---|---|
| id | uuid PK | |
| engineer_id | uuid FK | |
| delta | int | positive = earned, negative = spent |
| reason | enum | league_submission_reward / training_xp_reward / store_purchase / admin_grant |
| ref_id | uuid | FK to submission or store purchase |
| created_at | timestamptz | |

Current balance = `SUM(delta)` for engineer. Append-only.

### store_items
| column | type | notes |
|---|---|---|
| id | uuid PK | |
| name | text | |
| type | enum | badge / card_border / avatar_frame / title |
| point_cost | int | |
| asset_url | text | |
| exclusive_season_id | uuid FK nullable | if set, only top-N finishers receive it; not purchasable |
| exclusive_top_n | int nullable | |

### purchases
| column | type | notes |
|---|---|---|
| id | uuid PK | |
| engineer_id | uuid FK | |
| item_id | uuid FK | |
| purchased_at | timestamptz | |

### challenge_proposals
| column | type | notes |
|---|---|---|
| id | uuid PK | |
| proposed_by | uuid FK users | |
| title | text | |
| goal | text | |
| notes | text | additional context from proposer |
| status | enum | proposed / approved / rejected |
| reviewed_by | uuid FK users nullable | |
| reviewer_notes | text nullable | |

---

## Challenge & Submission Flow

### Training Mode
1. Engineer opens a challenge — sees goal, full problem description, example inputs and expected outputs.
2. Engineer writes a system prompt and tool config in the agent designer.
3. Engineer submits. No attempt limit.
4. League service validates JWT, calls litellm with the hidden test suite (same harness as league mode), collects per-test outputs + tokens + latency + cost.
5. Scores computed and returned immediately.
6. Engineer can iterate and resubmit freely.
7. Training submissions earn XP points (flat, not composite-scaled) but do not affect the leaderboard.

### League Mode
1. Engineer opens the challenge — sees the **goal only**. No examples, no hints.
2. Engineer writes system prompt + tool config blind.
3. Engineer submits. Attempt counter increments (max 3 by default).
4. Agent runs against hidden test suite via litellm. Results stored but **not shown to the engineer**.
5. When the challenge deadline passes, all league scores are revealed simultaneously. This prevents real-time rank-watching and last-minute gaming.
6. Best composite score across the engineer's league attempts counts for the leaderboard.
7. Points awarded = `floor(composite_score × season_multiplier)`.

### Execution Pipeline (both modes)
```
league:8010 → auth:8001 (validate JWT)
           → litellm:8003 (run agent against each test case; pinned model + temperature + seed)
           → scoring engine (grade outputs, normalise, compute composite)
           → postgres (write submission + scores)
           → observability:8004 (log run event: tokens, latency, cost, engineer_id)
```

---

## Scoring Engine

Seven dimensions, each 0–100. Composite = weighted sum scaled to 0–1000.

| Dimension | Measurement | Default weight |
|---|---|---|
| Quality | Correctness against hidden test cases: exact/fuzzy match for structured outputs (classification, extraction); LLM-as-judge rubric (via litellm) for open-ended outputs | 35% |
| Robustness | % of edge-case/adversarial test variants the agent handles correctly | 20% |
| Token efficiency | Inverse of token usage, normalised against the season median for this challenge | 15% |
| Speed | Inverse of p50 latency across test runs, normalised against season median | 10% |
| Cost efficiency | Inverse of total $ cost, normalised against season median | 10% |
| Improvement rate | `(this_score − personal_season_best) / personal_season_best`, capped at +50%, then scaled | 5% |
| Creativity | Cosine distance of system_prompt embedding from the centroid of all submissions for this challenge | 5% |

**Admin controls:** Weights are editable per-season via the admin portal before the season goes active. Validation enforces they sum to 100%. Once status = active, weights are locked to ensure consistency across all submissions in that season.

**Creativity scoring:** The league service calls the litellm embeddings endpoint to embed each submitted system prompt. After the challenge closes, it computes the centroid of all submission embeddings and scores each submission by its cosine distance from that centroid, normalised 0–100. High distance = more novel approach.

**Improvement rate** rewards engineers who start lower and learn fast, preventing the league from being purely a "best engineers win" outcome.

---

## Leaderboard & Season Management

- Leaderboard is per-season. It resets at season start.
- Each engineer's leaderboard entry is their **best composite score** across all league submissions in the season, not a sum. This rewards quality over volume.
- Rankings are recomputed and published after each challenge closes (not in real-time mid-challenge).
- Leaderboard displays: rank, engineer name, team/area (from org hierarchy), composite score, quality score, token efficiency indicator, trend vs previous challenge.
- Season-end: top-3 engineers receive exclusive store items (Champion Crown, Silver, Bronze) that are not purchasable. Season-specific items are permanently locked after the season closes.

---

## Store & Points Economy

- Points are earned from league submissions: `floor(composite_score × season_multiplier)`.
- Training submissions earn a flat 50 XP points (encourages practice without inflating league balances).
- Points are spent in the cosmetic store. All items are cosmetic only — purchases never affect scores or rankings. This is enforced server-side; the scoring engine has no access to purchase history.
- **Item types:** profile badge, card border, avatar frame, display title.
- **Season-exclusive items:** items with `exclusive_season_id` set are granted automatically to top-N finishers at season close. They cannot be purchased.
- The points ledger is append-only. Refunds are negative entries, not deletions.

---

## Admin Portal

**Season Manager tab:**
- Create/edit seasons (name, dates, scoring weights, multiplier).
- Weights are editable only while season is in `upcoming` status.
- One-click close season early (with confirmation).
- Export leaderboard as CSV.

**Challenge Builder tab:**
- Create/edit challenges: title, goal, training inputs, hidden test suite, allowed models, token budget, max league attempts, season multiplier override, deadline.
- Promote approved community proposals directly into the challenge builder (pre-fills fields from the proposal).
- Save as draft; publish to season when ready.

**Community Proposals tab:**
- Queue of engineer-submitted challenge ideas.
- Admin can approve (→ opens in challenge builder), reject (with optional notes), or request changes.
- Proposer is notified of outcome.

**Store Editor tab:**
- Add/edit/remove store items: name, type, point cost, asset upload, exclusivity settings.

---

## Anti-Gaming Measures

| Mechanism | What it prevents |
|---|---|
| League scores hidden until challenge deadline | Real-time rank-watching and last-minute prompt adjustment based on others' visible scores |
| Limited league attempts (default 3, configurable) | Brute-force prompt tuning against the live scorer |
| Fixed execution environment (pinned model, temperature, seed per challenge) | Variance in results across attempts; ensures all engineers compete under identical conditions |
| Submission hash deduplication | Identical system prompts across different engineers are flagged for admin review (copy-paste detection) |
| Training mode rate limiting (10 submissions/hour per engineer per challenge) | Automated grid-search over prompts using the training harness as a proxy oracle |
| Append-only points ledger | Point manipulation via deletion |

---

## Developer Portal UI

New **League** section in the developer portal sidebar, with four pages:

1. **Challenges** — active challenges, mode toggle (training/league), submit button, attempt counter for league mode.
2. **My Results** — history of submissions, per-dimension scores, improvement trend over the season.
3. **Leaderboard** — season standings with your rank highlighted, filterable by area/unit.
4. **Store & Profile** — point balance, item catalogue, purchased items, active cosmetics.

---

## Testing Strategy

- Unit tests for the scoring engine (each dimension calculation, weight normalisation, composite formula).
- Integration tests for the submission execution pipeline using a mock litellm endpoint.
- API tests for all league endpoints (auth, attempt limits, score visibility rules).
- The hidden test suite is never returned in any API response — this is enforced by a query-level rule (hidden_test_suite column excluded from all non-admin reads).
