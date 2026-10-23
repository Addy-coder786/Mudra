import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// The recognition server (app/backend): port 8000, or MUDRA_PORT as for the backend itself
const backend = `http://127.0.0.1:${process.env.MUDRA_PORT || 8000}`

// The API on the page's own origin: the sign-in cookie needs it, and a phone or tunnel visitor reaches one address
// only. With VITE_API_URL set, the app talks to the backend directly instead (development default on this PC).
const proxy = {
  '^/(health|model|models|labels|predict|stream|recordings|reference|library|letters|phrases|events|speech|tts|asr|captions|auth|api|docs|openapi\\.json)(/|$)': {
    target: backend,
    changeOrigin: true,
    ws: true,
  },
}
// Public preview through a Cloudflare Quick Tunnel (tools/start_judges_tunnel.ps1): its host names change on every
// start, so only the tunnel domain is allowed, and only when the judges launcher asks for it.
const allowedHosts = process.env.MUDRA_PUBLIC_TUNNEL === '1' ? ['.trycloudflare.com'] : undefined

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  server: { port: 3000, open: false, allowedHosts, proxy },
  // `vite preview` serves the production build with the same proxy: the judges launcher uses it, because the
  // development server's hundreds of small module requests take minutes through a tunnel
  preview: { port: 3000, allowedHosts, proxy },
})
