"""DID-style signed identity tokens for agents.

Implements a simple verifiable identity model:
- Admin service acts as the identity authority (signs tokens)
- Tokens are JWTs containing the agent's identity claims
- Any service can verify tokens using the admin's public key

The signing key pair is generated once per admin startup and stored in Redis.
The public key is served at GET /identity/jwks so any service can verify.

Usage:
    # Issue a token (admin side)
    token = await issue_identity_token(redis, agent_slug, name, team_id, capabilities)

    # Verify a token (any service)
    claims = verify_identity_token(token, public_key)
"""

from __future__ import annotations

import base64
import hashlib
import logging
import secrets
from datetime import datetime, timedelta, timezone

import jwt
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives.asymmetric.rsa import RSAPrivateKey, RSAPublicKey

log = logging.getLogger(__name__)

_REDIS_KEY = "identity:signing_key"
_REDIS_KID_KEY = "identity:signing_kid"
_KEY_TTL = 90 * 24 * 3600  # 90 days in seconds
_ISSUER = "ai-gateway"

_DEV_SECRET = "dev-identity-key-secret-change-in-prod"


def _fernet(secret: str) -> Fernet:
    """Derive a Fernet key from an arbitrary secret string using SHA-256."""
    digest = hashlib.sha256(secret.encode()).digest()
    fernet_key = base64.urlsafe_b64encode(digest)
    return Fernet(fernet_key)


def _get_identity_secret() -> str:
    """Return the IDENTITY_KEY_SECRET env var, falling back to the dev placeholder."""
    from app.config import settings

    return settings.identity_key_secret or _DEV_SECRET


# ---------------------------------------------------------------------------
# Key management
# ---------------------------------------------------------------------------


async def get_or_create_signing_key(redis) -> tuple[RSAPrivateKey, str]:
    """Load or generate an RSA-2048 signing key pair.

    Private key is stored in Redis (PEM format) at ``identity:signing_key``
    with a 90-day TTL.  A stable key ID (``kid``) is stored alongside it at
    ``identity:signing_kid``.

    Returns:
        (private_key, key_id) — the RSAPrivateKey object and the opaque kid
        string used to identify the key in JWKS responses.
    """
    secret = _get_identity_secret()
    f = _fernet(secret)

    raw: bytes | str | None = await redis.get(_REDIS_KEY)
    kid_str: str | None = await redis.get(_REDIS_KID_KEY)

    if raw and kid_str:
        try:
            # raw may be bytes or str depending on Redis client decode_responses setting
            raw_bytes = raw if isinstance(raw, bytes) else raw.encode()
            pem_bytes = f.decrypt(raw_bytes)
            private_key = serialization.load_pem_private_key(pem_bytes, password=None)
            return private_key, kid_str  # type: ignore[return-value]
        except Exception as exc:
            log.warning("Failed to load/decrypt stored signing key, regenerating: %s", exc)

    # Generate a new RSA-2048 key pair
    private_key = rsa.generate_private_key(
        public_exponent=65537,
        key_size=2048,
    )
    pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.TraditionalOpenSSL,
        encryption_algorithm=serialization.NoEncryption(),
    )
    kid = secrets.token_urlsafe(16)

    encrypted_pem = f.encrypt(pem)
    await redis.setex(_REDIS_KEY, _KEY_TTL, encrypted_pem)
    await redis.setex(_REDIS_KID_KEY, _KEY_TTL, kid)

    log.info("Generated new RSA-2048 identity signing key (kid=%s)", kid)
    return private_key, kid


async def get_public_key(redis) -> RSAPublicKey:
    """Return the public key corresponding to the current signing key."""
    private_key, _ = await get_or_create_signing_key(redis)
    return private_key.public_key()  # type: ignore[return-value]


# ---------------------------------------------------------------------------
# Token issuance
# ---------------------------------------------------------------------------


async def issue_identity_token(
    redis,
    slug: str,
    name: str,
    team_id: str | None,
    capabilities: list[str],
    ttl_seconds: int = 86400 * 30,
) -> str:
    """Issue a signed RS256 JWT identity token for an agent.

    Args:
        redis:        Async Redis client.
        slug:         Agent slug used as the JWT ``sub`` claim.
        name:         Human-readable agent name.
        team_id:      Optional team UUID (stringified) the agent belongs to.
        capabilities: List of capability tags.
        ttl_seconds:  Token lifetime in seconds (default: 30 days).

    Returns:
        A signed JWT string (RS256).
    """
    private_key, kid = await get_or_create_signing_key(redis)

    now = datetime.now(timezone.utc)
    exp = now + timedelta(seconds=ttl_seconds)

    payload: dict = {
        "iss": _ISSUER,
        "sub": slug,
        "name": name,
        "iat": int(now.timestamp()),
        "exp": int(exp.timestamp()),
        "capabilities": capabilities,
    }
    if team_id is not None:
        payload["team_id"] = team_id

    token: str = jwt.encode(
        payload,
        private_key,  # type: ignore[arg-type]
        algorithm="RS256",
        headers={"kid": kid},
    )
    return token


# ---------------------------------------------------------------------------
# Token verification
# ---------------------------------------------------------------------------


def verify_identity_token(token: str, public_key: RSAPublicKey) -> dict:
    """Verify an RS256 identity token against the supplied public key.

    Args:
        token:      The JWT string to verify.
        public_key: RSAPublicKey from the issuing admin service.

    Returns:
        The decoded claims dict on success.

    Raises:
        jwt.PyJWTError: If the token is invalid, expired, or tampered.
    """
    claims: dict = jwt.decode(
        token,
        public_key,  # type: ignore[arg-type]
        algorithms=["RS256"],
        options={"require": ["sub", "iss", "iat", "exp"]},
    )
    return claims


# ---------------------------------------------------------------------------
# JWKS helpers
# ---------------------------------------------------------------------------


def public_key_to_jwk(public_key: RSAPublicKey, kid: str) -> dict:
    """Serialise an RSAPublicKey to a JWK dict (RFC 7517)."""
    pub_numbers = (
        public_key.public_key().public_numbers()
        if hasattr(public_key, "private_numbers")
        else public_key.public_numbers()
    )  # type: ignore[attr-defined]

    def _b64url(n: int, length: int) -> str:
        return base64.urlsafe_b64encode(n.to_bytes(length, "big")).rstrip(b"=").decode()

    # RSA public key: n (modulus) and e (exponent)
    n_bytes = (pub_numbers.n.bit_length() + 7) // 8
    return {
        "kty": "RSA",
        "use": "sig",
        "alg": "RS256",
        "kid": kid,
        "n": _b64url(pub_numbers.n, n_bytes),
        "e": _b64url(pub_numbers.e, 3),
    }
