# AI Champions Community API

The Champions API enables developers to discover expert practitioners across SimCorp, submit knowledge content, ask for expert advice, and book time with community leaders. The system gamifies participation through points, content moderation, and automated routing.

## Authentication

All endpoints require Bearer token authentication via the `Authorization: Bearer <token>` header, obtained from the developer portal.

Admin-only endpoints require admin authentication via `require_admin_auth` middleware.

## Core Concepts

- **Champions**: Active developers nominated to share expertise (Wave 1)
- **Content**: Educational materials submitted by champions (blog posts, guides, examples) with automatic metadata classification
- **Asks**: Questions posted by developers, claimable by champions for resolution (Wave 2)
- **Bookings**: Office hour sessions scheduled between developers and champions (Wave 3)
- **Points**: Gamification ledger tracking champion contributions (integrated with League service)

## Directory & Profiles

### List Active Champions

`GET /champions`

Returns all active champions with their bio, focus areas, and office hours availability.

**Response:**
```json
[
  {
    "developer_id": "550e8400-e29b-41d4-a716-446655440000",
    "bio": "Platform infrastructure expert",
    "focus_areas": ["kubernetes", "scaling", "devops"],
    "office_hours_text": "Tue/Thu 2-4pm PT",
    "active": true
  }
]
```

### Get Champion Profile

`GET /champions/{developer_id}`

Fetch a specific champion's profile.

**Response:**
```json
{
  "developer_id": "550e8400-e29b-41d4-a716-446655440000",
  "bio": "Platform infrastructure expert",
  "focus_areas": ["kubernetes", "scaling", "devops"],
  "office_hours_text": "Tue/Thu 2-4pm PT",
  "active": true
}
```

## Content Submission & Feed

### Submit Content

`POST /champions/content`

Submit educational content (blog post, video, guide, code example, etc.). The system automatically classifies the content and ingests it into the librarian for RAG-based discovery.

**Request:**
```json
{
  "champion_id": "550e8400-e29b-41d4-a716-446655440000",
  "type": "blog_post",
  "url": "https://example.com/guide",
  "text": null,
  "optional_title": "How to scale Kubernetes in AWS"
}
```

**Notes:**
- Either `url` or `text` is required
- `type` examples: `blog_post`, `video`, `guide`, `code_example`, `tutorial`
- Text is truncated to 8000 chars before processing
- Automatic metadata includes generated title, summary, and tags
- Content is ingested into the librarian service for semantic search
- Champion earns 50 points for each submission

**Response:**
```json
{
  "id": "650e8400-e29b-41d4-a716-446655440000",
  "title": "How to scale Kubernetes in AWS",
  "summary": "A comprehensive guide to Kubernetes autoscaling…"
}
```

### List Content Feed

`GET /champions/content`

List recent content submissions from all active champions (up to 50 most recent).

**Response:**
```json
[
  {
    "id": "650e8400-e29b-41d4-a716-446655440000",
    "champion_id": "550e8400-e29b-41d4-a716-446655440000",
    "type": "blog_post",
    "submitted_at": "2026-05-28T10:30:00Z",
    "metadata": {
      "title": "How to scale Kubernetes in AWS",
      "summary": "A comprehensive guide…",
      "tags": ["kubernetes", "cloud", "scaling"]
    },
    "upvotes": 12,
    "views": 150
  }
]
```

### Upvote Content

`POST /champions/content/{contribution_id}/upvote`

Toggle upvote on a piece of content (idempotent). First upvote increments the count and grants 5 points to the champion. Subsequent calls on the same content toggle the upvote off.

**Request:**
```json
{
  "developer_id": "750e8400-e29b-41d4-a716-446655440000"
}
```

**Response:**
```json
{
  "upvoted": true,
  "upvotes": 13
}
```

### Flag Content

`POST /champions/content/{contribution_id}/flag`

Report inappropriate or spam content for moderation review.

**Request:**
```json
{
  "developer_id": "750e8400-e29b-41d4-a716-446655440000",
  "reason": "Promotional/spam content"
}
```

**Response:**
```json
{
  "id": "850e8400-e29b-41d4-a716-446655440000"
}
```

## Asks Board (Wave 2)

### Create an Ask

`POST /champions/asks`

Post a question or request that champions can claim and resolve.

**Request:**
```json
{
  "title": "How to optimize GraphQL queries?",
  "description": "We're seeing slow response times on our GraphQL endpoint. What's the best approach to profiling and optimization?",
  "created_by": "750e8400-e29b-41d4-a716-446655440000",
  "team_id": "250e8400-e29b-41d4-a716-446655440000",
  "tags": ["graphql", "performance", "backend"]
}
```

**Response:**
```json
{
  "id": "950e8400-e29b-41d4-a716-446655440000"
}
```

### List Asks

`GET /champions/asks?status={status}`

List open, claimed, or resolved asks. Status filter is optional.

**Query Parameters:**
- `status` (optional): `open`, `claimed`, `resolved_pending`, `resolved`

**Response:**
```json
[
  {
    "id": "950e8400-e29b-41d4-a716-446655440000",
    "title": "How to optimize GraphQL queries?",
    "description": "We're seeing slow response times…",
    "created_by": "750e8400-e29b-41d4-a716-446655440000",
    "team_id": "250e8400-e29b-41d4-a716-446655440000",
    "status": "open",
    "claimed_by": null,
    "resolved_at": null,
    "confirmed_at": null,
    "auto_confirm_at": null,
    "created_at": "2026-05-28T10:30:00Z",
    "tags": ["graphql", "performance", "backend"]
  }
]
```

### Claim an Ask

`POST /champions/asks/{ask_id}/claim`

Champion claims responsibility for resolving an ask (transitions ask from `open` to `claimed`).

**Request:**
```json
{
  "champion_id": "550e8400-e29b-41d4-a716-446655440000"
}
```

**Response:**
```json
{
  "ok": true,
  "id": "950e8400-e29b-41d4-a716-446655440000",
  "claimed_by": "550e8400-e29b-41d4-a716-446655440000"
}
```

**Error Responses:**
- `409 Conflict`: Ask is not in `open` status or not found

### Resolve an Ask

`POST /champions/asks/{ask_id}/resolve`

Champion marks the ask as resolved (transitions from `claimed` to `resolved_pending`). Sets 7-day auto-confirmation window.

**Request:**
```json
{
  "champion_id": "550e8400-e29b-41d4-a716-446655440000"
}
```

**Response:**
```json
{
  "ok": true,
  "id": "950e8400-e29b-41d4-a716-446655440000",
  "status": "resolved_pending"
}
```

**Error Responses:**
- `409 Conflict`: Ask not in `claimed` state or not claimed by this champion

### Confirm Ask Resolution

`POST /champions/asks/{ask_id}/confirm`

Original asker confirms that the resolution is satisfactory (transitions from `resolved_pending` to `resolved`). Champion earns 200 points.

**Request:**
```json
{
  "asker_id": "750e8400-e29b-41d4-a716-446655440000"
}
```

**Response:**
```json
{
  "ok": true,
  "id": "950e8400-e29b-41d4-a716-446655440000",
  "status": "resolved"
}
```

**Error Responses:**
- `403 Forbidden`: Only the asker can confirm
- `404 Not Found`: Ask not found
- `409 Conflict`: Ask not in `resolved_pending` state

### Smart Ask Routing (Wave 3)

`POST /champions/asks/{ask_id}/route`

Automatically suggest the top 3 champions for an ask based on focus area overlap and recent contribution activity.

**Response:**
```json
{
  "ask_id": "950e8400-e29b-41d4-a716-446655440000",
  "suggestions": [
    {
      "developer_id": "550e8400-e29b-41d4-a716-446655440000",
      "score": 0.9234,
      "focus_areas": ["graphql", "backend", "performance"]
    },
    {
      "developer_id": "660e8400-e29b-41d4-a716-446655440000",
      "score": 0.7856,
      "focus_areas": ["graphql", "database", "indexing"]
    }
  ]
}
```

**Scoring:**
- Focus area overlap weight: 60%
- Recency of contributions weight: 40%
- Contributions within 7 days = 1.0
- Contributions within 30 days = 0.6
- Contributions older than 30 days = 0.3

## Bookings (Wave 3)

### Create a Booking Request

`POST /champions/{champion_id}/book`

Request a time slot with a champion for office hours or 1-on-1 guidance.

**Request:**
```json
{
  "requested_by": "750e8400-e29b-41d4-a716-446655440000",
  "slot_text": "Tuesday 2-3pm PT",
  "topic": "GraphQL optimization deep dive",
  "team_id": "250e8400-e29b-41d4-a716-446655440000"
}
```

**Response:**
```json
{
  "booking_id": "a50e8400-e29b-41d4-a716-446655440000"
}
```

### List Champion's Bookings

`GET /champions/{champion_id}/bookings`

List all bookings (requested, confirmed, done, cancelled) for a champion.

**Response:**
```json
[
  {
    "id": "a50e8400-e29b-41d4-a716-446655440000",
    "champion_id": "550e8400-e29b-41d4-a716-446655440000",
    "requested_by": "750e8400-e29b-41d4-a716-446655440000",
    "slot_text": "Tuesday 2-3pm PT",
    "topic": "GraphQL optimization deep dive",
    "team_id": "250e8400-e29b-41d4-a716-446655440000",
    "status": "requested",
    "created_at": "2026-05-28T10:30:00Z"
  }
]
```

### Confirm Booking

`POST /champions/bookings/{booking_id}/confirm`

Champion confirms availability for the requested slot (transitions from `requested` to `confirmed`).

**Request:**
```json
{
  "champion_id": "550e8400-e29b-41d4-a716-446655440000"
}
```

**Response:**
```json
{
  "ok": true,
  "id": "a50e8400-e29b-41d4-a716-446655440000",
  "status": "confirmed"
}
```

### Mark Booking as Done

`POST /champions/bookings/{booking_id}/done`

Champion marks the session as completed (transitions from `confirmed` to `done`). Champion earns 150 points.

**Request:**
```json
{
  "champion_id": "550e8400-e29b-41d4-a716-446655440000"
}
```

**Response:**
```json
{
  "ok": true,
  "id": "a50e8400-e29b-41d4-a716-446655440000",
  "status": "done"
}
```

### Cancel Booking

`POST /champions/bookings/{booking_id}/cancel`

Cancel a booking request (works from `requested` or `confirmed` states).

**Request:**
```json
{
  "actor_id": "750e8400-e29b-41d4-a716-446655440000"
}
```

**Response:**
```json
{
  "ok": true,
  "id": "a50e8400-e29b-41d4-a716-446655440000",
  "status": "cancelled",
  "actor_id": "750e8400-e29b-41d4-a716-446655440000"
}
```

## Admin: Nomination & Retirement

### Nominate a Champion

`POST /admin/champions`

Admin nominates a developer as an AI Champion (Wave 1). Creates or updates the champion record.

**Request:**
```json
{
  "developer_id": "550e8400-e29b-41d4-a716-446655440000",
  "bio": "Platform infrastructure expert with 8 years at SimCorp",
  "focus_areas": ["kubernetes", "scaling", "devops"],
  "office_hours_text": "Tue/Thu 2-4pm PT, Zoom: [link]"
}
```

**Response:**
```json
{
  "ok": true,
  "developer_id": "550e8400-e29b-41d4-a716-446655440000"
}
```

### Retire a Champion

`DELETE /admin/champions/{developer_id}`

Deactivate a champion (soft delete: `active = FALSE`).

**Response:** `204 No Content`

## Admin: Content Moderation

### List Open Flags

`GET /admin/champions/flags`

List content flagged for moderation (requires admin auth).

**Response:**
```json
[
  {
    "id": "b50e8400-e29b-41d4-a716-446655440000",
    "contribution_id": "650e8400-e29b-41d4-a716-446655440000",
    "contribution_title": "How to scale Kubernetes in AWS",
    "flagged_by": "750e8400-e29b-41d4-a716-446655440000",
    "reason": "Promotional/spam content",
    "created_at": "2026-05-28T10:30:00Z"
  }
]
```

### Resolve a Flag

`POST /admin/champions/flags/{flag_id}/resolve`

Moderate a flag by either dismissing it or removing the content.

**Request:**
```json
{
  "action": "remove"
}
```

**Actions:**
- `dismiss`: Mark the flag as dismissed, content remains visible
- `remove`: Soft-delete the content by setting `flag_count = 999` (tombstone marker)

**Response:**
```json
{
  "ok": true,
  "id": "b50e8400-e29b-41d4-a716-446655440000",
  "action": "remove"
}
```

## Admin: Activity Dashboard

### Get Org-Wide Activity Stats

`GET /admin/champions/activity`

Aggregate statistics for the champions community (Wave 3).

**Response:**
```json
{
  "org": {
    "active_champions": 15,
    "contributions_total": 87,
    "contributions_30d": 23,
    "asks_open": 5,
    "asks_resolved_30d": 12,
    "bookings_done_30d": 18
  },
  "per_champion": [
    {
      "developer_id": "550e8400-e29b-41d4-a716-446655440000",
      "contributions": 12,
      "asks_resolved": 8,
      "bookings_done": 6,
      "points_30d": 2250
    }
  ]
}
```

## AiHelp Widget Integration

The Champions API is integrated with the AiHelp in-portal assistant for both admin and developer portals.

### Chat Intent Classification (Portal)

The developer portal's AiHelp widget uses LLM-based intent classification to route questions through multiple strategies:

1. **Show Champions Intent**: Display active champions filtered by skill area
2. **Find Content Intent**: Retrieve champion-created content from the librarian via RAG
3. **Book Champion Intent**: Resolve champion names/IDs and link to their profile
4. **Ask CTA Intent**: When no content matches, suggest creating a new ask

### Chat with AiHelp (Portal)

`POST /ai-help/chat/portal`

Chat with the AI assistant (developer context). Handles intent classification, RAG retrieval from champion content, and fallback suggestion to post an ask.

**Request:**
```json
{
  "messages": [
    {
      "role": "user",
      "content": "How do I optimize GraphQL queries?"
    }
  ],
  "context": "portal"
}
```

**Response Examples:**

Text response:
```json
{
  "type": "text",
  "reply": "GraphQL optimization involves…",
  "content": "GraphQL optimization involves…",
  "cited_sources": [
    {
      "contribution_id": "650e8400-e29b-41d4-a716-446655440000",
      "title": "How to scale Kubernetes in AWS",
      "source_url": "https://example.com/guide"
    }
  ]
}
```

Champions list:
```json
{
  "type": "champions",
  "reply": "Here are champions for graphql:",
  "content": "Here are champions for graphql:",
  "champions": [
    {
      "developer_id": "550e8400-e29b-41d4-a716-446655440000",
      "focus_areas": ["graphql", "backend"],
      "bio": "Expert in GraphQL and API design"
    }
  ]
}
```

Ask CTA (no matching content):
```json
{
  "type": "ask_cta",
  "reply": "I don't have a great answer for that yet. Want to ask a champion?",
  "content": "I don't have a great answer for that yet. Want to ask a champion?",
  "prefill": {
    "title": "How do I optimize GraphQL queries?",
    "description": "How do I optimize GraphQL queries?"
  },
  "cited_sources": []
}
```

## Points & Gamification

Champions earn points for:
- Content submission: 50 points per piece
- Content upvote: 5 points per upvote (received)
- Ask resolution: 200 points when asker confirms
- Office hours completion: 150 points per completed booking

Points are tracked in the `league_points_ledger` table and can be spent in the League store (shared gamification system).

## Error Handling

All endpoints follow REST conventions:

- `400 Bad Request`: Malformed request body
- `401 Unauthorized`: Missing or invalid auth token
- `403 Forbidden`: Insufficient permissions
- `404 Not Found`: Resource not found
- `409 Conflict`: State conflict (e.g., ask not in the expected status)
- `422 Unprocessable Entity`: Validation error (e.g., missing required field)
- `429 Too Many Requests`: Rate limit exceeded
- `5xx Server Error`: Internal error

## Base URL

All endpoints are relative to the gateway base URL:
```
https://aigw-dev.lab.cloud.scdom.net/admin
```
