"""Auth proxy Lambda — exchanges Cognito auth codes for tokens and sets HttpOnly cookies.

This Lambda sits between the browser and Cognito's /oauth2/token endpoint.
The browser sends the PKCE auth code here; we exchange it with Cognito and
set the resulting JWT in an HttpOnly cookie so JavaScript can never read it.

Routes (all unauthenticated):
  POST /auth/callback  — exchange auth code for tokens, set cookies
  POST /auth/refresh   — use refresh_token cookie to get a new id_token
  POST /auth/logout    — clear cookies
"""

import base64
import json
import logging
import os
import urllib.error
import urllib.parse
import urllib.request

logger = logging.getLogger()
logger.setLevel(logging.INFO)

AUTH_DOMAIN  = os.environ["AUTH_DOMAIN"]   # e.g. https://my-app.auth.us-east-1.amazoncognito.com
CLIENT_ID    = os.environ["COGNITO_CLIENT_ID"]


def lambda_handler(event: dict, context) -> dict:
    ctx  = event.get("requestContext", {}).get("http", {})
    method = ctx.get("method", "")
    path   = ctx.get("path", "")

    if method == "POST" and path == "/auth/callback":
        return _handle_callback(event)
    if method == "POST" and path == "/auth/refresh":
        return _handle_refresh(event)
    if method == "POST" and path == "/auth/logout":
        return _handle_logout()

    return _resp(404, {"error": "Not found"})


# ── Handlers ──────────────────────────────────────────────────────────────────

def _handle_callback(event: dict) -> dict:
    try:
        body = json.loads(event.get("body") or "{}")
    except Exception:
        return _resp(400, {"error": "Invalid JSON"})

    code          = body.get("code", "").strip()
    redirect_uri  = body.get("redirect_uri", "").strip()
    code_verifier = body.get("code_verifier", "").strip()

    if not code or not redirect_uri or not code_verifier:
        return _resp(400, {"error": "code, redirect_uri, and code_verifier are required"})

    data = _cognito_token_request({
        "grant_type":    "authorization_code",
        "client_id":     CLIENT_ID,
        "redirect_uri":  redirect_uri,
        "code":          code,
        "code_verifier": code_verifier,
    })
    if data is None:
        return _resp(400, {"error": "Token exchange with Cognito failed"})

    id_token      = data.get("id_token", "")
    refresh_token = data.get("refresh_token", "")
    if not id_token:
        return _resp(400, {"error": "No id_token in Cognito response"})

    user_info = _extract_user_info(id_token)
    logger.info("Auth callback succeeded for sub=%s", user_info.get("sub"))

    return {
        "statusCode": 200,
        "headers": {"Content-Type": "application/json"},
        "cookies": [
            _access_cookie(id_token),
            _refresh_cookie(refresh_token),
        ],
        "body": json.dumps(user_info),
    }


def _handle_refresh(event: dict) -> dict:
    refresh_token = _get_cookie(event, "memoire_refresh")
    if not refresh_token:
        return _resp(401, {"error": "No refresh token"})

    data = _cognito_token_request({
        "grant_type":    "refresh_token",
        "client_id":     CLIENT_ID,
        "refresh_token": refresh_token,
    })
    if data is None:
        return _resp(401, {"error": "Token refresh failed"})

    id_token = data.get("id_token", "")
    if not id_token:
        return _resp(401, {"error": "No id_token in refresh response"})

    user_info = _extract_user_info(id_token)
    logger.info("Token refresh succeeded for sub=%s", user_info.get("sub"))

    return {
        "statusCode": 200,
        "headers": {"Content-Type": "application/json"},
        "cookies": [_access_cookie(id_token)],
        "body": json.dumps(user_info),
    }


def _handle_logout() -> dict:
    return {
        "statusCode": 200,
        "headers": {"Content-Type": "application/json"},
        "cookies": [
            "memoire_token=; HttpOnly; Secure; SameSite=None; Path=/; Max-Age=0",
            "memoire_refresh=; HttpOnly; Secure; SameSite=None; Path=/; Max-Age=0",
        ],
        "body": json.dumps({"ok": True}),
    }


# ── Helpers ───────────────────────────────────────────────────────────────────

def _cognito_token_request(params: dict) -> dict | None:
    """POST to Cognito /oauth2/token and return the parsed JSON, or None on error."""
    payload = urllib.parse.urlencode(params).encode()
    req = urllib.request.Request(
        f"{AUTH_DOMAIN}/oauth2/token",
        data=payload,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as exc:
        logger.warning("Cognito token request failed: %s %s", exc.code, exc.reason)
        return None
    except Exception as exc:
        logger.error("Cognito token request error: %s", exc)
        return None


def _extract_user_info(id_token: str) -> dict:
    """Decode the JWT payload (without verification — authorizer does that) for display info."""
    try:
        segment = id_token.split(".")[1]
        # Re-pad to a multiple of 4 for standard base64
        padded  = segment + "=" * (4 - len(segment) % 4)
        payload = json.loads(base64.b64decode(padded.replace("-", "+").replace("_", "/")))
        return {
            "email": payload.get("email") or payload.get("cognito:username", ""),
            "sub":   payload.get("sub", ""),
            "exp":   payload.get("exp", 0),
        }
    except Exception:
        return {"email": "", "sub": "", "exp": 0}


def _get_cookie(event: dict, name: str) -> str | None:
    """Extract a named cookie value from the API Gateway event."""
    for raw in event.get("cookies", []):
        for part in raw.split(";"):
            k, _, v = part.strip().partition("=")
            if k.strip() == name:
                return v.strip()
    return None


def _access_cookie(token: str) -> str:
    return f"memoire_token={token}; HttpOnly; Secure; SameSite=None; Path=/; Max-Age=14400"


def _refresh_cookie(token: str) -> str:
    return f"memoire_refresh={token}; HttpOnly; Secure; SameSite=None; Path=/; Max-Age=2592000"


def _resp(status: int, body: dict) -> dict:
    return {
        "statusCode": status,
        "headers": {"Content-Type": "application/json"},
        "body": json.dumps(body),
    }
