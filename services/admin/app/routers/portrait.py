"""Developer usage portrait — AI-generated weekly illustration from usage telemetry."""

import base64
import logging
from datetime import date, timedelta

import httpx
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db import get_session
from app.routers.dev_auth import _get_current_developer

log = logging.getLogger(__name__)

router = APIRouter(prefix="/portrait", tags=["portrait"])

_CREATURE_MAP: dict[str, tuple[str, str]] = {
    "claude-sonnet-4-6": ("a songbird", "🐦"),
    "claude-opus-4-7": ("an owl", "🦉"),
    "claude-haiku-4-5": ("a hummingbird", "🦜"),
    "github-gpt-4o": ("a raven", "🐦‍⬛"),
    "gemini-1.5-pro": ("a peacock", "🦚"),
}
_DEFAULT_CREATURE: tuple[str, str] = ("a heron", "🦢")

_HOUR_BUCKETS = [
    (range(0, 7), "moonlit scene", "peak usage in late-night hours"),
    (range(7, 12), "dawn light", "peak usage in morning hours"),
    (range(12, 18), "afternoon light", "peak usage in afternoon hours"),
    (range(18, 24), "dusk", "peak usage in evening hours"),
]


def _build_scene(stats: dict) -> tuple[str, dict]:
    """Assemble a DALL-E prompt and explanation from usage telemetry.

    Args:
        stats: dict with keys top_model, cache_hit_pct, tool_ratio, peak_hour,
               request_count. Values may be None if the developer has no usage.

    Returns:
        (prompt_str, scene_data_dict) where scene_data has keys:
        creature, atmosphere, machinery, time, scale
    """
    top_model: str | None = stats.get("top_model")
    cache_hit_pct: float = float(stats.get("cache_hit_pct") or 0.0)
    tool_ratio: float = float(stats.get("tool_ratio") or 0.0)
    peak_hour: int = int(stats.get("peak_hour") or 12)
    request_count: int = int(stats.get("request_count") or 0)

    creature_name, creature_emoji = _CREATURE_MAP.get(top_model or "", _DEFAULT_CREATURE)
    creature_reason = f"Most-used model: {top_model}" if top_model else "Default"

    atmosphere = "clear morning light" if cache_hit_pct >= 0.5 else "dense fog"
    atmosphere_reason = f"Cache hit rate: {cache_hit_pct:.0%}"

    if tool_ratio >= 0.3:
        machinery = ", clockwork gears and instruments nearby"
        machinery_name = "clockwork gears"
        machinery_reason = f"High tool-call usage ({tool_ratio:.0%} of requests used tools)"
    else:
        machinery = ""
        machinery_name = "none"
        machinery_reason = f"Low tool-call usage ({tool_ratio:.0%} of requests used tools)"

    time_name, time_reason = "afternoon light", "peak usage in afternoon hours"
    for hour_range, t_name, t_reason in _HOUR_BUCKETS:
        if peak_hour in hour_range:
            time_name, time_reason = t_name, t_reason
            break

    if request_count >= 100:
        scale = "a dense ancient forest"
        scale_reason = f"{request_count} requests this week"
    elif request_count >= 20:
        scale = "a forest clearing"
        scale_reason = f"{request_count} requests this week"
    else:
        scale = "a single ancient tree"
        scale_reason = f"{request_count} requests this week"

    prompt = (
        f"{scale}, {creature_name} perched{machinery}, {atmosphere}, "
        f"{time_name}, fine-line ink drawing, botanical illustration, "
        f"monochromatic, high detail"
    )

    scene_data = {
        "creature": {"name": creature_name, "emoji": creature_emoji, "reason": creature_reason},
        "atmosphere": {
            "name": atmosphere,
            "emoji": "🌫" if "fog" in atmosphere else "☀️",
            "reason": atmosphere_reason,
        },
        "machinery": {"name": machinery_name, "emoji": "⚙️", "reason": machinery_reason},
        "time": {
            "name": time_name,
            "emoji": "🌙" if "moonlit" in time_name else "⏰",
            "reason": time_reason,
        },
        "scale": {"name": scale, "emoji": "🌲", "reason": scale_reason},
    }
    return prompt, scene_data


async def _fetch_usage_stats(session: AsyncSession, developer_id: str) -> dict:
    row = (
        (
            await session.execute(
                text("""
                SELECT
                    mode() WITHIN GROUP (ORDER BY model)                           AS top_model,
                    AVG(cache_hit::int)                                            AS cache_hit_pct,
                    SUM(tool_invocation_count)::float / NULLIF(COUNT(*), 0)        AS tool_ratio,
                    mode() WITHIN GROUP (ORDER BY EXTRACT(hour FROM created_at))   AS peak_hour,
                    COUNT(*)                                                        AS request_count
                FROM cost_records
                WHERE developer_id = CAST(:dev_id AS uuid)
                  AND created_at >= NOW() - INTERVAL '7 days'
            """),
                {"dev_id": developer_id},
            )
        )
        .mappings()
        .one()
    )
    return dict(row)


async def _generate_image(prompt: str) -> bytes:
    """Call litellm /v1/images/generations and return raw PNG bytes."""
    async with httpx.AsyncClient(timeout=60.0) as client:
        resp = await client.post(
            f"{settings.litellm_url}/v1/images/generations",
            json={
                "model": "dall-e-3",
                "prompt": prompt,
                "n": 1,
                "size": "1024x1024",
                "quality": "standard",
                "response_format": "b64_json",
            },
            headers={"Authorization": f"Bearer {settings.litellm_master_key}"},
        )
    if resp.status_code != 200:
        log.error("DALL-E 3 generation failed: %s %s", resp.status_code, resp.text[:200])
        raise HTTPException(status_code=502, detail="Image generation failed")
    b64 = resp.json()["data"][0]["b64_json"]
    return base64.b64decode(b64)


@router.get("/me")
async def get_my_portrait(
    session: AsyncSession = Depends(get_session),
    developer: dict = Depends(_get_current_developer),
):
    """Return this week's usage portrait for the current developer.

    Generated on first call of the week; cached for subsequent calls.
    Returns 404 if the developer has no usage data in the past 7 days.
    """
    developer_id: str = developer["user_id"]
    week_start: date = date.today() - timedelta(days=date.today().weekday())

    # Check cache
    cached = (
        (
            await session.execute(
                text("""
                SELECT scene_data, image_data
                FROM usage_portraits
                WHERE developer_id = CAST(:dev_id AS uuid) AND week_start = :week
            """),
                {"dev_id": developer_id, "week": week_start},
            )
        )
        .mappings()
        .first()
    )

    if cached:
        return {
            "image_base64": base64.b64encode(bytes(cached["image_data"])).decode(),
            "mime": "image/png",
            "week_start": week_start.isoformat(),
            "scene_data": cached["scene_data"],
        }

    # Fetch usage stats
    stats = await _fetch_usage_stats(session, developer_id)
    if not stats.get("request_count"):
        raise HTTPException(status_code=404, detail="No usage data available for portrait")

    # Build scene and generate image
    prompt, scene_data = _build_scene(stats)
    image_bytes = await _generate_image(prompt)

    # Store in DB
    await session.execute(
        text("""
            INSERT INTO usage_portraits (developer_id, week_start, scene_prompt, scene_data, image_data)
            VALUES (CAST(:dev_id AS uuid), :week, :prompt, CAST(:scene AS jsonb), :image)
            ON CONFLICT (developer_id, week_start) DO UPDATE
                SET scene_prompt = EXCLUDED.scene_prompt,
                    scene_data   = EXCLUDED.scene_data,
                    image_data   = EXCLUDED.image_data,
                    generated_at = NOW()
        """),
        {
            "dev_id": developer_id,
            "week": week_start,
            "prompt": prompt,
            "scene": __import__("json").dumps(scene_data),
            "image": image_bytes,
        },
    )
    await session.commit()

    return {
        "image_base64": base64.b64encode(image_bytes).decode(),
        "mime": "image/png",
        "week_start": week_start.isoformat(),
        "scene_data": scene_data,
    }
