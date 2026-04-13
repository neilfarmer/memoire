"""Lambda authorizer supporting both Cognito JWTs and Personal Access Tokens (PATs).

Authorization header formats accepted:
  - Cognito JWT:  "Bearer eyJ..."  or  "eyJ..."
  - Personal PAT: "pat_<token>"

JWT validation is implemented in pure Python (no external packages required):
  - RS256 / PKCS#1 v1.5 + SHA-256 verified using Python's built-in pow() and hashlib.
  - Cognito public keys are fetched once and cached in Lambda memory for 1 hour.

PAT validation:
  - SHA-256 hash of the token is looked up in the tokens DynamoDB table via a GSI.
  - Plaintext tokens are never stored — only their SHA-256 hex digests.
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

logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Emit structured JSON so CloudWatch Logs Insights can query individual fields.
class _JsonFormatter(logging.Formatter):
    def format(self, record):
        log = {"level": record.levelname, "message": record.getMessage()}
        if record.exc_info:
            log["exception"] = self.formatException(record.exc_info)
        return json.dumps(log)

if not logger.handlers:
    _handler = logging.StreamHandler()
    _handler.setFormatter(_JsonFormatter())
    logger.addHandler(_handler)

TOKENS_TABLE = os.environ["TOKENS_TABLE"]
JWKS_URI     = os.environ["JWKS_URI"]
JWT_ISSUER   = os.environ["JWT_ISSUER"]
JWT_AUDIENCE = os.environ["JWT_AUDIENCE"]

_dynamodb = boto3.resource("dynamodb")

# In-memory JWKS cache (persists across warm Lambda invocations)
_jwks_cache: dict | None = None
_jwks_cache_at: float = 0.0
JWKS_TTL = 3600  # 1 hour


# ── Helpers ───────────────────────────────────────────────────────────────────

def _b64url_decode(s: str) -> bytes:
    """Decode a base64url-encoded string (no padding required)."""
    s = s.replace("-", "+").replace("_", "/")
    pad = 4 - len(s) % 4
    if pad != 4:
        s += "=" * pad
    return base64.b64decode(s)


def _get_jwks() -> dict:
    """Fetch Cognito JWKS, using an in-memory cache."""
    global _jwks_cache, _jwks_cache_at
    now = time.time()
    if _jwks_cache and (now - _jwks_cache_at) < JWKS_TTL:
        return _jwks_cache
    logger.info("Refreshing JWKS from %s", JWKS_URI)
    with urllib.request.urlopen(JWKS_URI, timeout=5) as resp:  # nosec B310 — JWKS_URI is a Terraform-injected Cognito URL
        _jwks_cache = json.loads(resp.read())
        _jwks_cache_at = now
    return _jwks_cache


def _verify_rsa_pkcs1v15_sha256(
    message: bytes, signature: bytes, n: int, e: int
) -> bool:
    """Verify an RSA-PKCS1v1.5-SHA256 signature using only Python builtins.

    RSA public verification: m = sig^e mod n.
    Because the Cognito public exponent is 65537 (17 bits), pow() is fast.
    """
    k = (n.bit_length() + 7) // 8  # Modulus byte length
    if len(signature) != k:
        return False

    sig_int = int.from_bytes(signature, "big")
    m       = pow(sig_int, e, n)
    em      = m.to_bytes(k, "big")

    # PKCS#1 v1.5 DigestInfo DER prefix for SHA-256
    sha256_der_prefix = bytes([
        0x30, 0x31, 0x30, 0x0d, 0x06, 0x09, 0x60, 0x86,
        0x48, 0x01, 0x65, 0x03, 0x04, 0x02, 0x01, 0x05,
        0x00, 0x04, 0x20,
    ])
    digest  = hashlib.sha256(message).digest()
    t       = sha256_der_prefix + digest   # 19 + 32 = 51 bytes
    pad_len = k - len(t) - 3              # Space for 0x00 0x01 ... 0x00

    if pad_len < 8:                        # PKCS#1 requires ≥ 8 bytes of 0xFF
        return False

    expected = b"\x00\x01" + b"\xff" * pad_len + b"\x00" + t
    return em == expected


# ── JWT validation ─────────────────────────────────────────────────────────────

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

    # Validate expiry, issuer, and audience
    now = time.time()
    if payload.get("exp", 0) < now:
        logger.warning("JWT rejected: expired (sub=%s)", payload.get("sub"))
        return None
    if payload.get("iss") != JWT_ISSUER:
        logger.warning("JWT rejected: issuer mismatch (got %s)", payload.get("iss"))
        return None
    aud = payload.get("aud") or payload.get("client_id")
    if isinstance(aud, list):
        if JWT_AUDIENCE not in aud:
            logger.warning("JWT rejected: audience mismatch")
            return None
    elif aud != JWT_AUDIENCE:
        logger.warning("JWT rejected: audience mismatch (got %s)", aud)
        return None

    # Only RS256 is supported (used by Cognito JWKS)
    if header.get("alg") != "RS256":
        logger.warning("JWT rejected: unsupported algorithm %s", header.get("alg"))
        return None

    # Locate the matching public key by kid
    kid = header.get("kid")
    if not kid:
        return None
    jwks     = _get_jwks()
    key_data = next((k for k in jwks.get("keys", []) if k.get("kid") == kid), None)
    if not key_data:
        logger.warning("No JWKS key found for kid=%s", kid)
        return None

    try:
        n = int.from_bytes(_b64url_decode(key_data["n"]), "big")
        e = int.from_bytes(_b64url_decode(key_data["e"]), "big")
    except (KeyError, Exception) as exc:
        logger.error("Failed to parse JWK: %s", exc)
        return None

    message   = f"{parts[0]}.{parts[1]}".encode()
    signature = _b64url_decode(parts[2])

    if not _verify_rsa_pkcs1v15_sha256(message, signature, n, e):
        logger.warning("JWT signature verification failed")
        return None

    return payload.get("sub")


# ── PAT validation ─────────────────────────────────────────────────────────────

def _verify_pat(token: str) -> str | None:
    """Look up a PAT by its hash in DynamoDB and return the user_id, or None."""
    token_hash = hashlib.sha256(token.encode()).hexdigest()
    table  = _dynamodb.Table(TOKENS_TABLE)
    result = table.query(
        IndexName="token-hash-index",
        KeyConditionExpression=Key("token_hash").eq(token_hash),
        Limit=1,
    )
    items = result.get("Items", [])
    if not items:
        logger.warning("Auth rejected: PAT hash not found in tokens table")
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
                logger.warning("Auth rejected: PAT expired (user_id=%s)", item.get("user_id"))
                return None
        except (ValueError, TypeError):
            pass  # invalid timestamp — treat as no expiry
    return item.get("user_id")


# ── Entry point ───────────────────────────────────────────────────────────────

def _extract_token(event: dict) -> str:
    """Return the raw token string from either the Authorization header (PATs)
    or the memoire_token cookie (browser JWT), preferring Authorization."""
    headers = event.get("headers") or {}

    # Authorization header — used by PAT clients and PAT API users
    auth_header = headers.get("authorization") or headers.get("Authorization") or ""
    auth_header = auth_header.strip()
    if auth_header.lower().startswith("bearer"):
        auth_header = auth_header[6:].strip()  # strip "bearer" + any surrounding whitespace
    if auth_header:
        return auth_header

    # Cookie — used by browser sessions (HttpOnly cookie set by /auth/callback)
    cookie_header = headers.get("cookie") or headers.get("Cookie") or ""
    for part in cookie_header.split(";"):
        k, _, v = part.strip().partition("=")
        if k.strip() == "memoire_token":
            return v.strip()

    return ""


def lambda_handler(event: dict, context) -> dict:
    token = _extract_token(event)

    if not token:
        logger.warning("Auth rejected: no token in Authorization header or cookie")
        return {"isAuthorized": False}

    try:
        if token.startswith("pat_"):
            user_id = _verify_pat(token)
        else:
            user_id = _verify_jwt(token)
    except Exception as exc:
        logger.error("Auth error: %s", exc)
        return {"isAuthorized": False}

    if not user_id:
        logger.warning("Auth rejected: token validation failed")
        return {"isAuthorized": False}

    return {
        "isAuthorized": True,
        "context": {
            "user_id":     user_id,
            "auth_method": "pat" if token.startswith("pat_") else "jwt",
        },
    }
