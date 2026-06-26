"""Auto-Drive: feedback-based model routing.

Tracks per-model stats in Redis using a 5-minute rolling window (minute-bucketed
keys) and computes a composite score to select the best-performing candidate.

Scoring formula:
  score = (cache_hit_rate * 0.4) + (1 / (avg_latency_ms / 1000 + 1) * 0.4) + ((1 - error_rate) * 0.2)

Redis key scheme (per-minute bucket, TTL 360 s):
  autoroute:stats:{model}:{metric}:m{epoch_minute}
"""

from __future__ import annotations

import logging
import time

# Intents that require strong reasoning — only route to frontier/complex models.
# All other intents (question, documentation, code_review, general, …) are eligible
# for cheaper model substitution.
_COMPLEX_INTENTS = frozenset({"code_generation", "debugging", "refactoring", "testing"})

_log = logging.getLogger(__name__)

_WINDOW_SECONDS = 300  # 5-minute rolling window
_BUCKET_TTL = 360  # bucket expiry — a bit longer than the window
_EXPLORATION_SCORE = 0.5  # score assigned to models with zero request data


def _epoch_minute() -> int:
    return int(time.time()) // 60


def _bucket_keys(model: str, metric: str) -> list[str]:
    """Return the 5 minute-bucket keys in the current window."""
    now = _epoch_minute()
    return [f"autoroute:stats:{model}:{metric}:m{now - i}" for i in range(5)]


async def record_request(
    redis,
    model: str,
    latency_ms: float,
    cache_hit: bool,
    error: bool,
) -> None:
    """Increment per-minute bucket counters for *model*.

    Safe to call fire-and-forget; all Redis errors are swallowed so autorouting
    never blocks or breaks the critical request path.
    """
    try:
        bucket = _epoch_minute()
        pipe = redis.pipeline()
        base = f"autoroute:stats:{model}"
        pipe.incr(f"{base}:requests:m{bucket}")
        pipe.expire(f"{base}:requests:m{bucket}", _BUCKET_TTL)
        if cache_hit:
            pipe.incr(f"{base}:hits:m{bucket}")
            pipe.expire(f"{base}:hits:m{bucket}", _BUCKET_TTL)
        pipe.incrbyfloat(f"{base}:latency_sum:m{bucket}", latency_ms)
        pipe.expire(f"{base}:latency_sum:m{bucket}", _BUCKET_TTL)
        if error:
            pipe.incr(f"{base}:errors:m{bucket}")
            pipe.expire(f"{base}:errors:m{bucket}", _BUCKET_TTL)
        await pipe.execute()
    except Exception as exc:
        _log.debug("autoroute record_request failed (ignored): %s", exc)


async def _sum_buckets(redis, model: str, metric: str) -> float:
    """Sum values across the 5 most recent minute-buckets."""
    keys = _bucket_keys(model, metric)
    try:
        values = await redis.mget(*keys)
        return sum(float(v) for v in values if v is not None)
    except Exception:
        return 0.0


async def get_model_scores(redis) -> dict[str, float]:
    """Return a score dict for all models that have recorded data.

    Higher score == better. Models with no traffic get *_EXPLORATION_SCORE* so
    they receive occasional requests and we avoid locking in on the leader.
    """
    # Discover tracked models via key scan
    try:
        cursor = b"0"
        model_names: set[str] = set()
        while True:
            cursor, keys = await redis.scan(
                cursor, match="autoroute:stats:*:requests:m*", count=200
            )
            for k in keys:
                # Pattern: autoroute:stats:{model}:requests:m{minute}
                parts = k.decode() if isinstance(k, bytes) else k
                # strip prefix "autoroute:stats:" and suffix ":requests:m{N}"
                inner = parts[len("autoroute:stats:") :]
                model_part = inner.rsplit(":requests:", 1)[0]
                model_names.add(model_part)
            if cursor == b"0" or cursor == 0:
                break
    except Exception as exc:
        _log.debug("autoroute model scan failed: %s", exc)
        return {}

    scores: dict[str, float] = {}
    for model in model_names:
        requests = await _sum_buckets(redis, model, "requests")
        if requests == 0:
            scores[model] = _EXPLORATION_SCORE
            continue
        hits = await _sum_buckets(redis, model, "hits")
        latency_sum = await _sum_buckets(redis, model, "latency_sum")
        errors = await _sum_buckets(redis, model, "errors")

        cache_hit_rate = hits / requests
        avg_latency_ms = latency_sum / requests if requests > 0 else 1000.0
        error_rate = errors / requests

        score = (
            cache_hit_rate * 0.4
            + (1.0 / (avg_latency_ms / 1000.0 + 1.0)) * 0.4
            + (1.0 - error_rate) * 0.2
        )
        scores[model] = round(score, 4)

    return scores


async def select_best_model(redis, candidates: list[str]) -> str:
    """Return the candidate with the highest score.

    Falls back to the first candidate if Redis is unavailable or no scores are
    available.
    """
    if not candidates:
        raise ValueError("candidates list must not be empty")

    try:
        scores = await get_model_scores(redis)
        best = max(candidates, key=lambda m: scores.get(m, _EXPLORATION_SCORE))
        return best
    except Exception as exc:
        _log.warning("autoroute select_best_model failed, using first candidate: %s", exc)
        return candidates[0]


async def select_model_for_intent(
    redis,
    intent: str,
    all_candidates: list[str],
    complex_models: list[str],
) -> str:
    """Select the best model for *intent*, restricting to *complex_models* for demanding tasks.

    Simple intents (questions, documentation, code review) may use any candidate
    from *all_candidates*.  Complex intents (code generation, debugging, refactoring,
    testing) are restricted to *complex_models* so quality is preserved.  If no
    *complex_models* appear in *all_candidates*, falls back to the full list.
    """
    if intent in _COMPLEX_INTENTS and complex_models:
        complex_set = set(complex_models)
        eligible = [m for m in all_candidates if m in complex_set]
        if not eligible:
            eligible = all_candidates
    else:
        eligible = all_candidates
    return await select_best_model(redis, eligible)
