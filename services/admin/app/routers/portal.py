"""Self-service developer portal — registration, auth, API key management."""
import hashlib
import json
import os
import secrets
from collections import defaultdict
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session

router = APIRouter(prefix="/portal", tags=["portal"])
templates = Jinja2Templates(directory="app/templates")

# ── DB helpers ──────────────────────────────────────────────────────────────

_ENSURE_STMTS = [
    text("""CREATE TABLE IF NOT EXISTS developers (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        email VARCHAR(255) NOT NULL UNIQUE,
        display_name VARCHAR(255),
        password_hash TEXT NOT NULL,
        status VARCHAR(50) NOT NULL DEFAULT 'pending',
        email_verified_at TIMESTAMPTZ,
        team_id UUID REFERENCES teams(id) ON DELETE SET NULL,
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
    )"""),
    text("CREATE INDEX IF NOT EXISTS idx_developers_email ON developers(email)"),
    text("CREATE INDEX IF NOT EXISTS idx_developers_team  ON developers(team_id)"),
    text("ALTER TABLE api_keys ADD COLUMN IF NOT EXISTS developer_id UUID"),
    text("ALTER TABLE api_keys ADD COLUMN IF NOT EXISTS last_used_at TIMESTAMPTZ"),
]

_tables_ensured = False


async def _ensure_tables(session: AsyncSession) -> None:
    global _tables_ensured
    if _tables_ensured:
        return
    for stmt in _ENSURE_STMTS:
        await session.execute(stmt)
    await session.commit()
    _tables_ensured = True


# ── Password hashing (stdlib, no extra deps) ─────────────────────────────────

def _hash_password(password: str) -> str:
    salt = secrets.token_hex(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), 260_000)
    return f"pbkdf2:{salt}:{dk.hex()}"


def _verify_password(password: str, stored: str) -> bool:
    try:
        _, salt, dk_hex = stored.split(":")
        dk = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), 260_000)
        return secrets.compare_digest(dk.hex(), dk_hex)
    except Exception:
        return False


# ── Session helpers ───────────────────────────────────────────────────────────

SESSION_TTL = 8 * 3600  # 8 hours
VERIFY_TTL = 24 * 3600
PWRESET_TTL = 15 * 60


def _session_key(token: str) -> str:
    return f"portal_session:{token}"


def _verify_key(token: str) -> str:
    return f"portal_verify:{token}"


def _pwreset_key(token: str) -> str:
    return f"portal_pwreset:{token}"


async def get_developer(request: Request, session: AsyncSession = Depends(get_session)) -> Optional[dict]:
    """Dependency — returns developer dict or None."""
    token = request.cookies.get("portal_session")
    if not token:
        return None
    redis = request.app.state.redis
    dev_id = await redis.get(_session_key(token))
    if not dev_id:
        return None
    await _ensure_tables(session)
    row = (await session.execute(
        text("SELECT id, email, display_name, status, email_verified_at, team_id FROM developers WHERE id = :id"),
        {"id": dev_id},
    )).fetchone()
    if not row:
        return None
    return {
        "id": str(row[0]), "email": row[1], "display_name": row[2],
        "status": row[3], "email_verified_at": row[4], "team_id": str(row[5]) if row[5] else None,
    }


async def require_developer(request: Request, session: AsyncSession = Depends(get_session)) -> dict:
    """Dependency — redirects to login if not authenticated."""
    dev = await get_developer(request, session)
    if not dev:
        raise _redirect("/portal/login")
    return dev


def _redirect(url: str, status_code: int = 303):
    """Raise as exception-style redirect."""
    from fastapi import HTTPException
    from starlette.responses import RedirectResponse as RR
    # We can't raise RedirectResponse directly as an exception from a dependency,
    # so we return it and callers check. This helper is used in route handlers only.
    return RedirectResponse(url, status_code=status_code)


# ── Landing page ─────────────────────────────────────────────────────────────

@router.get("", response_class=HTMLResponse)
@router.get("/", response_class=HTMLResponse)
async def portal_root(request: Request, session: AsyncSession = Depends(get_session)):
    dev = await get_developer(request, session)
    if dev:
        return RedirectResponse("/portal/dashboard", status_code=303)
    return templates.TemplateResponse(request, "portal_landing.html", {})


# ── Auth routes (public) ─────────────────────────────────────────────────────

@router.get("/login", response_class=HTMLResponse)
async def login_page(request: Request, error: str = "", success: str = ""):
    return templates.TemplateResponse(request, "portal_login.html", {"error": error, "success": success})


@router.post("/login")
async def login(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
    session: AsyncSession = Depends(get_session),
):
    await _ensure_tables(session)
    row = (await session.execute(
        text("SELECT id, password_hash, status FROM developers WHERE email = :e"),
        {"e": email.lower().strip()},
    )).fetchone()

    if not row or not _verify_password(password, row[1]):
        return templates.TemplateResponse(
            request, "portal_login.html",
            {"error": "Invalid email or password.", "success": ""},
            status_code=401,
        )

    if row[2] == "disabled":
        return templates.TemplateResponse(
            request, "portal_login.html",
            {"error": "Your account has been suspended. Contact Platform Engineering.", "success": ""},
            status_code=403,
        )

    token = secrets.token_urlsafe(32)
    await request.app.state.redis.setex(_session_key(token), SESSION_TTL, str(row[0]))

    resp = RedirectResponse("/portal/dashboard", status_code=303)
    resp.set_cookie("portal_session", token, httponly=True, samesite="lax", max_age=SESSION_TTL)
    return resp


@router.get("/signup", response_class=HTMLResponse)
async def signup_page(request: Request, error: str = ""):
    return templates.TemplateResponse(request, "portal_signup.html", {"error": error})


@router.post("/signup")
async def signup(
    request: Request,
    email: str = Form(...),
    display_name: str = Form(...),
    password: str = Form(...),
    password2: str = Form(...),
    session: AsyncSession = Depends(get_session),
):
    await _ensure_tables(session)
    email = email.lower().strip()

    if password != password2:
        return templates.TemplateResponse(request, "portal_signup.html", {"error": "Passwords do not match."})
    if len(password) < 8:
        return templates.TemplateResponse(request, "portal_signup.html", {"error": "Password must be at least 8 characters."})

    existing = (await session.execute(
        text("SELECT id FROM developers WHERE email = :e"), {"e": email}
    )).fetchone()
    if existing:
        return templates.TemplateResponse(
            request, "portal_signup.html",
            {"error": "An account with this email already exists."},
        )

    # Create personal team
    team_slug = email.split("@")[0].replace(".", "-").lower()
    existing_slug = (await session.execute(
        text("SELECT id FROM teams WHERE slug = :s"), {"s": team_slug}
    )).fetchone()
    if existing_slug:
        team_slug = f"{team_slug}-{secrets.token_hex(3)}"

    team_result = await session.execute(
        text("INSERT INTO teams (name, slug) VALUES (:n, :s) RETURNING id"),
        {"n": display_name or email.split("@")[0], "s": team_slug},
    )
    team_id = team_result.fetchone()[0]

    dev_result = await session.execute(
        text("""INSERT INTO developers (email, display_name, password_hash, status, team_id)
                VALUES (:e, :dn, :ph, 'active', :tid) RETURNING id"""),
        {"e": email, "dn": display_name, "ph": _hash_password(password), "tid": team_id},
    )
    dev_id = dev_result.fetchone()[0]
    await session.commit()

    # In dev: generate a verify token but skip email; just log it
    verify_token = secrets.token_urlsafe(32)
    await request.app.state.redis.setex(_verify_key(verify_token), VERIFY_TTL, str(dev_id))
    verify_url = f"/portal/verify?token={verify_token}"
    print(f"[DEV] Email verify link for {email}: {verify_url}")

    # Auto-verify in dev (no SMTP configured)
    await session.execute(
        text("UPDATE developers SET status='active', email_verified_at=NOW() WHERE id=:id"),
        {"id": dev_id},
    )
    await session.commit()

    return RedirectResponse("/portal/login?success=Account+created+successfully.+You+can+now+sign+in.", status_code=303)


@router.get("/verify", response_class=HTMLResponse)
async def verify_email(
    request: Request,
    token: str = "",
    session: AsyncSession = Depends(get_session),
):
    if not token:
        return RedirectResponse("/portal/login")
    dev_id = await request.app.state.redis.get(_verify_key(token))
    if not dev_id:
        return templates.TemplateResponse(request, "portal_login.html", {"error": "Verification link expired or invalid.", "success": ""})
    await _ensure_tables(session)
    await session.execute(
        text("UPDATE developers SET status='active', email_verified_at=NOW() WHERE id=:id"),
        {"id": dev_id},
    )
    await session.commit()
    await request.app.state.redis.delete(_verify_key(token))
    return RedirectResponse("/portal/login?success=Email+verified.+You+can+now+sign+in.", status_code=303)


@router.post("/logout")
async def logout(request: Request):
    token = request.cookies.get("portal_session")
    if token:
        await request.app.state.redis.delete(_session_key(token))
    resp = RedirectResponse("/portal/login", status_code=303)
    resp.delete_cookie("portal_session")
    return resp


# ── Authenticated routes ──────────────────────────────────────────────────────

@router.get("/dashboard", response_class=HTMLResponse)
async def dashboard(
    request: Request,
    days: int = 30,
    session: AsyncSession = Depends(get_session),
):
    dev = await get_developer(request, session)
    if not dev:
        return RedirectResponse("/portal/login", status_code=303)

    stats = {"requests": 0, "tokens_in": 0, "tokens_out": 0, "cost": 0.0, "cache_hits": 0}
    model_rows: list[dict] = []

    if dev["team_id"]:
        where = "AND cr.created_at >= NOW() - INTERVAL '1 day' * :d" if days > 0 else ""
        q = await session.execute(
            text(f"""
                SELECT
                    cr.model,
                    COUNT(*)                    AS reqs,
                    SUM(cr.tokens_input)        AS tin,
                    SUM(cr.tokens_output)       AS tout,
                    SUM(cr.cost_usd)            AS cost,
                    SUM(CASE WHEN cr.cache_hit THEN 1 ELSE 0 END) AS hits
                FROM cost_records cr
                WHERE cr.team_id = :tid {where}
                GROUP BY cr.model
                ORDER BY cost DESC
            """),
            {"tid": dev["team_id"], "d": days},
        )
        for r in q.fetchall():
            model_rows.append({"model": r[0], "requests": r[1], "tokens_in": r[2] or 0,
                                "tokens_out": r[3] or 0, "cost": float(r[4] or 0), "hits": r[5] or 0})
            stats["requests"] += r[1]
            stats["tokens_in"] += r[2] or 0
            stats["tokens_out"] += r[3] or 0
            stats["cost"] += float(r[4] or 0)
            stats["cache_hits"] += r[5] or 0

    cache_pct = round(stats["cache_hits"] / stats["requests"] * 100, 1) if stats["requests"] else 0
    return templates.TemplateResponse(request, "portal_dashboard.html", {
        "dev": dev, "stats": stats, "model_rows": model_rows,
        "days": days, "cache_pct": cache_pct,
    })


@router.get("/keys", response_class=HTMLResponse)
async def keys_page(
    request: Request,
    new_key: str = "",
    session: AsyncSession = Depends(get_session),
):
    dev = await get_developer(request, session)
    if not dev:
        return RedirectResponse("/portal/login", status_code=303)

    await _ensure_tables(session)
    rows = (await session.execute(
        text("""SELECT id, name, created_at, last_used_at
                FROM api_keys
                WHERE developer_id = :did AND revoked_at IS NULL
                ORDER BY created_at DESC"""),
        {"did": dev["id"]},
    )).fetchall()
    keys = [{"id": str(r[0]), "name": r[1], "created_at": r[2], "last_used_at": r[3]} for r in rows]

    return templates.TemplateResponse(request, "portal_keys.html", {
        "dev": dev, "keys": keys, "new_key": new_key,
    })


@router.post("/keys")
async def create_key(
    request: Request,
    name: str = Form(...),
    session: AsyncSession = Depends(get_session),
):
    dev = await get_developer(request, session)
    if not dev:
        return RedirectResponse("/portal/login", status_code=303)
    if not dev["team_id"]:
        return RedirectResponse("/portal/keys?error=no+team", status_code=303)

    await _ensure_tables(session)
    raw_key = "sk-" + secrets.token_urlsafe(32)
    key_hash = hashlib.sha256(raw_key.encode()).hexdigest()

    await session.execute(
        text("""INSERT INTO api_keys (team_id, developer_id, name, key_hash)
                VALUES (:tid, :did, :name, :kh)"""),
        {"tid": dev["team_id"], "did": dev["id"], "name": name.strip() or "My Key", "kh": key_hash},
    )
    await session.commit()

    resp = RedirectResponse(f"/portal/keys?new_key={raw_key}", status_code=303)
    return resp


@router.post("/keys/{key_id}/revoke")
async def revoke_key(
    key_id: str,
    request: Request,
    session: AsyncSession = Depends(get_session),
):
    dev = await get_developer(request, session)
    if not dev:
        return RedirectResponse("/portal/login", status_code=303)

    await _ensure_tables(session)
    await session.execute(
        text("UPDATE api_keys SET revoked_at=NOW() WHERE id=:id AND developer_id=:did"),
        {"id": key_id, "did": dev["id"]},
    )
    await session.commit()
    return RedirectResponse("/portal/keys", status_code=303)


@router.get("/usage", response_class=HTMLResponse)
async def usage(request: Request, period: str = "30d", session: AsyncSession = Depends(get_session)):
    dev = await get_developer(request, session)
    if not dev:
        return RedirectResponse("/portal/login", status_code=303)

    team_id = dev.get("team_id")
    period_map = {"24h": "24 hours", "7d": "7 days", "30d": "30 days", "mtd": "MTD"}
    if period not in period_map:
        period = "30d"

    if period == "mtd":
        interval_sql = "date_trunc('month', NOW())"
        interval_clause = "created_at >= date_trunc('month', NOW())"
    else:
        hours = {"24h": 24, "7d": 168, "30d": 720}[period]
        interval_clause = f"created_at >= NOW() - INTERVAL '{hours} hours'"
        interval_sql = None

    stats = {"total_spend": 0.0, "request_count": 0, "tokens_in": 0, "tokens_out": 0,
             "cache_rate": 0.0, "cache_saved": 0.0}
    by_model: list[dict] = []
    daily_rows: list[dict] = []
    by_key: list[dict] = []

    if team_id:
        try:
            row = (await session.execute(text(f"""
                SELECT
                    COALESCE(SUM(cost_usd), 0)                                       AS total_spend,
                    COUNT(*)                                                          AS request_count,
                    COALESCE(SUM(tokens_input), 0)                                   AS tokens_in,
                    COALESCE(SUM(tokens_output), 0)                                  AS tokens_out,
                    COALESCE(AVG(CASE WHEN cache_hit THEN 1.0 ELSE 0.0 END), 0)     AS cache_rate,
                    COALESCE(SUM(CASE WHEN cache_hit THEN cost_usd ELSE 0 END), 0)   AS cache_saved
                FROM cost_records
                WHERE team_id = :tid AND {interval_clause}
            """), {"tid": team_id})).mappings().one()
            stats = dict(row)
        except Exception:
            pass

        try:
            rows = (await session.execute(text(f"""
                SELECT model,
                       COUNT(*)                    AS calls,
                       COALESCE(SUM(tokens_input + tokens_output), 0)  AS tokens,
                       COALESCE(SUM(cost_usd), 0) AS cost
                FROM cost_records
                WHERE team_id = :tid AND {interval_clause}
                GROUP BY model ORDER BY cost DESC LIMIT 8
            """), {"tid": team_id})).mappings().all()
            by_model = [dict(r) for r in rows]
        except Exception:
            pass

        try:
            rows = (await session.execute(text(f"""
                SELECT DATE_TRUNC('day', created_at)::date AS day,
                       model,
                       COALESCE(SUM(cost_usd), 0) AS cost
                FROM cost_records
                WHERE team_id = :tid AND {interval_clause}
                GROUP BY day, model ORDER BY day
            """), {"tid": team_id})).mappings().all()
            daily_rows = [dict(r) for r in rows]
        except Exception:
            pass

        try:
            rows = (await session.execute(text(f"""
                SELECT k.name                                                        AS key_name,
                       COUNT(c.id)                                                   AS calls,
                       COALESCE(SUM(c.tokens_input + c.tokens_output), 0)           AS tokens,
                       COALESCE(SUM(c.cost_usd), 0)                                 AS cost
                FROM cost_records c
                JOIN api_keys k ON k.team_id = c.team_id
                WHERE c.team_id = :tid AND {interval_clause}
                GROUP BY k.name ORDER BY cost DESC LIMIT 6
            """), {"tid": team_id})).mappings().all()
            by_key = [dict(r) for r in rows]
        except Exception:
            pass

    # Build chart data: collect all days and models
    day_model_cost: dict = defaultdict(lambda: defaultdict(float))
    all_days: list = []
    all_models_seen: list = []
    for r in daily_rows:
        day_str = str(r["day"])
        model_short = r["model"].split("/")[-1] if "/" in r["model"] else r["model"]
        day_model_cost[day_str][model_short] += float(r["cost"])
        if day_str not in all_days:
            all_days.append(day_str)
        if model_short not in all_models_seen:
            all_models_seen.append(model_short)

    chart_data = json.dumps({
        "days": all_days,
        "models": all_models_seen[:4],
        "costs": {d: dict(v) for d, v in day_model_cost.items()},
    })

    max_model_cost = float(max((r["cost"] for r in by_model), default=1) or 1)
    period_label = {"24h": "24 hours", "7d": "7 days", "30d": "30 days", "mtd": "month to date"}[period]
    tokens_ratio = (
        f"{stats['tokens_in'] / stats['tokens_out']:.1f}:1"
        if stats.get("tokens_out") else "—"
    )

    return templates.TemplateResponse(request, "portal_usage.html", {
        "dev": dev,
        "period": period,
        "period_label": period_label,
        "stats": stats,
        "by_model": by_model,
        "by_key": by_key,
        "chart_data": chart_data,
        "max_model_cost": max_model_cost,
        "tokens_ratio": tokens_ratio,
    })


@router.get("/quickstart", response_class=HTMLResponse)
async def quickstart(request: Request, session: AsyncSession = Depends(get_session)):
    dev = await get_developer(request, session)
    if not dev:
        return RedirectResponse("/portal/login", status_code=303)
    return templates.TemplateResponse(request, "portal_quickstart.html", {"dev": dev})


@router.get("/guides/agents", response_class=HTMLResponse)
async def agents_guide(request: Request, session: AsyncSession = Depends(get_session)):
    dev = await get_developer(request, session)
    if not dev:
        return RedirectResponse("/portal/login", status_code=303)
    return templates.TemplateResponse(request, "portal_agents.html", {"dev": dev})


@router.get("/profile", response_class=HTMLResponse)
async def profile_page(request: Request, session: AsyncSession = Depends(get_session)):
    dev = await get_developer(request, session)
    if not dev:
        return RedirectResponse("/portal/login", status_code=303)
    return templates.TemplateResponse(request, "portal_profile.html", {"dev": dev, "saved": False})


@router.post("/profile")
async def update_profile(
    request: Request,
    display_name: str = Form(""),
    current_password: str = Form(""),
    new_password: str = Form(""),
    new_password2: str = Form(""),
    session: AsyncSession = Depends(get_session),
):
    dev = await get_developer(request, session)
    if not dev:
        return RedirectResponse("/portal/login", status_code=303)
    await _ensure_tables(session)

    error = ""
    if display_name:
        await session.execute(
            text("UPDATE developers SET display_name=:dn, updated_at=NOW() WHERE id=:id"),
            {"dn": display_name, "id": dev["id"]},
        )

    if new_password:
        if new_password != new_password2:
            error = "New passwords do not match."
        elif len(new_password) < 8:
            error = "Password must be at least 8 characters."
        else:
            row = (await session.execute(
                text("SELECT password_hash FROM developers WHERE id=:id"), {"id": dev["id"]}
            )).fetchone()
            if not row or not _verify_password(current_password, row[0]):
                error = "Current password is incorrect."
            else:
                await session.execute(
                    text("UPDATE developers SET password_hash=:ph, updated_at=NOW() WHERE id=:id"),
                    {"ph": _hash_password(new_password), "id": dev["id"]},
                )

    await session.commit()
    if error:
        return templates.TemplateResponse(request, "portal_profile.html", {"dev": dev, "saved": False, "error": error})
    return templates.TemplateResponse(request, "portal_profile.html", {"dev": dev, "saved": True, "error": ""})
