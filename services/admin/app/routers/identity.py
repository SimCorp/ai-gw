"""DID-style identity token endpoints for agent authentication.

Routers:
    router        — authenticated endpoints (POST /identity/tokens, POST /identity/verify)
    public_router — unauthenticated GET /identity/jwks
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

import jwt as _jwt
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from app.identity_signing import (
    get_or_create_signing_key,
    get_public_key,
    issue_identity_token,
    public_key_to_jwk,
    verify_identity_token,
)

log = logging.getLogger(__name__)

router = APIRouter(prefix="/identity", tags=["identity"])
public_router = APIRouter(prefix="/identity", tags=["identity"])


# ---------------------------------------------------------------------------
# Request / response models
# ---------------------------------------------------------------------------


class IssueTokenRequest(BaseModel):
    slug: str
    name: str | None = None          # defaults to slug when omitted
    team_id: str | None = None
    scopes: list[str] = []            # treated as capabilities
    ttl_seconds: int = 86400 * 30    # 30-day default


class IssueTokenResponse(BaseModel):
    token: str
    expires_at: str                   # ISO-8601 UTC timestamp


class VerifyTokenRequest(BaseModel):
    token: str


class VerifyTokenResponse(BaseModel):
    valid: bool
    claims: dict | None = None
    error: str | None = None


# ---------------------------------------------------------------------------
# POST /identity/tokens — issue a signed identity token
# ---------------------------------------------------------------------------


@router.post("/tokens", response_model=IssueTokenResponse, summary="Issue agent identity token")
async def issue_token(body: IssueTokenRequest, request: Request):
    """Issue a signed RS256 identity token for an agent slug.

    The ``scopes`` field is stored as the ``capabilities`` claim in the JWT.
    ``name`` defaults to ``slug`` when omitted so callers need only supply
    the slug for a minimal token.
    """
    redis = request.app.state.redis
    effective_name = body.name or body.slug

    token = await issue_identity_token(
        redis=redis,
        slug=body.slug,
        name=effective_name,
        team_id=body.team_id,
        capabilities=body.scopes,
        ttl_seconds=body.ttl_seconds,
    )

    # Decode without verification just to extract exp for the response
    unverified = _jwt.decode(token, options={"verify_signature": False})
    exp_ts = unverified.get("exp", 0)
    expires_at = datetime.fromtimestamp(exp_ts, tz=timezone.utc).isoformat()

    return IssueTokenResponse(token=token, expires_at=expires_at)


# ---------------------------------------------------------------------------
# GET /identity/jwks — public key in JWKS format (no auth)
# ---------------------------------------------------------------------------


@public_router.get("/jwks", summary="Return the public JWKS for token verification")
async def jwks(request: Request):
    """Return the admin service's public signing key as a JWK Set.

    This endpoint requires no authentication; any service in the gateway
    can fetch it to verify identity tokens.
    """
    redis = request.app.state.redis
    private_key, kid = await get_or_create_signing_key(redis)
    pub_key = private_key.public_key()
    jwk = public_key_to_jwk(pub_key, kid)
    return {"keys": [jwk]}


# ---------------------------------------------------------------------------
# POST /identity/verify — verify a token and return claims
# ---------------------------------------------------------------------------


@router.post("/verify", response_model=VerifyTokenResponse, summary="Verify an identity token")
async def verify_token(body: VerifyTokenRequest, request: Request):
    """Verify a signed identity token and return its claims on success."""
    redis = request.app.state.redis
    try:
        pub_key = await get_public_key(redis)
        claims = verify_identity_token(body.token, pub_key)
        return VerifyTokenResponse(valid=True, claims=claims)
    except _jwt.ExpiredSignatureError:
        return VerifyTokenResponse(valid=False, error="Token has expired")
    except _jwt.InvalidSignatureError:
        return VerifyTokenResponse(valid=False, error="Invalid token signature")
    except _jwt.PyJWTError as exc:
        return VerifyTokenResponse(valid=False, error=str(exc))
