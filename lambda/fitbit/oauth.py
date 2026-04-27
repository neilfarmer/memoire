"""Fitbit OAuth2 authorization-code flow with PKCE.

Frontend flow:
  1. GET /fitbit/auth/start?redirect_uri=...
       Returns {authorize_url, code_verifier}. Frontend stores the verifier
       in sessionStorage and redirects the browser to authorize_url.
  2. Fitbit redirects back to redirect_uri?code=...
  3. Frontend POSTs /fitbit/auth/callback with {code, redirect_uri, code_verifier}.
       We exchange the code for tokens and persist them under the user_id.
"""

import base64
import hashlib
import json
import logging
import os
import secrets
import time
import urllib.error
import urllib.parse
import urllib.request

import db
from response import ok, error
from utils import now_iso

logger = logging.getLogger()

CLIENT_ID     = os.environ.get("FITBIT_CLIENT_ID", "")
CLIENT_SECRET = os.environ.get("FITBIT_CLIENT_SECRET", "")
TOKENS_TABLE  = os.environ["FITBIT_TOKENS_TABLE"]

AUTHORIZE_URL = "https://www.fitbit.com/oauth2/authorize"
TOKEN_URL     = "https://api.fitbit.com/oauth2/token"

DEFAULT_SCOPES = ["activity", "nutrition", "weight", "sleep", "profile"]


def _pkce_pair() -> tuple[str, str]:
    verifier  = base64.urlsafe_b64encode(secrets.token_bytes(64)).rstrip(b"=").decode()
    digest    = hashlib.sha256(verifier.encode()).digest()
    challenge = base64.urlsafe_b64encode(digest).rstrip(b"=").decode()
    return verifier, challenge


def start(user_id: str, query_params: dict) -> dict:
    if not CLIENT_ID:
        return error("Fitbit integration not configured", status=503)

    qp = query_params or {}
    redirect_uri = (qp.get("redirect_uri") or "").strip()
    if not redirect_uri:
        return error("redirect_uri is required")

    verifier, challenge = _pkce_pair()
    state = secrets.token_urlsafe(24)

    params = {
        "response_type":         "code",
        "client_id":             CLIENT_ID,
        "redirect_uri":          redirect_uri,
        "scope":                 " ".join(DEFAULT_SCOPES),
        "code_challenge":        challenge,
        "code_challenge_method": "S256",
        "state":                 state,
    }
    return ok({
        "authorize_url": f"{AUTHORIZE_URL}?{urllib.parse.urlencode(params)}",
        "code_verifier": verifier,
        "state":         state,
    })


def callback(user_id: str, body: dict) -> dict:
    if not CLIENT_ID or not CLIENT_SECRET:
        return error("Fitbit integration not configured", status=503)

    code          = (body.get("code") or "").strip()
    redirect_uri  = (body.get("redirect_uri") or "").strip()
    code_verifier = (body.get("code_verifier") or "").strip()
    if not code or not redirect_uri or not code_verifier:
        return error("code, redirect_uri, and code_verifier are required")

    data = _token_request({
        "client_id":     CLIENT_ID,
        "grant_type":    "authorization_code",
        "redirect_uri":  redirect_uri,
        "code":          code,
        "code_verifier": code_verifier,
    })
    if data is None:
        return error("Token exchange with Fitbit failed", status=400)

    _store_tokens(user_id, data)
    return ok({"connected": True})


def refresh_tokens(user_id: str, refresh_token: str) -> dict | None:
    """Used by the sync Lambda. Returns refreshed token row or None on failure."""
    data = _token_request({
        "client_id":     CLIENT_ID,
        "grant_type":    "refresh_token",
        "refresh_token": refresh_token,
    })
    if data is None:
        return None
    return _store_tokens(user_id, data)


def get_tokens(user_id: str) -> dict | None:
    item = db.get_table(TOKENS_TABLE).get_item(Key={"user_id": user_id}).get("Item")
    return item or None


def delete_tokens(user_id: str) -> None:
    db.get_table(TOKENS_TABLE).delete_item(Key={"user_id": user_id})


def _store_tokens(user_id: str, data: dict) -> dict:
    expires_in = int(data.get("expires_in", 28800))
    item = {
        "user_id":         user_id,
        "access_token":    data.get("access_token", ""),
        "refresh_token":   data.get("refresh_token", ""),
        "expires_at":      int(time.time()) + expires_in,
        "scope":           data.get("scope", ""),
        "fitbit_user_id":  data.get("user_id", ""),
        "connected_at":    now_iso(),
        "updated_at":      now_iso(),
    }
    db.get_table(TOKENS_TABLE).put_item(Item=item)
    return item


def _token_request(params: dict) -> dict | None:
    """POST to Fitbit /oauth2/token. Uses HTTP Basic auth as required by the Fitbit API."""
    payload = urllib.parse.urlencode(params).encode()
    basic   = base64.b64encode(f"{CLIENT_ID}:{CLIENT_SECRET}".encode()).decode()
    req = urllib.request.Request(
        TOKEN_URL,
        data=payload,
        headers={
            "Authorization": f"Basic {basic}",
            "Content-Type":  "application/x-www-form-urlencoded",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:  # nosec B310 — fixed Fitbit HTTPS endpoint
            return json.loads(resp.read())
    except urllib.error.HTTPError as exc:
        body = ""
        try:
            body = exc.read().decode()[:200]
        except Exception:
            pass
        logger.warning("Fitbit token request failed: %s %s %s", exc.code, exc.reason, body)
        return None
    except Exception as exc:
        logger.error("Fitbit token request error: %s", exc)
        return None
