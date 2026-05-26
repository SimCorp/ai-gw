# services/league/app/routers/submissions.py
import hashlib
import json
import time
import uuid
from uuid import UUID

import httpx
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import require_dev_auth
from app.config import settings
from app.db import get_session
from app.scoring import (
    DEFAULT_WEIGHTS,
    compute_composite,
    score_efficiency,
    score_improvement_rate,
    score_quality_exact,
    score_robustness,
)

router = APIRouter(tags=["submissions"])


class SubmissionCreate(BaseModel):
    mode: str  # "training" or "league"
    system_prompt: str
    tool_config: list[dict] = []


async def _call_litellm(system_prompt: str, user_input: str, model: str, max_tokens: int) -> dict:
    """Call litellm and return {output, tokens, latency_ms, cost_usd}."""
    start = time.monotonic()
    async with httpx.AsyncClient(timeout=60.0) as client:
        resp = await client.post(
            f"{settings.litellm_url}/v1/chat/completions",
            headers={"Authorization": f"Bearer {settings.litellm_master_key}"},
            json={
                "model": model,
                "max_tokens": max_tokens,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_input},
                ],
            },
        )
        resp.raise_for_status()
    data = resp.json()
    latency_ms = (time.monotonic() - start) * 1000
    return {
        "output": data["choices"][0]["message"]["content"],
        "tokens": data.get("usage", {}).get("total_tokens", 0),
        "latency_ms": latency_ms,
        "cost_usd": data.get("usage", {}).get("cost", 0.0),
    }


async def _run_test_suite(
    system_prompt: str,
    test_cases: list[dict],
    model: str,
    max_tokens: int,
) -> list[dict]:
    results = []
    for case in test_cases:
        try:
            run = await _call_litellm(system_prompt, case["input"], model, max_tokens)
            results.append({
                "input": case["input"],
                "expected": case["expected"],
                "actual": run["output"].strip(),
                "tokens": run["tokens"],
                "latency_ms": run["latency_ms"],
                "cost_usd": run.get("cost_usd", 0.0),
                "weight": case.get("weight", 1.0),
            })
        except Exception as exc:
            results.append({
                "input": case["input"],
                "expected": case["expected"],
                "actual": "",
                "tokens": 0,
                "latency_ms": 0,
                "cost_usd": 0.0,
                "weight": case.get("weight", 1.0),
                "error": str(exc),
            })
    return results


def _compute_scores(
    run_results: list[dict],
    prior_composite: float | None,
    season_weights: dict,
) -> dict[str, float]:
    total_tokens = sum(r["tokens"] for r in run_results)
    total_cost = sum(r["cost_usd"] for r in run_results)
    avg_latency = sum(r["latency_ms"] for r in run_results) / max(len(run_results), 1)

    quality = score_quality_exact(run_results)
    robustness = score_robustness(
        passed=sum(1 for r in run_results if r.get("actual", "").strip() == r.get("expected", "").strip()),
        total=len(run_results),
    )
    token_efficiency = score_efficiency(actual=total_tokens, median=500)
    speed = score_efficiency(actual=avg_latency, median=300.0)
    cost_efficiency = score_efficiency(actual=total_cost * 10000, median=5.0)

    weights = season_weights or dict(DEFAULT_WEIGHTS)
    partial_scores = {
        "quality": quality,
        "robustness": robustness,
        "token_efficiency": token_efficiency,
        "speed": speed,
        "cost_efficiency": cost_efficiency,
        "improvement_rate": 50.0,
        "creativity": 50.0,
    }
    composite = compute_composite(partial_scores, weights)
    partial_scores["improvement_rate"] = score_improvement_rate(composite, prior_composite)
    composite = compute_composite(partial_scores, weights)
    return {**partial_scores, "composite": composite}


@router.post("/challenges/{challenge_id}/submit")
async def submit(
    challenge_id: UUID,
    body: SubmissionCreate,
    session: AsyncSession = Depends(get_session),
    user=Depends(require_dev_auth),
):
    if body.mode not in ("training", "league"):
        raise HTTPException(status_code=422, detail="mode must be 'training' or 'league'")

    row = (await session.execute(text("""
        SELECT c.*, s.scoring_weights, s.season_multiplier
        FROM league_challenges c
        JOIN league_seasons s ON s.id = c.season_id
        WHERE c.id = :id
    """), {"id": str(challenge_id)})).mappings().one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail="Challenge not found")
    if row["status"] != "active":
        raise HTTPException(status_code=409, detail="Challenge is not active")

    if body.mode == "league":
        attempt_count = (await session.execute(text("""
            SELECT COUNT(*) FROM league_submissions
            WHERE challenge_id = :cid AND engineer_id = :uid AND mode = 'league'
        """), {"cid": str(challenge_id), "uid": user["user_id"]})).scalar()
        if attempt_count >= row["max_league_attempts"]:
            raise HTTPException(status_code=429, detail=f"League attempt limit of {row['max_league_attempts']} reached")

    prior_row = (await session.execute(text("""
        SELECT MAX(sc.composite) AS best
        FROM league_submissions sub
        JOIN league_scores sc ON sc.submission_id = sub.id
        WHERE sub.challenge_id = :cid AND sub.engineer_id = :uid
    """), {"cid": str(challenge_id), "uid": user["user_id"]})).mappings().one_or_none()
    prior_best = float(prior_row["best"]) if prior_row and prior_row["best"] is not None else None

    test_cases = row["hidden_test_suite"] if body.mode == "league" else row["training_inputs"]
    attempt_num = (await session.execute(text("""
        SELECT COALESCE(MAX(attempt_number), 0) + 1
        FROM league_submissions
        WHERE challenge_id = :cid AND engineer_id = :uid AND mode = :mode
    """), {"cid": str(challenge_id), "uid": user["user_id"], "mode": body.mode})).scalar()

    model = row["allowed_models"][0]
    run_results = await _run_test_suite(body.system_prompt, test_cases, model, row["max_tokens_budget"])

    season_weights = row["scoring_weights"] or dict(DEFAULT_WEIGHTS)
    scores = _compute_scores(run_results, prior_best, season_weights)

    prompt_hash = hashlib.sha256(body.system_prompt.encode()).hexdigest()
    sub_result = await session.execute(text("""
        INSERT INTO league_submissions
          (challenge_id, engineer_id, mode, system_prompt, tool_config, attempt_number, run_results, prompt_hash)
        VALUES
          (:cid, :uid, :mode, :prompt, CAST(:tools AS jsonb), :attempt, CAST(:results AS jsonb), :hash)
        RETURNING id
    """), {
        "cid": str(challenge_id),
        "uid": user["user_id"],
        "mode": body.mode,
        "prompt": body.system_prompt,
        "tools": json.dumps(body.tool_config),
        "attempt": attempt_num,
        "results": json.dumps(run_results),
        "hash": prompt_hash,
    })
    submission_id = sub_result.scalar()

    await session.execute(text("""
        INSERT INTO league_scores
          (submission_id, quality, robustness, token_efficiency, speed,
           cost_efficiency, improvement_rate, creativity, composite)
        VALUES
          (:sid, :quality, :robustness, :token_efficiency, :speed,
           :cost_efficiency, :improvement_rate, :creativity, :composite)
    """), {"sid": str(submission_id), **{k: round(v, 2) for k, v in scores.items()}})

    if body.mode == "league":
        season_id = str(row["season_id"])
        multiplier = float(row["season_multiplier"])
        pts = int(scores["composite"] * multiplier)
        await session.execute(text("""
            INSERT INTO league_leaderboard (season_id, engineer_id, composite_score, points_earned, updated_at)
            VALUES (:sid, :uid, :score, :pts, NOW())
            ON CONFLICT (season_id, engineer_id) DO UPDATE
              SET composite_score = GREATEST(league_leaderboard.composite_score, EXCLUDED.composite_score),
                  points_earned = GREATEST(league_leaderboard.points_earned, EXCLUDED.points_earned),
                  updated_at = NOW()
        """), {"sid": season_id, "uid": user["user_id"], "score": round(scores["composite"], 2), "pts": pts})

        if prior_best is None or scores["composite"] > prior_best:
            delta = pts - (int(prior_best * multiplier) if prior_best else 0)
            if delta > 0:
                await session.execute(text("""
                    INSERT INTO league_points_ledger (engineer_id, delta, reason, ref_id)
                    VALUES (:uid, :delta, 'league_submission_reward', :ref)
                """), {"uid": user["user_id"], "delta": delta, "ref": str(submission_id)})

    if body.mode == "training":
        await session.execute(text("""
            INSERT INTO league_points_ledger (engineer_id, delta, reason, ref_id)
            VALUES (:uid, 50, 'training_xp_reward', :ref)
        """), {"uid": user["user_id"], "ref": str(submission_id)})

    await session.commit()

    if body.mode == "training":
        return {"submission_id": str(submission_id), "scores": scores, "run_results": run_results}
    else:
        return {
            "submission_id": str(submission_id),
            "message": "Submission received. Scores will be revealed when the challenge closes.",
        }
