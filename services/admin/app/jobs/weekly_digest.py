"""
Weekly AI usage digest for team admins/managers.
Runs every Monday 07:00 UTC.
Queries usage data from spend_logs/audit_log and emails each team_admin.
"""
from __future__ import annotations

import logging

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

log = logging.getLogger(__name__)


async def send_weekly_digests(session: AsyncSession) -> None:
    """Called by scheduler. Sends one email per team_admin user."""
    import os
    portal_url = os.getenv("PORTAL_BASE_URL", "http://localhost:3001")

    # Get all team_admin users with their teams
    admins = (await session.execute(text("""
        SELECT DISTINCT u.id::text, u.email, u.display_name,
               r.scope_id::text AS team_id,
               t.name AS team_name
        FROM users u
        JOIN user_roles r ON r.user_id = u.id AND r.role = 'team_admin'
                          AND (r.expires_at IS NULL OR r.expires_at > NOW())
        JOIN teams t ON t.id = r.scope_id
        WHERE u.status = 'active' AND u.email IS NOT NULL
        ORDER BY u.email
    """))).mappings().all()

    for admin in admins:
        try:
            # Get spend data for this team over the last 7 days
            team_size = (await session.execute(text("""
                SELECT COUNT(*) FROM team_members WHERE team_id = CAST(:tid AS uuid)
            """), {"tid": admin["team_id"]})).scalar() or 0

            # Try to get actual spend — use a safe query that won't fail if table doesn't exist
            try:
                spend_row = (await session.execute(text("""
                    SELECT
                        COALESCE(SUM(total_cost), 0) as total_cost,
                        COUNT(DISTINCT user_id) as active_users
                    FROM spend_logs
                    WHERE team_id = CAST(:tid AS uuid)
                      AND created_at > NOW() - INTERVAL '7 days'
                """), {"tid": admin["team_id"]})).mappings().first()
                total_cost = float(spend_row["total_cost"] or 0)
                active_users = int(spend_row["active_users"] or 0)
            except Exception:
                total_cost = 0.0
                active_users = 0

            # Get team budget
            try:
                budget_row = (await session.execute(text("""
                    SELECT monthly_budget_usd FROM teams WHERE id = CAST(:tid AS uuid)
                """), {"tid": admin["team_id"]})).first()
                monthly_budget = float(budget_row[0]) if budget_row and budget_row[0] else None
            except Exception:
                monthly_budget = None

            html = _digest_html(
                portal_url=portal_url,
                display_name=admin["display_name"] or admin["email"],
                team_name=admin["team_name"],
                total_cost=total_cost,
                active_users=active_users,
                team_size=team_size,
                monthly_budget=monthly_budget,
            )

            from app.email import send_email
            await send_email(admin["email"], f"Weekly AI digest: {admin['team_name']}", html)
            log.info("Sent weekly digest to %s for team %s", admin["email"], admin["team_name"])

        except Exception as exc:
            log.error("Failed to send digest to %s: %s", admin["email"], exc)


def _digest_html(
    portal_url: str,
    display_name: str,
    team_name: str,
    total_cost: float,
    active_users: int,
    team_size: int,
    monthly_budget: float | None,
) -> str:
    budget_line = ""
    if monthly_budget and monthly_budget > 0:
        pct = round(total_cost / monthly_budget * 100 * 4, 1)  # 4 weeks in month approx
        budget_line = f"<p><strong>Budget utilisation:</strong> {pct}% of ${monthly_budget:,.2f}/mo</p>"

    return f"""
<html><body style="font-family:sans-serif;color:#1a1a2e;max-width:560px;margin:auto">
  <h2 style="color:#0A7BD7">Weekly AI Gateway digest</h2>
  <p>Hi {display_name},</p>
  <p>Here's a summary of AI activity for <strong>{team_name}</strong> over the last 7 days:</p>
  <table style="width:100%;border-collapse:collapse;margin:16px 0">
    <tr><td style="padding:8px 0;border-bottom:1px solid #eee"><strong>Total cost</strong></td>
        <td style="padding:8px 0;border-bottom:1px solid #eee;text-align:right">${total_cost:,.2f}</td></tr>
    <tr><td style="padding:8px 0;border-bottom:1px solid #eee"><strong>Active users</strong></td>
        <td style="padding:8px 0;border-bottom:1px solid #eee;text-align:right">{active_users} / {team_size}</td></tr>
  </table>
  {budget_line}
  <p><a href="{portal_url}/admin/reports" style="background:#0A7BD7;color:#fff;padding:10px 20px;
    border-radius:6px;text-decoration:none;display:inline-block">View full report</a></p>
  <p style="color:#888;font-size:12px">This digest is sent every Monday. Manage your notification
    preferences in the portal.</p>
</body></html>"""
