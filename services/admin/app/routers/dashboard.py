from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session

router = APIRouter(tags=["dashboard"])
templates = Jinja2Templates(directory="app/templates")


@router.get("/", response_class=HTMLResponse)
async def dashboard(request: Request, session: AsyncSession = Depends(get_session)):

    # Import here to avoid circular at module load
    from sqlalchemy import text

    stats_result = await session.execute(
        text("""
            SELECT
                t.name AS team_name,
                COUNT(cr.id) AS request_count,
                SUM(cr.tokens_input + cr.tokens_output) AS total_tokens,
                ROUND(SUM(cr.cost_usd)::numeric, 4) AS total_cost_usd,
                ROUND(AVG(CASE WHEN cr.cache_hit THEN 1.0 ELSE 0.0 END) * 100, 1) AS cache_hit_pct
            FROM teams t
            LEFT JOIN cost_records cr ON cr.team_id = t.id
            GROUP BY t.id, t.name
            ORDER BY total_tokens DESC NULLS LAST
        """)
    )
    rows = stats_result.mappings().all()

    return templates.TemplateResponse("dashboard.html", {"request": request, "rows": rows})
