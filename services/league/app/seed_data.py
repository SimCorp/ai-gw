"""High-quality demo content for AI-League.

Pure data constants — no DB or HTTP code. Imported by main.py to seed a
fresh database on startup.

Schema-aligned with services/admin/migrations/versions/0017_league_schema.py.
"""
from datetime import datetime, timezone

# Canonical scoring weights — sum to 1.0, per the design spec.
DEFAULT_WEIGHTS = {
    "quality": 0.30,
    "robustness": 0.20,
    "token_efficiency": 0.10,
    "speed": 0.10,
    "cost_efficiency": 0.10,
    "improvement_rate": 0.10,
    "creativity": 0.10,
}

ALLOWED_MODELS = ["claude-sonnet-4-6", "gpt-4o", "gpt-4o-mini"]


# ---------------------------------------------------------------------------
# Seasons — natural key is `name`
# ---------------------------------------------------------------------------
SEASONS = [
    {
        "name": "Q1 2026 — Foundations",
        "status": "closed",
        "starts_at": datetime(2026, 1, 6, 9, 0, tzinfo=timezone.utc),
        "ends_at": datetime(2026, 3, 28, 17, 0, tzinfo=timezone.utc),
        "scoring_weights": DEFAULT_WEIGHTS,
        "season_multiplier": 1.0,
    },
    {
        "name": "Q2 2026 — Agentic Workflows",
        "status": "active",
        "starts_at": datetime(2026, 4, 1, 9, 0, tzinfo=timezone.utc),
        "ends_at": datetime(2026, 6, 27, 17, 0, tzinfo=timezone.utc),
        "scoring_weights": DEFAULT_WEIGHTS,
        "season_multiplier": 1.0,
    },
    {
        "name": "Q3 2026 — Production Agents",
        "status": "upcoming",
        "starts_at": datetime(2026, 7, 1, 9, 0, tzinfo=timezone.utc),
        "ends_at": datetime(2026, 9, 26, 17, 0, tzinfo=timezone.utc),
        "scoring_weights": DEFAULT_WEIGHTS,
        "season_multiplier": 1.5,  # kickoff bonus
    },
]


# ---------------------------------------------------------------------------
# Challenges — natural key is `title`. Linked to season via `season_name`.
# Status one of: draft / active / closed.
# ---------------------------------------------------------------------------
CHALLENGES = [
    # ── Q1 2026 — closed ────────────────────────────────────────────────
    {
        "season_name": "Q1 2026 — Foundations",
        "title": "PR Summarizer",
        "goal": (
            "Given a unified diff, produce exactly three sentences capturing "
            "(1) the intent of the change, (2) the primary risk a reviewer should "
            "scrutinise, and (3) whether tests adequately cover the change. "
            "Output plain text — no markdown, no preamble."
        ),
        "status": "closed",
        "training_inputs": [
            {
                "input": "diff --git a/api/users.py b/api/users.py\n@@ -42,7 +42,8 @@ def get_user(id):\n-    return User.objects.get(id=id)\n+    user = User.objects.get(id=id)\n+    return user.serialize(include_email=True)",
                "expected_output": "Adds email exposure to the user GET endpoint by switching to a serializer call. Risk: previously private email is now returned to any authenticated caller — verify access control. No new tests are added to cover the email field.",
            },
            {
                "input": "diff --git a/billing/refund.py b/billing/refund.py\n@@ -10,3 +10,5 @@ def refund(order_id):\n     order = Order.get(order_id)\n+    if order.refunded_at:\n+        return order\n     stripe.refund(order)",
                "expected_output": "Makes the refund endpoint idempotent by short-circuiting when the order is already refunded. Risk: the early return skips audit logging that callers may expect on every invocation. No tests are updated to cover the new idempotent path.",
            },
        ],
        "hidden_test_suite": [
            {"input": "diff --git a/cache.py b/cache.py\n-    ttl = 60\n+    ttl = 3600", "expected_output": "Increases the cache TTL from 60 to 3600 seconds. Risk: stale data may persist much longer; downstream systems that assume sub-minute freshness will break. No tests are added.", "weight": 1.0},
            {"input": "diff --git a/auth/session.py b/auth/session.py\n-    HMAC_KEY = settings.SECRET\n+    HMAC_KEY = settings.SESSION_SIGNING_KEY", "expected_output": "Splits session signing from the generic SECRET into a dedicated SESSION_SIGNING_KEY. Risk: deploys that haven't set the new env var will fail to sign sessions and lock users out. No tests are added.", "weight": 1.5},
            {"input": "diff --git a/util/retry.py b/util/retry.py\n+def retry(fn, attempts=3):\n+    for i in range(attempts):\n+        try: return fn()\n+        except: pass", "expected_output": "Adds a bare retry helper that swallows all exceptions across three attempts. Risk: silent failure mode — original exceptions are discarded so callers cannot diagnose failures. No tests are added for the new helper.", "weight": 1.0},
        ],
    },
    {
        "season_name": "Q1 2026 — Foundations",
        "title": "Log Triage Agent",
        "goal": (
            "Classify the given stack trace or log excerpt into one of "
            "{infrastructure, application_bug, third_party, user_error}. "
            "Respond as a single JSON object: "
            '{"category": "...", "confidence": 0.0-1.0, "rationale": "one sentence"}.'
        ),
        "status": "closed",
        "training_inputs": [
            {
                "input": "ConnectionError: HTTPSConnectionPool(host='api.stripe.com', port=443): Max retries exceeded with url: /v1/charges (Caused by NewConnectionError: timed out)",
                "expected_output": '{"category": "third_party", "confidence": 0.9, "rationale": "Outbound Stripe API call timed out — failure is in the external provider, not our code."}',
            },
            {
                "input": "ValueError: invalid literal for int() with base 10: 'abc'\n  File 'handlers.py', line 22, in parse_age\n    return int(request.GET['age'])",
                "expected_output": '{"category": "user_error", "confidence": 0.85, "rationale": "Caller submitted a non-numeric value where an integer was required — input validation should reject this before parsing."}',
            },
        ],
        "hidden_test_suite": [
            {"input": "psycopg2.OperationalError: FATAL: remaining connection slots are reserved for non-replication superuser connections", "expected_output": '{"category": "infrastructure", "confidence": 0.95, "rationale": "Postgres connection pool exhausted — database tier capacity issue, not application logic."}', "weight": 1.0},
            {"input": "AttributeError: 'NoneType' object has no attribute 'split'\n  File 'parser.py', line 87, in tokenize\n    parts = self.cache.get(key).split(',')", "expected_output": '{"category": "application_bug", "confidence": 0.9, "rationale": "Cache returned None and the code path did not guard against the miss — a programming error in our own module."}', "weight": 1.2},
            {"input": "boto3.exceptions.S3UploadFailedError: An error occurred (AccessDenied) when calling the PutObject operation: Access Denied", "expected_output": '{"category": "infrastructure", "confidence": 0.8, "rationale": "IAM policy denies the upload — configuration/permissions issue in the cloud environment."}', "weight": 1.0},
        ],
    },
    {
        "season_name": "Q1 2026 — Foundations",
        "title": "SQL Optimizer",
        "goal": (
            "Rewrite the given Postgres query so it preserves the original result set "
            "but improves on the EXPLAIN plan. Use only standard SQL. Return only the "
            "rewritten query — no explanation, no markdown fences."
        ),
        "status": "closed",
        "training_inputs": [
            {
                "input": "SELECT * FROM orders WHERE customer_id IN (SELECT id FROM customers WHERE country = 'DK');\n-- Plan: Seq Scan on orders + Hash Semi Join\n-- Indexes: orders(customer_id), customers(country)",
                "expected_output": "SELECT o.* FROM orders o JOIN customers c ON c.id = o.customer_id WHERE c.country = 'DK';",
            },
        ],
        "hidden_test_suite": [
            {"input": "SELECT u.name, (SELECT COUNT(*) FROM posts p WHERE p.user_id = u.id) AS post_count FROM users u;\n-- Plan: nested loop, COUNT subquery per user row.\n-- Indexes: posts(user_id)", "expected_output": "SELECT u.name, COALESCE(p.post_count, 0) AS post_count FROM users u LEFT JOIN (SELECT user_id, COUNT(*) AS post_count FROM posts GROUP BY user_id) p ON p.user_id = u.id;", "weight": 1.5},
            {"input": "SELECT * FROM events WHERE created_at::date = '2026-01-15';\n-- Plan: Seq Scan, function on indexed column.\n-- Indexes: events(created_at)", "expected_output": "SELECT * FROM events WHERE created_at >= '2026-01-15' AND created_at < '2026-01-16';", "weight": 1.0},
        ],
    },

    # ── Q2 2026 — active ────────────────────────────────────────────────
    {
        "season_name": "Q2 2026 — Agentic Workflows",
        "title": "Code Review Bot",
        "goal": (
            "Review the given Python function for correctness, style, and security "
            'issues. Respond as JSON: {"issues": [{"severity": "low|medium|high", '
            '"line": <int>, "message": "<one sentence>"}]}. Empty list if clean.'
        ),
        "status": "active",
        "training_inputs": [
            {
                "input": "def get_user(id):\n    q = f\"SELECT * FROM users WHERE id={id}\"\n    return db.execute(q).fetchone()",
                "expected_output": '{"issues": [{"severity": "high", "line": 2, "message": "SQL injection — the id parameter is interpolated directly into the query string; use parameterised execution instead."}]}',
            },
            {
                "input": "def calculate_total(items):\n    total = 0\n    for item in items:\n        total = total + item.price\n    return total",
                "expected_output": '{"issues": [{"severity": "low", "line": 4, "message": "Prefer `sum(item.price for item in items)` or `total += item.price` for idiomatic Python."}]}',
            },
        ],
        "hidden_test_suite": [
            {"input": "def fetch(url):\n    import urllib.request\n    return urllib.request.urlopen(url).read()", "expected_output": '{"issues": [{"severity": "high", "line": 3, "message": "Untrusted URL fetched without scheme or host validation — SSRF risk."}, {"severity": "medium", "line": 3, "message": "No timeout — call can hang indefinitely."}]}', "weight": 1.5},
            {"input": "def store_password(user, pwd):\n    user.password = pwd\n    user.save()", "expected_output": '{"issues": [{"severity": "high", "line": 2, "message": "Passwords must be hashed (e.g. argon2/bcrypt) before storage — never persist plaintext."}]}', "weight": 1.5},
            {"input": "def divide(a, b):\n    return a / b", "expected_output": '{"issues": [{"severity": "medium", "line": 2, "message": "No guard against b == 0 — will raise ZeroDivisionError at runtime."}]}', "weight": 1.0},
        ],
    },
    {
        "season_name": "Q2 2026 — Agentic Workflows",
        "title": "Incident First Responder",
        "goal": (
            "Given an alert payload (alert name, metric, timestamp, affected service), "
            "propose three prioritised diagnostic actions and one escalation rule. "
            'Respond as JSON: {"actions": ["...", "...", "..."], "escalate_if": "..."}.'
        ),
        "status": "active",
        "training_inputs": [
            {
                "input": "Alert: api_p99_latency_breach\nMetric: api.latency.p99 = 4200ms (threshold 1500ms)\nService: payments-api\nTime: 2026-04-12 14:23 UTC",
                "expected_output": '{"actions": ["Check payments-api pod CPU and memory in Grafana for the last 30m", "Inspect upstream provider (Stripe) status page for incidents", "Tail recent error logs filtered by p99>3s requests for endpoint breakdown"], "escalate_if": "p99 remains above 3000ms for 15+ minutes after the first action"}',
            },
        ],
        "hidden_test_suite": [
            {"input": "Alert: db_connection_pool_exhausted\nMetric: postgres.connections.idle = 0 / max 100\nService: orders-api\nTime: 2026-04-12 02:11 UTC", "expected_output": '{"actions": ["Identify which queries are holding connections via pg_stat_activity", "Check for long-running transactions or deadlocks", "Restart the highest-CPU orders-api pod to release connections if no transaction is critical"], "escalate_if": "pool stays at 0 idle for 10+ minutes or active queries exceed 30s"}', "weight": 1.0},
            {"input": "Alert: error_rate_spike\nMetric: app.http.5xx.rate = 12% (threshold 1%)\nService: checkout-api\nTime: 2026-04-12 19:45 UTC", "expected_output": '{"actions": ["Group recent 5xx by error type to identify dominant exception", "Diff most recent deploy commit against last known-good version", "Roll back checkout-api to previous deployment if errors trace to a code change"], "escalate_if": "error rate stays above 5% after rollback or affects payment confirmations"}', "weight": 1.2},
            {"input": "Alert: disk_usage_critical\nMetric: host.disk.used = 96% (threshold 85%)\nService: log-aggregator-1\nTime: 2026-04-12 06:30 UTC", "expected_output": '{"actions": ["Run du -h /var/log | sort -h to find largest contributors", "Check whether log rotation cron is failing", "Expire oldest log files older than retention policy"], "escalate_if": "disk reaches 99% before mitigation or rotation cannot be restored"}', "weight": 1.0},
        ],
    },
    {
        "season_name": "Q2 2026 — Agentic Workflows",
        "title": "API Contract Diff",
        "goal": (
            "Given two OpenAPI specs (old and new), classify the differences into four "
            'buckets. Respond as JSON: {"added": [...], "removed": [...], '
            '"breaking": [...], "semantic": [...]} where each entry is a one-line '
            "description. Breaking = anything an existing client could fail on."
        ),
        "status": "active",
        "training_inputs": [
            {
                "input": "OLD: GET /users {id: int, name: string}\nNEW: GET /users {id: int, name: string, email: string}",
                "expected_output": '{"added": ["GET /users response now includes email field"], "removed": [], "breaking": [], "semantic": []}',
            },
            {
                "input": "OLD: POST /orders body {item_id: int, quantity: int}\nNEW: POST /orders body {item_id: int, quantity: int, currency: string (required)}",
                "expected_output": '{"added": ["POST /orders accepts currency"], "removed": [], "breaking": ["POST /orders currency field is required — existing callers will receive 400"], "semantic": []}',
            },
        ],
        "hidden_test_suite": [
            {"input": "OLD: GET /accounts/{id} returns 200 with {balance: number}\nNEW: GET /accounts/{id} returns 200 with {balance: string}", "expected_output": '{"added": [], "removed": [], "breaking": ["GET /accounts/{id} balance type changed from number to string — clients parsing it as a number will break"], "semantic": []}', "weight": 1.5},
            {"input": "OLD: DELETE /sessions/{id} returns 204\nNEW: (endpoint removed)", "expected_output": '{"added": [], "removed": ["DELETE /sessions/{id}"], "breaking": ["DELETE /sessions/{id} no longer exists — clients calling it will receive 404"], "semantic": []}', "weight": 1.0},
            {"input": "OLD: GET /search?q=string (returns up to 100 results)\nNEW: GET /search?q=string (returns up to 25 results, pagination required for more)", "expected_output": '{"added": [], "removed": [], "breaking": [], "semantic": ["GET /search default page size reduced from 100 to 25 — clients relying on the larger page may miss results"]}', "weight": 1.2},
        ],
    },

    # ── Q3 2026 — upcoming (draft) ──────────────────────────────────────
    {
        "season_name": "Q3 2026 — Production Agents",
        "title": "Refactor Strategist",
        "goal": (
            "Given a module's file tree, dependency graph, and refactor objective, "
            "produce an ordered step-by-step plan. Each step states (a) what to do, "
            "(b) which files it touches, (c) the verification before moving on."
        ),
        "status": "draft",
        "training_inputs": [
            {
                "input": "Files: payments/{api.py, stripe.py, validators.py, tests/test_payments.py}\nGraph: api → stripe, api → validators, tests → api\nObjective: extract a Provider interface so we can plug in Adyen alongside Stripe.",
                "expected_output": "1. Define abstract Provider class with charge/refund methods (new file payments/provider.py). Verify by running existing tests — they must still pass.\n2. Make stripe.py implement Provider (no behaviour change). Verify with same test suite.\n3. Update api.py to receive a Provider instance via dependency injection. Verify tests pass with Stripe injected.\n4. Add AdyenProvider stub (raises NotImplementedError). Verify isinstance check works.\n5. Add Adyen integration tests skipped by default. Verify pytest collection succeeds.",
            },
        ],
        "hidden_test_suite": [
            {"input": "Files: search/{index.py, query.py, ranking.py, embeddings.py}\nGraph: query → index, query → ranking, ranking → embeddings\nObjective: replace the in-memory index with a Postgres+pgvector backend.", "expected_output": "1. Add IndexBackend protocol with add/search methods. Verify imports compile.\n2. Wrap current in-memory implementation as InMemoryBackend(IndexBackend). Verify existing tests pass.\n3. Add PgVectorBackend with same interface — empty stub. Verify it can be instantiated.\n4. Implement PgVectorBackend.add against a migration that creates the vectors table. Verify single-row insert succeeds in a test.\n5. Implement PgVectorBackend.search with cosine distance. Verify a top-5 result test passes.\n6. Wire query.py to read the backend from config. Verify both backends pass an end-to-end search test.", "weight": 1.5},
        ],
    },
    {
        "season_name": "Q3 2026 — Production Agents",
        "title": "Test Generator",
        "goal": (
            "Given a function signature, a docstring, and one example input/output, "
            "generate a property-based test (pytest + hypothesis) that catches a "
            "planted bug in a buggy reference implementation. Output the test only."
        ),
        "status": "draft",
        "training_inputs": [
            {
                "input": "def merge_intervals(intervals: list[tuple[int,int]]) -> list[tuple[int,int]]:\n    \"\"\"Merge overlapping intervals. Example: [(1,3),(2,4)] -> [(1,4)]\"\"\"",
                "expected_output": "from hypothesis import given, strategies as st\n\n@given(st.lists(st.tuples(st.integers(0, 100), st.integers(0, 100))))\ndef test_merge_intervals_is_idempotent_and_non_overlapping(raw):\n    intervals = [(min(a,b), max(a,b)) for a,b in raw]\n    merged = merge_intervals(intervals)\n    assert merge_intervals(merged) == merged\n    for (a1,b1), (a2,b2) in zip(merged, merged[1:]):\n        assert b1 < a2, 'merged intervals must be disjoint and ordered'",
            },
        ],
        "hidden_test_suite": [
            {"input": "def serialize(obj: dict) -> str:\n    \"\"\"Round-trippable JSON serialization. Example: {'a':1} -> '{\"a\":1}' and deserialize(serialize(x)) == x\"\"\"", "expected_output": "from hypothesis import given, strategies as st\n\n@given(st.dictionaries(st.text(min_size=1, max_size=10), st.one_of(st.integers(), st.text(), st.booleans())))\ndef test_serialize_roundtrip(obj):\n    assert deserialize(serialize(obj)) == obj", "weight": 1.5},
        ],
    },
]


# ---------------------------------------------------------------------------
# Store items — natural key is `name`.
# `exclusive_season_name` is resolved to UUID at seed time; non-null items are
# not purchasable (granted only to top-N finishers).
# ---------------------------------------------------------------------------
STORE_ITEMS = [
    # Badges
    {"name": "First Submission", "type": "badge", "point_cost": 0, "asset_url": ""},
    {"name": "Bronze Submitter", "type": "badge", "point_cost": 200, "asset_url": ""},
    {"name": "Silver Submitter", "type": "badge", "point_cost": 800, "asset_url": ""},
    {"name": "Gold Submitter", "type": "badge", "point_cost": 3000, "asset_url": ""},
    # Card borders
    {"name": "Pixel Border", "type": "card_border", "point_cost": 500, "asset_url": ""},
    {"name": "Aurora Border", "type": "card_border", "point_cost": 1500, "asset_url": ""},
    # Avatar frames
    {"name": "Carbon Avatar Frame", "type": "avatar_frame", "point_cost": 1000, "asset_url": ""},
    {"name": "Plasma Avatar Frame", "type": "avatar_frame", "point_cost": 2500, "asset_url": ""},
    # Exclusive titles — not purchasable, granted to top finishers
    {
        "name": "Foundations Finalist",
        "type": "title",
        "point_cost": 0,
        "asset_url": "",
        "exclusive_season_name": "Q1 2026 — Foundations",
        "exclusive_top_n": 10,
    },
    {
        "name": "Agentic Architect",
        "type": "title",
        "point_cost": 0,
        "asset_url": "",
        "exclusive_season_name": "Q2 2026 — Agentic Workflows",
        "exclusive_top_n": 3,
    },
]


# ---------------------------------------------------------------------------
# Proposals — natural key is `title`.
# All proposed by dev@simcorp.com (seeded by admin service startup).
# Status one of: proposed / approved / rejected.
# ---------------------------------------------------------------------------
PROPOSALS = [
    {
        "title": "Test Flakiness Detective",
        "goal": "Given a CI test history (passes, failures, environments), classify each test as {stable, flaky, broken} and explain the signal driving the call.",
        "notes": "We've been chasing flaky pytest specs for two quarters — would be great to have an agent that catches them before they waste reviewer time.",
        "status": "proposed",
    },
    {
        "title": "Doc Translator Agent",
        "goal": "Translate internal English-language design docs to Danish, preserving code snippets verbatim and flagging any phrases that lack a natural Danish technical equivalent.",
        "notes": "Half of platform is in Copenhagen; we keep informally translating in Slack.",
        "status": "proposed",
    },
    {
        "title": "Slack Thread Summarizer",
        "goal": "Given a Slack thread (JSON), produce a 5-bullet summary capturing the decision, the dissent, the owner, the deadline, and any open questions.",
        "notes": "Want this for on-call handoff threads in particular.",
        "status": "approved",
        "reviewer_notes": "Great fit for Q3 — assigned to platform team for test-suite design.",
    },
    {
        "title": "Auto-PR Merger",
        "goal": "Detect PRs that are safe to auto-merge (no breaking changes, all checks green, no controversial reviewers) and merge them.",
        "notes": "Cut down our merge backlog.",
        "status": "rejected",
        "reviewer_notes": "Out of scope — agents writing to main require a security/governance review first. Reconsider once we have a guardrails layer.",
    },
]
