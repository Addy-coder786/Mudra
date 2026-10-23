# Cloudflare Worker for the public judges URL

From the teammate's MudraAI repository (`M2`), unchanged; see `docs/MOBILE_AND_JUDGES.md`.

| File | Purpose |
|---|---|
| `worker.js` | The Worker behind `https://mudra-camera-gateway.aakashtribhuvan2006.workers.dev`: proxies every request (websockets included) to the Quick Tunnel registered last; `POST /__update` (bearer token) sets that tunnel. |
| `wrangler.jsonc` | Its deployment config (Durable Object `TunnelState` keeps the current tunnel). |
| `configure-worker.ps1` | One-time deployment from the Cloudflare account that owns the Worker (`npx wrangler`), and the update token as a Worker secret. |
| `update-token.txt` | The local copy of that token, read by `tools/start_judges_tunnel.ps1`. **Git-ignored; never commit it.** |

The folder name is kept so the teammate's instructions and token path keep working; the rest of his phone-camera
prototype (a Python Camo-webcam tool) is not part of this repository.
