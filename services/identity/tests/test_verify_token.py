"""Unit tests for identity._verify_identity_token (mocked JWKS endpoint)."""

import base64
import time

import jwt
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa


def _b64url_uint(n: int) -> str:
    b = n.to_bytes((n.bit_length() + 7) // 8, "big")
    return base64.urlsafe_b64encode(b).rstrip(b"=").decode()


def _make_keypair():
    priv = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    nums = priv.public_key().public_numbers()
    jwk = {"kty": "RSA", "n": _b64url_uint(nums.n), "e": _b64url_uint(nums.e)}
    pem = priv.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    )
    return pem, jwk


def _sign(pem: bytes) -> str:
    now = int(time.time())
    return jwt.encode(
        {"sub": "agent-1", "iss": "ai-gw", "iat": now, "exp": now + 300},
        pem,
        algorithm="RS256",
    )


class _FakeResp:
    def __init__(self, data, status=200):
        self._data = data
        self.status_code = status

    def json(self):
        return self._data


class _FakeClient:
    def __init__(self, data, status=200):
        self._data = data
        self._status = status

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    async def get(self, url):
        return _FakeResp(self._data, self._status)


def _patch_httpx(monkeypatch, data, status=200):
    from app import main

    monkeypatch.setattr(main.httpx, "AsyncClient", lambda *a, **k: _FakeClient(data, status))


async def test_verify_valid_token_returns_true(monkeypatch):
    from app.main import _verify_identity_token

    pem, jwk = _make_keypair()
    token = _sign(pem)
    _patch_httpx(monkeypatch, {"keys": [jwk]})

    assert await _verify_identity_token(token, "http://admin") is True


async def test_verify_wrong_key_returns_false(monkeypatch):
    from app.main import _verify_identity_token

    signing_pem, _ = _make_keypair()
    _, other_jwk = _make_keypair()  # JWKS publishes a DIFFERENT key
    token = _sign(signing_pem)
    _patch_httpx(monkeypatch, {"keys": [other_jwk]})

    assert await _verify_identity_token(token, "http://admin") is False


async def test_verify_jwks_fetch_failure_returns_false(monkeypatch):
    from app.main import _verify_identity_token

    pem, _ = _make_keypair()
    token = _sign(pem)
    _patch_httpx(monkeypatch, {}, status=500)

    assert await _verify_identity_token(token, "http://admin") is False


async def test_verify_no_keys_returns_false(monkeypatch):
    from app.main import _verify_identity_token

    pem, _ = _make_keypair()
    token = _sign(pem)
    _patch_httpx(monkeypatch, {"keys": []})

    assert await _verify_identity_token(token, "http://admin") is False
