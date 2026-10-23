"""Google sign-in (OpenID Connect) for the SignLine web app.

Adapted from the teammate's MudraAI branch ``M2`` (2026-10-23). Flow: the page opens ``/auth/google/start`` in a
popup; Google sends the browser back to ``/auth/google/callback`` with a code; the code is exchanged for an ID token
(PKCE, state and nonce checked), the verified email becomes a signed, HTTP-only session cookie, and the popup tells
the page the result through ``BroadcastChannel`` / ``postMessage`` and closes. The page then reads ``/auth/me``.

Configuration (environment, see ``.env.example``): ``GOOGLE_CLIENT_ID``, ``GOOGLE_CLIENT_SECRET``,
``GOOGLE_REDIRECT_URI`` (the public callback, e.g. the judges Worker URL + ``/auth/google/callback``),
``SIGNLINE_ADMIN_EMAILS`` (admin allow-list), ``SIGNLINE_AUTH_SECRET`` (cookie signing key; random per start when
unset) and ``SIGNLINE_AUTH_COOKIE_SECURE``. Without a client ID and secret the start endpoint reports
``not_configured`` and the page falls back to the local demo sign-in.

Nothing here keeps an account directory: the session cookie carries the verified email, the display name, the
Google profile picture URL and the role; no token or authorization code is logged.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging
import os
import secrets
import time
from urllib.parse import urlencode

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse

log = logging.getLogger("mudra_api.auth")
router = APIRouter(prefix="/auth", tags=["authentication"])
SESSION_COOKIE = "signline_session"
OAUTH_COOKIE = "signline_oauth"
SESSION_TTL = 60 * 60 * 24 * 14
OAUTH_TTL = 10 * 60
RESULT_MESSAGE_TYPE = "signline-google-auth"  # the popup -> page message and BroadcastChannel name
_EPHEMERAL_SECRET = secrets.token_bytes(32)


def _secret() -> bytes:
    configured = os.getenv("SIGNLINE_AUTH_SECRET", "")
    return configured.encode("utf-8") if configured else _EPHEMERAL_SECRET


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")


def _unb64(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


def seal(payload: dict) -> str:
    """Signed, URL-safe token of a small JSON payload (HMAC-SHA256 with the server secret)."""
    encoded = _b64(json.dumps(payload, separators=(",", ":")).encode("utf-8"))
    signature = _b64(hmac.new(_secret(), encoded.encode("ascii"), hashlib.sha256).digest())
    return f"{encoded}.{signature}"


def open_sealed(value: str | None, max_age: int) -> dict | None:
    """The payload of a token from ``seal`` if its signature and lifetime are valid, else None."""
    if not value or "." not in value:
        return None
    encoded, signature = value.rsplit(".", 1)
    expected = _b64(hmac.new(_secret(), encoded.encode("ascii"), hashlib.sha256).digest())
    if not hmac.compare_digest(signature, expected):
        return None
    try:
        payload = json.loads(_unb64(encoded))
    except (ValueError, TypeError):
        return None
    now = int(time.time())
    if not isinstance(payload, dict) or int(payload.get("exp", 0)) < now:
        return None
    if int(payload.get("iat", 0)) > now + 30 or int(payload["exp"]) - int(payload["iat"]) > max_age:
        return None
    return payload


def redirect_uri() -> str:
    return os.getenv("GOOGLE_REDIRECT_URI", "").strip() or "http://localhost:3000/auth/google/callback"


def credentials() -> tuple[str, str] | None:
    client_id = os.getenv("GOOGLE_CLIENT_ID", "").strip()
    client_secret = os.getenv("GOOGLE_CLIENT_SECRET", "").strip()
    return (client_id, client_secret) if client_id and client_secret else None


def admin_emails() -> set[str]:
    return {e.strip().lower() for e in os.getenv("SIGNLINE_ADMIN_EMAILS", "").split(",") if e.strip()}


def _cookie_secure() -> bool:
    configured = os.getenv("SIGNLINE_AUTH_COOKIE_SECURE")
    if configured is not None and configured.strip():
        return configured.strip().lower() in {"1", "true", "yes", "on"}
    return redirect_uri().lower().startswith("https://")


def _set_cookie(response, name: str, value: str, *, max_age: int, path: str = "/") -> None:
    response.set_cookie(name, value, max_age=max_age, path=path, secure=_cookie_secure(), httponly=True, samesite="lax")


def safe_next(value: str | None) -> str:
    """A same-site path to continue to after sign-in; anything else becomes the learner home."""
    if not value or not value.startswith("/") or value.startswith("//") or "\\" in value:
        return "/app/home"
    if value.startswith("/admin"):
        return "/admin"
    if value.startswith("/app"):
        return value
    return "/app/home"


def _popup_result_response(status: str, next_path: str = "/app/home") -> HTMLResponse:
    """The last page of the popup: reports the result to the opener and closes (or, without an opener, continues)."""
    success = status == "success"
    next_path = safe_next(next_path)
    payload = (json.dumps({"type": RESULT_MESSAGE_TYPE, "status": status, "next": next_path}, separators=(",", ":"))
               .replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026"))
    fallback = json.dumps(next_path if success else f"/signin?error=google_{status}").replace("<", "\\u003c")
    response = HTMLResponse(
        f"""<!doctype html><html><head><meta charset="utf-8"><title>SignLine sign-in</title></head>
<body style="font-family:sans-serif;display:grid;place-items:center;height:100vh;margin:0;background:#f6f5ef;">
  <div style="text-align:center;max-width:420px;padding:24px;border:2px solid #1f1b1d;border-radius:18px;background:#fff;">
    <p style="margin:0 0 12px;font-weight:700;">{"Sign-in complete" if success else "Sign-in was not completed"}</p>
    <p>You can close this window.</p>
    <script>
      const result = {payload};
      try {{ if ("BroadcastChannel" in window) {{ const c = new BroadcastChannel("{RESULT_MESSAGE_TYPE}"); c.postMessage(result); c.close(); }} }} catch {{}}
      try {{ if (window.opener) window.opener.postMessage(result, window.location.origin); }} catch {{}}
      window.close();
      window.setTimeout(() => window.location.replace({fallback}), 500);
    </script>
  </div>
</body></html>"""
    )
    response.delete_cookie(OAUTH_COOKIE, path="/auth/google/callback", secure=_cookie_secure(), httponly=True, samesite="lax")
    return response


def session_user(request: Request) -> dict | None:
    """The signed-in Google user of this request (``email``, ``name``, ``picture``, ``role``), or None."""
    session = open_sealed(request.cookies.get(SESSION_COOKIE), SESSION_TTL)
    if not session:
        return None
    return {k: session[k] for k in ("email", "name", "picture", "role") if k in session}


@router.get("/me")
def me(request: Request) -> dict:
    """Who is signed in with Google, and whether Google sign-in is configured on this server."""
    return {"user": session_user(request), "google_configured": credentials() is not None}


@router.post("/logout")
def logout():
    response = JSONResponse({"ok": True})
    response.delete_cookie(SESSION_COOKIE, path="/", secure=_cookie_secure(), httponly=True, samesite="lax")
    return response


@router.get("/google/start")
def google_start(next: str = "/app/home"):
    creds = credentials()
    if not creds:
        return _popup_result_response("not_configured", next)
    client_id, _ = creds
    state, nonce, verifier = secrets.token_urlsafe(32), secrets.token_urlsafe(32), secrets.token_urlsafe(48)
    challenge = _b64(hashlib.sha256(verifier.encode("ascii")).digest())
    now = int(time.time())
    oauth_state = seal({"state": state, "nonce": nonce, "verifier": verifier, "next": safe_next(next),
                        "iat": now, "exp": now + OAUTH_TTL})
    params = {
        "client_id": client_id, "redirect_uri": redirect_uri(), "response_type": "code",
        "scope": "openid email profile", "state": state, "nonce": nonce,
        "code_challenge": challenge, "code_challenge_method": "S256", "prompt": "select_account",
    }
    response = RedirectResponse("https://accounts.google.com/o/oauth2/v2/auth?" + urlencode(params), status_code=302)
    _set_cookie(response, OAUTH_COOKIE, oauth_state, max_age=OAUTH_TTL, path="/auth/google/callback")
    return response


def exchange_code(code: str, verifier: str, client_id: str, client_secret: str) -> dict:
    """Google's ID-token claims for an authorization code (network; replaced in tests)."""
    import requests
    from google.auth.transport.requests import Request as GoogleRequest
    from google.oauth2 import id_token

    token_response = requests.post(
        "https://oauth2.googleapis.com/token",
        data={"code": code, "client_id": client_id, "client_secret": client_secret, "redirect_uri": redirect_uri(),
              "grant_type": "authorization_code", "code_verifier": verifier},
        timeout=15,
    )
    token_response.raise_for_status()
    return id_token.verify_oauth2_token(token_response.json().get("id_token"), GoogleRequest(), audience=client_id,
                                        clock_skew_in_seconds=60)


@router.get("/google/callback")
def google_callback(request: Request, code: str | None = None, state: str | None = None, error: str | None = None):
    oauth = open_sealed(request.cookies.get(OAUTH_COOKIE), OAUTH_TTL)
    if error or not oauth or not state or not hmac.compare_digest(state, str(oauth.get("state", ""))):
        return _popup_result_response("cancelled")
    creds = credentials()
    if not creds or not code:
        return _popup_result_response("failed")
    client_id, client_secret = creds
    try:
        claims = exchange_code(code, oauth["verifier"], client_id, client_secret)
        if claims.get("nonce") != oauth["nonce"] or not claims.get("email_verified"):
            raise ValueError("identity token does not match the sign-in request")
        email = str(claims.get("email", "")).strip().lower()
        subject = str(claims.get("sub", ""))
        if not email or not subject:
            raise ValueError("no verified email address")
    except Exception as exc:  # noqa: BLE001 - any failure ends the sign-in; never log codes, tokens or claims
        log.warning("Google sign-in failed: %s", type(exc).__name__)
        return _popup_result_response("failed")

    role = "admin" if email in admin_emails() else "user"
    now = int(time.time())
    picture = str(claims.get("picture") or "")
    session = {
        "sub": subject, "email": email, "name": str(claims.get("name") or email.split("@", 1)[0])[:100], "role": role,
        "iat": now, "exp": now + SESSION_TTL,
    }
    if picture.startswith("https://") and len(picture) <= 400:
        session["picture"] = picture
    next_path = oauth.get("next", "/app/home")
    if role != "admin" and next_path == "/admin":
        next_path = "/app/home"
    response = _popup_result_response("success", next_path)
    _set_cookie(response, SESSION_COOKIE, seal(session), max_age=SESSION_TTL)
    return response
