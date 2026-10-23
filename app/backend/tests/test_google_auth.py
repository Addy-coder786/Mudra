"""Google sign-in endpoints (mudra_api/google_auth.py) with Google itself replaced by a stub."""

from __future__ import annotations

import time
from urllib.parse import parse_qs, urlparse

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from mudra_api import google_auth
from mudra_api.google_auth import OAUTH_COOKIE, SESSION_COOKIE, router, safe_next, seal


@pytest.fixture
def client():
    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


@pytest.fixture
def configured(monkeypatch):
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "client-id.apps.googleusercontent.com")
    monkeypatch.setenv("GOOGLE_CLIENT_SECRET", "client-secret")
    monkeypatch.setenv("GOOGLE_REDIRECT_URI", "http://localhost:3000/auth/google/callback")
    monkeypatch.setenv("SIGNLINE_ADMIN_EMAILS", "Admin@Example.com")
    monkeypatch.setenv("SIGNLINE_AUTH_SECRET", "test-secret")


def _start(client) -> tuple[str, str, dict]:
    """Run /auth/google/start: (state, nonce, cookies) as the browser would hold them."""
    r = client.get("/auth/google/start?next=/app/learning", follow_redirects=False)
    assert r.status_code == 302
    q = parse_qs(urlparse(r.headers["location"]).query)
    oauth = google_auth.open_sealed(r.cookies.get(OAUTH_COOKIE), google_auth.OAUTH_TTL)
    return q["state"][0], q["nonce"][0], oauth


def _claims(nonce, email="learner@example.com", **extra):
    return {"sub": "1234567890", "email": email, "email_verified": True, "name": "Learner One",
            "picture": "https://lh3.googleusercontent.com/a/photo", "nonce": nonce, **extra}


def test_not_configured_start_reports_to_the_page_and_me_says_so(client, monkeypatch):
    monkeypatch.delenv("GOOGLE_CLIENT_ID", raising=False)
    monkeypatch.delenv("GOOGLE_CLIENT_SECRET", raising=False)
    assert client.get("/auth/me").json() == {"user": None, "google_configured": False}
    r = client.get("/auth/google/start")
    assert r.status_code == 200 and '"status":"not_configured"' in r.text and "signline-google-auth" in r.text


def test_start_redirects_to_google_with_pkce_state_and_nonce(client, configured):
    r = client.get("/auth/google/start?next=/admin", follow_redirects=False)
    url = urlparse(r.headers["location"])
    q = parse_qs(url.query)
    assert url.netloc == "accounts.google.com"
    assert q["client_id"] == ["client-id.apps.googleusercontent.com"]
    assert q["redirect_uri"] == ["http://localhost:3000/auth/google/callback"]
    assert q["code_challenge_method"] == ["S256"] and q["scope"] == ["openid email profile"]
    oauth = google_auth.open_sealed(r.cookies.get(OAUTH_COOKIE), google_auth.OAUTH_TTL)
    assert oauth["state"] == q["state"][0] and oauth["nonce"] == q["nonce"][0] and oauth["next"] == "/admin"
    assert "HttpOnly" in r.headers["set-cookie"] and "Path=/auth/google/callback" in r.headers["set-cookie"]


def test_callback_signs_in_a_learner_with_name_and_picture(client, configured, monkeypatch):
    state, nonce, oauth = _start(client)
    seen = {}

    def fake_exchange(code, verifier, client_id, client_secret):
        seen.update(code=code, verifier=verifier, client_id=client_id)
        return _claims(nonce)

    monkeypatch.setattr(google_auth, "exchange_code", fake_exchange)
    r = client.get(f"/auth/google/callback?code=abc&state={state}")
    assert r.status_code == 200 and '"status":"success"' in r.text and '"next":"/app/learning"' in r.text
    assert seen == {"code": "abc", "verifier": oauth["verifier"], "client_id": "client-id.apps.googleusercontent.com"}
    assert SESSION_COOKIE in r.cookies
    me = client.get("/auth/me").json()
    assert me["user"] == {"email": "learner@example.com", "name": "Learner One",
                          "picture": "https://lh3.googleusercontent.com/a/photo", "role": "user"}
    assert me["google_configured"] is True
    client.post("/auth/logout")
    assert client.get("/auth/me").json()["user"] is None


def test_admin_allow_list_and_admin_next_only_for_admins(client, configured, monkeypatch):
    state, nonce, _ = _start(client)
    monkeypatch.setattr(google_auth, "exchange_code", lambda *a: _claims(nonce, email="admin@example.com"))
    client.get(f"/auth/google/callback?code=abc&state={state}")
    assert client.get("/auth/me").json()["user"]["role"] == "admin"

    client.cookies.clear()
    r = client.get("/auth/google/start?next=/admin", follow_redirects=False)
    state = parse_qs(urlparse(r.headers["location"]).query)["state"][0]
    nonce = google_auth.open_sealed(r.cookies.get(OAUTH_COOKIE), google_auth.OAUTH_TTL)["nonce"]
    monkeypatch.setattr(google_auth, "exchange_code", lambda *a: _claims(nonce))  # a learner asking for /admin
    r = client.get(f"/auth/google/callback?code=abc&state={state}")
    assert '"status":"success"' in r.text and '"next":"/app/home"' in r.text


@pytest.mark.parametrize("case", ["bad_state", "wrong_nonce", "unverified_email", "google_error", "exchange_fails"])
def test_callback_rejects_tampered_or_failed_sign_ins(client, configured, monkeypatch, case):
    state, nonce, _ = _start(client)
    claims = _claims("other-nonce" if case == "wrong_nonce" else nonce)
    if case == "unverified_email":
        claims["email_verified"] = False

    def exchange(*a):
        if case == "exchange_fails":
            raise ValueError("token exchange failed")
        return claims

    monkeypatch.setattr(google_auth, "exchange_code", exchange)
    url = f"/auth/google/callback?code=abc&state={'nope' if case == 'bad_state' else state}"
    if case == "google_error":
        url += "&error=access_denied"
    r = client.get(url)
    expected = "cancelled" if case in ("bad_state", "google_error") else "failed"
    assert r.status_code == 200 and f'"status":"{expected}"' in r.text
    assert SESSION_COOKIE not in r.cookies and client.get("/auth/me").json()["user"] is None


def test_sealed_tokens_expire_and_reject_other_keys(monkeypatch):
    monkeypatch.setenv("SIGNLINE_AUTH_SECRET", "one")
    now = int(time.time())
    token = seal({"iat": now, "exp": now + 60})
    assert google_auth.open_sealed(token, 120) is not None
    assert google_auth.open_sealed(token, 30) is None  # longer than the allowed lifetime
    assert google_auth.open_sealed(seal({"iat": now - 100, "exp": now - 1}), 120) is None  # expired
    monkeypatch.setenv("SIGNLINE_AUTH_SECRET", "two")
    assert google_auth.open_sealed(token, 120) is None  # signed with another key
    assert google_auth.open_sealed("garbage", 120) is None


def test_safe_next_keeps_only_same_site_app_paths():
    assert safe_next("/app/learning") == "/app/learning"
    assert safe_next("/admin/users") == "/admin"
    for bad in (None, "", "https://evil.example", "//evil.example", "/emergency", "/app\\x"):
        assert safe_next(bad) == "/app/home"
