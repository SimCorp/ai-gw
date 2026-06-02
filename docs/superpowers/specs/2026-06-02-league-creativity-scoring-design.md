# League Creativity Scoring

**Date:** 2026-06-02
**Status:** Approved (autonomous build under /goal) — feature #2a of the hardening sequence
**Spec + plan combined** (lighter ceremony; no pgvector, no migration).

## Problem

League submissions score on 7 dimensions; `creativity` (weight 0.05) is stubbed at a neutral `50.0`
(`services/league/app/routers/submissions.py` `_compute_scores`, and the `league_scores.creativity`
column default). Per `2026-05-26-ai-league-design.md`: *"Creativity: cosine distance of system_prompt
embedding from the centroid of all submissions for this challenge."* It is computed **after the
challenge closes**, batch, admin-triggered — to prevent gaming and batch embedding cost.

## Design

**No schema change, no pgvector.** `league_submissions.system_prompt` already exists; the
`league_scores.creativity` column already exists. We embed prompts at scoring time and compute the
centroid + cosine distance in Python.

### New pure scoring helpers (`services/league/app/scoring.py`)

```python
def centroid(vectors: list[list[float]]) -> list[float]:
    """Component-wise mean of equal-length vectors. [] -> ValueError."""

def cosine_distance(a: list[float], b: list[float]) -> float:
    """1 - cosine_similarity. Range [0, 2]. Zero-norm vector -> distance 1.0 (neutral)."""

def score_creativity(distance: float) -> float:
    """Map cosine distance to 0-100: min(100, max(0, distance * 50)).
    distance 0 (identical to crowd) -> 0; 1 (orthogonal) -> 50; 2 (opposite) -> 100."""
```

Rationale for the mapping: rewards being *different from the crowd*; an orthogonal prompt lands at
the same neutral 50 the stub used, so existing leaderboards shift minimally.

### New admin endpoint (`services/league/app/routers/submissions.py`)

`POST /challenges/{challenge_id}/score-creativity` — gated by `require_admin_auth` (already used in
`challenges.py`).

Flow:
1. 404 if the challenge does not exist.
2. Load all submissions for the challenge that have a `league_scores` row, with their `system_prompt`.
3. If fewer than 2 scored submissions → no-op: return `{"scored": 0, "reason": "need >= 2 submissions"}`
   (a centroid of one is the point itself → distance 0 for everyone, meaningless).
4. Batch-embed all `system_prompt`s in one litellm call (`POST {litellm_url}/v1/embeddings`,
   `{"model": settings.embedding_model, "input": [...]}`, bearer `litellm_master_key`; parse
   `data["data"][i]["embedding"]`, preserving order).
5. Compute the centroid.
6. For each submission: `creativity = score_creativity(cosine_distance(emb, centroid))`; update
   `league_scores.creativity`; recompute `composite = compute_composite(all_dims, weights)` using the
   challenge's season weights (look up `season.scoring_weights`, fall back to `DEFAULT_WEIGHTS`).
7. Return `{"scored": N}`.

Config: add `embedding_model: str = "text-embedding-3-small"` to `services/league/app/config.py`.

### Out of scope
- Real-time creativity at submission time (deliberately batch/post-close per spec).
- Persisting embeddings (recomputed each run; challenges are small).

## Plan (TDD)

1. **Scoring helpers** — unit tests in `services/league/tests/test_scoring.py` for `centroid`,
   `cosine_distance` (identical→0, orthogonal→1, opposite→2, zero-norm→1), `score_creativity`
   (0→0, 1→50, 2→100, clamping). Then implement in `scoring.py`. Commit.
2. **Endpoint** — tests in `services/league/tests/test_creativity.py` using the aiosqlite `db_session`
   + `app_client` fixtures and a mocked litellm embeddings response (extend the existing `mock_litellm`
   pattern): seed a challenge + ≥2 submissions + score rows; assert the endpoint embeds, updates
   `creativity` per submission, recomputes `composite`, and is admin-gated (401 without admin auth);
   assert the <2-submission no-op and the 404. Then implement the endpoint + config. Commit.
3. Full `pytest services/league` green; `ruff check`/`format` clean. Commit. PR.

## Success criteria
- `pytest services/league -v` green.
- Creativity is a real cosine-distance-from-centroid score; composite recomputed; admin-gated; batch
  single embeddings call; graceful <2-submission and 404 handling.
