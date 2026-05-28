# AI League API

The League API implements a competitive challenge platform where developers submit solutions to AI-focused problems, earn points based on multi-dimensional scoring, and compete on seasonal leaderboards. The system integrates with the Champions API for shared gamification.

## Authentication

All endpoints require Bearer token authentication via `Authorization: Bearer <token>` header. Admin endpoints additionally require admin authentication.

Developer auth is validated via `require_dev_auth` middleware. Admin endpoints use `require_admin_auth`.

## Core Concepts

- **Seasons**: Time-bounded competition periods with custom scoring weights and multipliers (draft → active → closed)
- **Challenges**: Problems with training and hidden test suites, created by admins or developers via proposals
- **Submissions**: Solutions submitted by engineers; scored on quality, robustness, efficiency, speed, and creativity
- **Leaderboard**: Ranked engineers by composite score for a season
- **Store**: Point-based cosmetic shop (badges, frames, titles)
- **Points Ledger**: Transaction log of earned/spent points
- **Proposals**: Developer-created challenge ideas, reviewed by admins

## Seasons

### List Seasons

`GET /seasons`

Return all seasons (upcoming, active, closed) in reverse chronological order by start date.

**Response:**
```json
[
  {
    "id": "550e8400-e29b-41d4-a716-446655440000",
    "name": "Spring 2026",
    "status": "active",
    "starts_at": "2026-05-01T00:00:00Z",
    "ends_at": "2026-07-31T23:59:59Z",
    "scoring_weights": {
      "quality": 0.2,
      "robustness": 0.15,
      "token_efficiency": 0.15,
      "speed": 0.15,
      "cost_efficiency": 0.15,
      "improvement_rate": 0.1,
      "creativity": 0.1
    },
    "season_multiplier": 1.0,
    "created_at": "2026-04-15T10:30:00Z"
  }
]
```

### Create Season (Admin)

`POST /seasons`

Create a new season with custom scoring weights. All weights must sum to 1.0.

**Request:**
```json
{
  "name": "Spring 2026",
  "starts_at": "2026-05-01T00:00:00Z",
  "ends_at": "2026-07-31T23:59:59Z",
  "scoring_weights": {
    "quality": 0.2,
    "robustness": 0.15,
    "token_efficiency": 0.15,
    "speed": 0.15,
    "cost_efficiency": 0.15,
    "improvement_rate": 0.1,
    "creativity": 0.1
  },
  "season_multiplier": 1.0
}
```

**Response:**
```json
{
  "id": "550e8400-e29b-41d4-a716-446655440000",
  "name": "Spring 2026",
  "status": "upcoming",
  "starts_at": "2026-05-01T00:00:00Z",
  "ends_at": "2026-07-31T23:59:59Z",
  "scoring_weights": { ... },
  "season_multiplier": 1.0,
  "created_at": "2026-04-15T10:30:00Z"
}
```

**Validation:**
- Weights must be non-negative
- Weights must sum to 1.0 ± 0.01 tolerance
- Weight keys must be exactly: `quality`, `robustness`, `token_efficiency`, `speed`, `cost_efficiency`, `improvement_rate`, `creativity`

### Update Season Weights (Admin)

`PATCH /seasons/{season_id}/weights`

Modify scoring weights for an upcoming season. Cannot change weights once a season is active or closed.

**Request:**
```json
{
  "quality": 0.25,
  "robustness": 0.15,
  "token_efficiency": 0.15,
  "speed": 0.15,
  "cost_efficiency": 0.15,
  "improvement_rate": 0.1,
  "creativity": 0.05
}
```

**Response:**
```json
{
  "id": "550e8400-e29b-41d4-a716-446655440000",
  "scoring_weights": { ... }
}
```

**Error Responses:**
- `404 Not Found`: Season not found
- `409 Conflict`: Cannot change weights for active or closed seasons

### Update Season Status (Admin)

`PATCH /seasons/{season_id}/status`

Transition season status: `upcoming` → `active` → `closed`.

**Request:**
```json
{
  "status": "active"
}
```

**Response:**
```json
{
  "id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "active"
}
```

**Valid Statuses:** `upcoming`, `active`, `closed`

## Challenges

### List Challenges for a Season

`GET /seasons/{season_id}/challenges`

List all challenges (draft, active, closed) in a season.

**Response:**
```json
[
  {
    "id": "650e8400-e29b-41d4-a716-446655440000",
    "season_id": "550e8400-e29b-41d4-a716-446655440000",
    "title": "Build a Smart Classifier",
    "goal": "Create a system prompt that classifies emails as spam with >95% accuracy",
    "training_inputs": [
      {
        "input": "Get free crypto now!!!",
        "expected": "spam"
      },
      {
        "input": "Q3 all-hands meeting scheduled for Friday",
        "expected": "legitimate"
      }
    ],
    "allowed_models": ["claude-sonnet-4-6"],
    "max_tokens_budget": 4096,
    "max_league_attempts": 3,
    "scores_revealed_at": null,
    "status": "active",
    "proposed_by": null,
    "created_at": "2026-05-01T10:30:00Z"
  }
]
```

### Get Challenge Details

`GET /challenges/{challenge_id}`

Fetch a specific challenge (public fields only; hidden test suite not included).

**Response:**
```json
{
  "id": "650e8400-e29b-41d4-a716-446655440000",
  "season_id": "550e8400-e29b-41d4-a716-446655440000",
  "title": "Build a Smart Classifier",
  "goal": "Create a system prompt that classifies emails as spam with >95% accuracy",
  "training_inputs": [ ... ],
  "allowed_models": ["claude-sonnet-4-6"],
  "max_tokens_budget": 4096,
  "max_league_attempts": 3,
  "scores_revealed_at": null,
  "status": "active",
  "proposed_by": null,
  "created_at": "2026-05-01T10:30:00Z"
}
```

### Create Challenge (Admin)

`POST /seasons/{season_id}/challenges`

Create a new challenge with training and hidden test suites. Hidden test suite is not revealed to engineers.

**Request:**
```json
{
  "title": "Build a Smart Classifier",
  "goal": "Create a system prompt that classifies emails as spam with >95% accuracy",
  "training_inputs": [
    {
      "input": "Get free crypto now!!!",
      "expected": "spam",
      "weight": 1.0
    }
  ],
  "hidden_test_suite": [
    {
      "input": "Limited-time offer for you",
      "expected": "spam",
      "weight": 1.0
    }
  ],
  "allowed_models": ["claude-sonnet-4-6"],
  "max_tokens_budget": 4096,
  "max_league_attempts": 3
}
```

**Response:** Same as Get Challenge Details, but includes `hidden_test_suite` (admin only).

### Update Challenge Status (Admin)

`PATCH /challenges/{challenge_id}/status`

Transition challenge status: `draft` → `active` → `closed`. When a challenge closes, leaderboard ranks are finalized and `scores_revealed_at` is set.

**Request:**
```json
{
  "status": "active"
}
```

**Response:**
```json
{
  "id": "650e8400-e29b-41d4-a716-446655440000",
  "status": "active"
}
```

**Valid Statuses:** `draft`, `active`, `closed`

## Submissions & Scoring

### Submit Challenge Solution

`POST /challenges/{challenge_id}/submit`

Submit a system prompt and optional tool config for a challenge. Tested against training inputs (mode=training) or hidden test suite (mode=league). Scores are computed from 7 dimensions.

**Request:**
```json
{
  "mode": "league",
  "system_prompt": "You are an expert email classifier. Classify emails as 'spam' or 'legitimate'...",
  "tool_config": []
}
```

**Modes:**
- `training`: Submit against training inputs, scores revealed immediately, 50 XP earned
- `league`: Submit against hidden test suite, 3 attempts max, scores hidden until challenge closes, points earned if best score

**Response (Training Mode):**
```json
{
  "submission_id": "750e8400-e29b-41d4-a716-446655440000",
  "scores": {
    "quality": 92.5,
    "robustness": 88.3,
    "token_efficiency": 75.2,
    "speed": 81.4,
    "cost_efficiency": 92.1,
    "improvement_rate": 50.0,
    "creativity": 50.0,
    "composite": 78.63
  },
  "run_results": [
    {
      "input": "Get free crypto now!!!",
      "expected": "spam",
      "actual": "spam",
      "tokens": 42,
      "latency_ms": 285,
      "cost_usd": 0.0012,
      "weight": 1.0
    }
  ]
}
```

**Response (League Mode):**
```json
{
  "submission_id": "750e8400-e29b-41d4-a716-446655440000",
  "message": "Submission received. Scores will be revealed when the challenge closes."
}
```

**Scoring Dimensions:**
- **Quality**: Exact match score (1.0 per correct output)
- **Robustness**: Percentage of test cases passed
- **Token Efficiency**: Inverse score based on token usage (median = 500)
- **Speed**: Inverse score based on latency in ms (median = 300ms)
- **Cost Efficiency**: Inverse score based on API cost (median = $0.0005)
- **Improvement Rate**: Score improvement vs. engineer's best prior submission
- **Creativity**: Manual evaluation (hardcoded 50.0 for now)
- **Composite**: Weighted combination of all dimensions per season weights

**Error Responses:**
- `404 Not Found`: Challenge not found
- `409 Conflict`: Challenge is not active
- `429 Too Many Requests`: League attempt limit reached

### List My Submissions

`GET /submissions/mine?challenge_id={challenge_id}`

List the authenticated engineer's submissions (training and league). For league-mode rows, scores are only visible if the challenge is closed or if in training mode.

**Query Parameters:**
- `challenge_id` (optional): Filter to specific challenge

**Response:**
```json
[
  {
    "id": "750e8400-e29b-41d4-a716-446655440000",
    "challenge_id": "650e8400-e29b-41d4-a716-446655440000",
    "challenge_title": "Build a Smart Classifier",
    "mode": "training",
    "attempt_number": 1,
    "submitted_at": "2026-05-28T14:30:00Z",
    "scores": {
      "quality": 92.5,
      "robustness": 88.3,
      "token_efficiency": 75.2,
      "speed": 81.4,
      "cost_efficiency": 92.1,
      "improvement_rate": 50.0,
      "creativity": 50.0,
      "composite": 78.63
    }
  },
  {
    "id": "850e8400-e29b-41d4-a716-446655440000",
    "challenge_id": "650e8400-e29b-41d4-a716-446655440000",
    "challenge_title": "Build a Smart Classifier",
    "mode": "league",
    "attempt_number": 1,
    "submitted_at": "2026-05-28T15:30:00Z"
  }
]
```

**Note:** League-mode submissions without revealed scores do not include a `scores` field.

## Leaderboard

### Get Leaderboard for Season

`GET /seasons/{season_id}/leaderboard`

Ranked list of all engineers in a season by composite score.

**Response:**
```json
[
  {
    "engineer_id": "550e8400-e29b-41d4-a716-446655440000",
    "email": "alice@simcorp.com",
    "display_name": "Alice Chen",
    "team_name": "Platform",
    "area_name": "Infrastructure",
    "composite_score": 92.45,
    "rank": 1,
    "points_earned": 9245,
    "updated_at": "2026-05-28T16:00:00Z"
  },
  {
    "engineer_id": "660e8400-e29b-41d4-a716-446655440000",
    "email": "bob@simcorp.com",
    "display_name": "Bob Smith",
    "team_name": "Observability",
    "area_name": "Infrastructure",
    "composite_score": 88.12,
    "rank": 2,
    "points_earned": 8812,
    "updated_at": "2026-05-28T15:45:00Z"
  }
]
```

### Get My Rank

`GET /seasons/{season_id}/leaderboard/me`

Get the authenticated engineer's rank and score in a specific season.

**Response:**
```json
{
  "rank": 1,
  "composite_score": 92.45,
  "points_earned": 9245
}
```

**Notes:**
- If engineer has no submissions, returns `rank: null`, `composite_score: 0.0`, `points_earned: 0`

## Store

The store allows engineers to spend earned points on cosmetic items (badges, avatar frames, card borders, titles).

### Get Point Balance

`GET /store/balance`

Get the authenticated engineer's total earned points (sum of all ledger entries).

**Response:**
```json
{
  "balance": 12450
}
```

### List Store Items

`GET /store/items?include_inactive={include_inactive}`

List available store items. Developers see only active items. Admins can pass `?include_inactive=true` to see deactivated items.

**Query Parameters:**
- `include_inactive` (optional, default=false): Include inactive items (admin only)

**Response:**
```json
[
  {
    "id": "950e8400-e29b-41d4-a716-446655440000",
    "name": "Gold Star Badge",
    "type": "badge",
    "point_cost": 500,
    "asset_url": "https://assets.simcorp.com/badges/gold-star.png",
    "exclusive_season_id": null,
    "exclusive_top_n": null,
    "active": true
  },
  {
    "id": "a50e8400-e29b-41d4-a716-446655440000",
    "name": "Season Spring 2026 #1 Frame",
    "type": "card_border",
    "point_cost": 0,
    "asset_url": "https://assets.simcorp.com/frames/spring-2026-1.png",
    "exclusive_season_id": "550e8400-e29b-41d4-a716-446655440000",
    "exclusive_top_n": 1,
    "active": true
  }
]
```

**Item Types:**
- `badge`: Profile badge icon
- `card_border`: Customized appearance around contribution/leaderboard cards
- `avatar_frame`: Framing for user avatar
- `title`: Cosmetic title prefix/suffix

### Create Store Item (Admin)

`POST /store/items`

Create a new store item.

**Request:**
```json
{
  "name": "Gold Star Badge",
  "type": "badge",
  "point_cost": 500,
  "asset_url": "https://assets.simcorp.com/badges/gold-star.png"
}
```

**Response:**
```json
{
  "id": "950e8400-e29b-41d4-a716-446655440000",
  "name": "Gold Star Badge",
  "type": "badge",
  "point_cost": 500,
  "asset_url": "https://assets.simcorp.com/badges/gold-star.png",
  "exclusive_season_id": null,
  "exclusive_top_n": null,
  "active": true
}
```

### Update Store Item (Admin)

`PATCH /store/items/{item_id}`

Modify an existing item (name, cost, asset URL, active status).

**Request:**
```json
{
  "name": "Platinum Star Badge",
  "point_cost": 750,
  "active": true
}
```

**Response:**
```json
{
  "id": "950e8400-e29b-41d4-a716-446655440000",
  "name": "Platinum Star Badge",
  "type": "badge",
  "point_cost": 750,
  "asset_url": "https://assets.simcorp.com/badges/gold-star.png",
  "exclusive_season_id": null,
  "exclusive_top_n": null,
  "active": true
}
```

### Purchase Item

`POST /store/purchase/{item_id}`

Buy an item with earned points (idempotent per item). Points are deducted from the ledger.

**Response:**
```json
{
  "item_id": "950e8400-e29b-41d4-a716-446655440000",
  "new_balance": 11950
}
```

**Error Responses:**
- `402 Payment Required`: Insufficient points
- `404 Not Found`: Item not found
- `409 Conflict`: Item already owned
- `410 Gone`: Item no longer available (inactive)
- `403 Forbidden`: Exclusive items cannot be directly purchased (reserved for top-N finishers)

### Get Owned Items

`GET /store/owned`

List items purchased by the authenticated engineer.

**Response:**
```json
[
  {
    "id": "950e8400-e29b-41d4-a716-446655440000",
    "name": "Gold Star Badge",
    "type": "badge",
    "asset_url": "https://assets.simcorp.com/badges/gold-star.png",
    "purchased_at": "2026-05-28T14:30:00Z"
  }
]
```

## Proposals

Engineers can propose new challenges; admins review and approve or reject them.

### Create Challenge Proposal

`POST /proposals`

Submit a challenge idea for admin review.

**Request:**
```json
{
  "title": "Rate Limiter Design Challenge",
  "goal": "Design a distributed rate limiter that handles 10k+ requests/sec across multiple services",
  "notes": "This would help engineers understand scalability and distributed systems"
}
```

**Response:**
```json
{
  "id": "b50e8400-e29b-41d4-a716-446655440000",
  "status": "proposed"
}
```

### List Proposals (Admin)

`GET /proposals`

List all proposals with review status.

**Response:**
```json
[
  {
    "id": "b50e8400-e29b-41d4-a716-446655440000",
    "title": "Rate Limiter Design Challenge",
    "goal": "Design a distributed rate limiter that handles 10k+ requests/sec across multiple services",
    "notes": "This would help engineers understand scalability and distributed systems",
    "status": "proposed",
    "proposer_name": "alice@simcorp.com",
    "proposed_by": "550e8400-e29b-41d4-a716-446655440000",
    "reviewed_by": null,
    "reviewer_notes": "",
    "created_at": "2026-05-28T10:30:00Z"
  }
]
```

### Review Proposal (Admin)

`PATCH /proposals/{proposal_id}/review`

Approve or reject a proposal.

**Request:**
```json
{
  "status": "approved",
  "reviewer_notes": "Great idea! Converting to challenge."
}
```

**Response:**
```json
{
  "id": "b50e8400-e29b-41d4-a716-446655440000",
  "status": "approved"
}
```

**Valid Statuses:** `approved`, `rejected`

## Points Ledger

### Internal: Point Grants (Admin)

`POST /internal/points`

Admin-only endpoint to grant or deduct points (used by other services like Champions). Not directly exposed to regular engineers.

Points are earned through:
- **Training submission**: 50 XP per submission
- **League submission**: Points = composite_score × season_multiplier
- **Ask resolution (Champions)**: 200 points
- **Content upvote (Champions)**: 5 points per upvote
- **Office hours (Champions)**: 150 points per completed booking

Points are spent through:
- **Store purchase**: Item's point_cost

## Error Handling

All endpoints follow REST conventions:

- `400 Bad Request`: Malformed request body or validation error
- `402 Payment Required`: Insufficient points for purchase
- `404 Not Found`: Resource not found
- `409 Conflict`: State conflict (e.g., item already owned, attempt limit reached)
- `410 Gone`: Resource no longer available (e.g., inactive item)
- `422 Unprocessable Entity`: Invalid enum value or constraint violation
- `429 Too Many Requests`: Rate limit exceeded
- `5xx Server Error`: Internal error

## Base URL

All endpoints are relative to the league service URL:
```
http://localhost:8010
```

In production (with nginx):
```
http://localhost:8080/league
```

## Example: Complete Challenge Workflow

1. **Admin creates season:** `POST /seasons`
2. **Admin creates challenge:** `POST /seasons/{season_id}/challenges`
3. **Admin activates challenge:** `PATCH /challenges/{challenge_id}/status` with `status: "active"`
4. **Engineer trains:** `POST /challenges/{challenge_id}/submit` with `mode: "training"` (multiple times)
5. **Engineer submits for league:** `POST /challenges/{challenge_id}/submit` with `mode: "league"`
6. **Engineer checks leaderboard:** `GET /seasons/{season_id}/leaderboard/me`
7. **Admin closes challenge:** `PATCH /challenges/{challenge_id}/status` with `status: "closed"`
8. **Scores revealed:** League submissions now show scores
9. **Engineer spends points:** `POST /store/purchase/{item_id}`
