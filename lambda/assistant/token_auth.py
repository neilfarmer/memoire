"""Direct token verification for the streaming endpoint.

The streaming handler is invoked via a Lambda Function URL (no API Gateway
authorizer context), so it must validate tokens itself.  This module mirrors
the logic in lambda/authorizer/handler.py — same JWT RS256 verification and
PAT hash lookup — without the Lambda authorizer boilerplate.
"""

import base64
import hashlib
import json
import logging
import os
import time
import urllib.request

import boto3
from boto3.dynamodb.conditions import Key

logger = logging.getLogger(__name__)

TOKENS_TABLE = os.environ.get("TOKENS_TABLE", "")
JWKS_URI     = os.environ.get("JWKS_URI", "")
JWT_ISSUER   = os.environ.get("JWT_ISSUER", "")
JWT_AUDIENCE = os.environ.get("JWT_AUDIENCE", "")

_dynamodb = boto3.resource("dynamodb")

_jwks_cache: dict | None = None
_jwks_cache_at: float = 0.0
_JWKS_TTL = 3600  # 1 hour


def _b64url_decode(s: str) -> bytes:
    s = s.replace("-", "+").replace("_", "/")
    pad = 4 - len(s) % 4
    if pad != 4:
        s += "=" * pad
    return base64.b64decode(s)


def _get_jwks() -> dict:
    global _jwks_cache, _jwks_cache_at
    now = time.time()
    if _jwks_cache and (now - _jwks_cache_at) < _JWKS_TTL:
        return _jwks_cache
    logger.info("Refreshing JWKS from %s", JWKS_URI)
    with urllib.request.urlopen(JWKS_URI, timeout=5) as resp:  # nosec B310
        _jwks_cache = json.loads(resp.read())
        _jwks_cache_at = now
    return _jwks_cache


def _verify_rsa_pkcs1v15_sha256(message: bytes, signature: bytes, n: int, e: int) -> bool:
    k = (n.bit_length() + 7) // 8
    if len(signature) != k:
        return False
    m  = pow(int.from_bytes(signature, "big"), e, n)
    em = m.to_bytes(k, "big")
    sha256_der_prefix = bytes([
        0x30, 0x31, 0x30, 0x0d, 0x06, 0x09, 0x60, 0x86,
        0x48, 0x01, 0x65, 0x03, 0x04, 0x02, 0x01, 0x05,
        0x00, 0x04, 0x20,
    ])
    t       = sha256_der_prefix + hashlib.sha256(message).digest()
    pad_len = k - len(t) - 3
    if pad_len < 8:
        return False
    return em == b"\x00\x01" + b"\xff" * pad_len + b"\x00" + t


def _verify_jwt(token: str) -> str | None:
    """Validate a Cognito JWT and return the sub claim, or None on failure."""
    parts = token.split(".")
    if len(parts) != 3:
        return None
    try:
        header  = json.loads(_b64url_decode(parts[0]))
        payload = json.loads(_b64url_decode(parts[1]))
    except Exception:
        return None

    now = time.time()
    if payload.get("exp", 0) < now:
        logger.warning("JWT expired (sub=%s)", payload.get("sub"))
        return None
    if payload.get("iss") != JWT_ISSUER:
        logger.warning("JWT issuer mismatch: %s", payload.get("iss"))
        return None
    aud = payload.get("aud") or payload.get("client_id")
    if isinstance(aud, list):
        if JWT_AUDIENCE not in aud:
            return None
    elif aud != JWT_AUDIENCE:
        return None

    if header.get("alg") != "RS256":
        logger.warning("JWT rejected: unsupported algorithm %s", header.get("alg"))
        return None

    kid      = header.get("kid")
    jwks     = _get_jwks()
    key_data = next((k for k in jwks.get("keys", []) if k.get("kid") == kid), None)
    if not key_data:
        logger.warning("No JWKS key for kid=%s", kid)
        return None

    try:
        n = int.from_bytes(_b64url_decode(key_data["n"]), "big")
        e = int.from_bytes(_b64url_decode(key_data["e"]), "big")
    except Exception:
        return None

    if not _verify_rsa_pkcs1v15_sha256(
        f"{parts[0]}.{parts[1]}".encode(), _b64url_decode(parts[2]), n, e
    ):
        logger.warning("JWT signature verification failed")
        return None

    return payload.get("sub")


def _verify_pat(token: str) -> str | None:
    """Validate a PAT by hash lookup and return user_id, or None."""
    if not TOKENS_TABLE:
        return None
    token_hash = hashlib.sha256(token.encode()).hexdigest()
    result = _dynamodb.Table(TOKENS_TABLE).query(
        IndexName="token-hash-index",
        KeyConditionExpression=Key("token_hash").eq(token_hash),
        Limit=1,
    )
    items = result.get("Items", [])
    if not items:
        return None
    item = items[0]
    expires_at = item.get("expires_at")
    if expires_at:
        from datetime import datetime, timezone
        try:
            exp_dt = datetime.fromisoformat(expires_at)
            if exp_dt.tzinfo is None:
                exp_dt = exp_dt.replace(tzinfo=timezone.utc)
            if datetime.now(timezone.utc) > exp_dt:
                logger.warning("PAT expired (user_id=%s)", item.get("user_id"))
                return None
        except (ValueError, TypeError):
            pass
    return item.get("user_id")


def extract_token(event: dict) -> str:
    """Extract the raw token from the Authorization header or memoire_token cookie."""
    headers = event.get("headers") or {}
    auth = (headers.get("authorization") or headers.get("Authorization") or "").strip()
    if auth.lower().startswith("bearer"):
        auth = auth[6:].strip()
    if auth:
        return auth
    cookie_header = headers.get("cookie") or headers.get("Cookie") or ""
    for part in cookie_header.split(";"):
        k, _, v = part.strip().partition("=")
        if k.strip() == "memoire_token":
            return v.strip()
    return ""


def get_user_id(event: dict) -> str | None:
    """Return user_id from the event token, or None if invalid/missing."""
    token = extract_token(event)
    if not token:
        return None
    try:
        if token.startswith("pat_"):
            return _verify_pat(token)
        return _verify_jwt(token)
    except Exception:
        logger.exception("Token verification error")
        return None
