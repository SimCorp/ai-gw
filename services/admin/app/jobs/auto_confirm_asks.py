"""Nightly cron: auto-confirm asks past their auto_confirm_at deadline."""
import logging

from sqlalchemy import text

from app.db import async_session_maker
from app.league_client import grant_points

log = logging.getLogger(__name__)


async def run_auto_confirm() -> int:
    """Promote resolved_pending -> resolved for all asks past auto_confirm_at.

    Grants league points to the claimed champion. Returns count promoted.

    The status update is committed BEFORE league grants are issued so that a
    transient grant failure does not undo the promotion (grants are
    best-effort).
    """
    async with async_session_maker() as session:
        result = await session.execute(text("""
            UPDATE champion_asks
            SET status = 'resolved', confirmed_at = NOW()
            WHERE status = 'resolved_pending'
              AND auto_confirm_at IS NOT NULL
              AND auto_confirm_at <= NOW()
            RETURNING id, claimed_by
        """))
        rows = list(result)
        await session.commit()

    for ask_id, claimed_by in rows:
        if claimed_by is None:
            continue
        try:
            await grant_points(
                engineer_id=str(claimed_by),
                delta=200,
                reason="champion_ask_resolved_auto",
                ref_id=str(ask_id),
            )
        except RuntimeError as e:
            log.warning("auto-confirm league grant failed for ask %s: %s", ask_id, e)
    return len(rows)
