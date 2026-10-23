# Phones, Google sign-in and the public judges URL

Adopted on 2026-10-23 from the teammate's MudraAI repository (branch `M2`: Google sign-in, PWA manifest, Cloudflare
Worker tunnel) and adapted to this project. The recognition pipeline, model and desktop pages are unchanged.

## Who runs what

| | Server PC (Aakash) | Demo PC (localhost) |
|---|---|---|
| Starts | `start_judges.bat` | `start_all.bat` (or `start_judges.bat` to take over the public URL) |
| People open | the permanent Worker URL, `https://mudra-camera-gateway.aakashtribhuvan2006.workers.dev` | `http://localhost:3000` |
| Google sign-in | his OAuth client (`GOOGLE_CLIENT_ID` / `GOOGLE_CLIENT_SECRET` in `app/backend/.env`), admin emails in `SIGNLINE_ADMIN_EMAILS` | the same client ID and secret in the local `.env` when the public URL points here; otherwise the automatic local sign-in |

Secrets never go into Git: `app/backend/.env` and `tools/phone-camera-prototype/cloudflare/update-token.txt` are
ignored. `app/backend/.env.example` lists the names.

## Sign-in

- **Google first.** `Continue with Google` opens a popup on `/auth/google/start`; the server does OpenID Connect
  with PKCE, state and nonce (`app/backend/mudra_api/google_auth.py`), verifies the ID token and sets a signed,
  HTTP-only cookie (`signline_session`, 14 days). The popup reports the result to the page (`postMessage` and a
  `BroadcastChannel`) and closes; the page reads `/auth/me`. A blocked popup runs Google in the same tab instead.
- **Automatic fallback.** When Google is not configured on the server (`/auth/me` says `google_configured: false`),
  or the popup is cancelled or fails, a learner is signed in locally at once (`signline_demo_session` in
  `localStorage`, as before) and lands on the home page. The admin workspace never falls back: it needs a Google
  account listed in `SIGNLINE_ADMIN_EMAILS`.
- **User card.** Next to Sign out (desktop sidebar, phone menu): the Google photo, name and email with a "Google user"
  pill, or the initial and "Local user". Sign out clears both the cookie (`POST /auth/logout`) and the local session.
- **One origin.** The Vite dev server and `vite preview` proxy the API (`/health`, `/stream`, `/auth`, …) to the
  backend (`vite.config.js`, port 8000 or `MUDRA_PORT`), so the page and the cookie share one origin on a phone and
  through the tunnel. `VITE_API_URL` still points the app at a backend directly (the development setup here).
- Google Cloud Console: the OAuth Web client must list both `http://localhost:3000/auth/google/callback` and
  `https://mudra-camera-gateway.aakashtribhuvan2006.workers.dev/auth/google/callback` as redirect URIs.

Endpoints: `GET /auth/me` → `{user: {email, name, picture, role} | null, google_configured}`;
`GET /auth/google/start?next=/app/home`; `GET /auth/google/callback`; `POST /auth/logout`.
Tests: `app/backend/tests/test_google_auth.py` (11, Google stubbed), `app/frontend/src/services/__tests__/googleSignIn.test.js`
and `session.test.js`.

## Phones

- The site is a PWA (`public/manifest.webmanifest`, icons in `public/brand/`): Android Chrome → menu → **Install app**;
  iPhone Safari → Share → **Add to Home Screen**. Phone cameras need HTTPS, which the Worker URL provides.
- On a phone held upright, Communication asks for a portrait camera stream (480×854) instead of 640×480, so the
  signer is not cropped; the overlay canvas follows the picture's size (`handTracker.fitCanvas`). **Recognition
  accuracy with a portrait stream is not measured** (the benchmark webcam is landscape); a phone test is next.
- The phone layout of Communication (tall camera, detected sign and meaning under it) is from 2026-10-23
  (`CommunicatePage.jsx`, below 768 px).

## The public judges URL (Cloudflare)

`tools/phone-camera-prototype/cloudflare/worker.js` is a Cloudflare Worker (deployed once by Aakash with
`configure-worker.ps1`, config `wrangler.jsonc`) that proxies the permanent URL to whichever temporary Quick Tunnel
was registered last (`POST /__update` with the bearer token). `tools/start_judges_tunnel.ps1` opens the Quick Tunnel
to `http://127.0.0.1:3000`, waits until it serves `/health`, registers it, and keeps running until the window is
closed. Whoever runs it last owns the public URL; the previous PC's visitors see "SignLine is offline".

`start_judges.bat` = `start_all.bat judges`: backend on `MUDRA_PORT` (8000), `npm run build`, `vite preview` on all
interfaces with the proxy and `MUDRA_PUBLIC_TUNNEL=1` (allowed host `.trycloudflare.com`), then the tunnel script.
Needs `cloudflared` (`winget install --id Cloudflare.cloudflared`) and the token file.

Measured on 2026-10-23 from the demo PC (backend on 8010): the Worker URL served the built app, the manifest, `/health`,
`/labels` (339) and `/auth/me` from one HTTPS origin; the sign-in fallback landed on `/app/home`; the `/stream`
websocket opened through the Worker. The *development* server through the tunnel showed a blank page for minutes
(each of its module requests is a round trip), which is why the launcher serves the build.
