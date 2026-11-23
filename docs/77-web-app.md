# Running OneStats as a web app (step 1: one origin on your PC)

OneStats is already a client/server app: a React/Vite single-page app (SPA) talking to a FastAPI +
PostgreSQL backend over a Bearer-token API. The desktop build just bundles them together. This guide
runs the **same code as a web app** — the backend serves the SPA and the API from **one origin**, so any
browser on your network can use it, with **no CORS** and nothing to install.

This is the first step toward a fully cloud-hosted deployment; see "Going cloud" at the end.

## What step 1 gives you

- `http://<your-pc>:8000/` serves the app; `http://<your-pc>:8000/api/...` serves the API — same origin.
- No installer, no per-machine updater: you deploy once, users just refresh.
- Multi-user already works (roles, per-workspace isolation, DB sessions).

It does **not** yet make your PC reachable from the public internet or add HTTPS — see "Reaching it from
elsewhere" for the safe way to do that.

## 1. Build the SPA for same-origin

Build the frontend with the API URL left **empty** so the app calls the API **relative to wherever it is
served** (i.e. the same origin):

```bash
cd apps/desktop
# PowerShell:  $env:VITE_ONESTATS_API_URL = ""
# bash:        export VITE_ONESTATS_API_URL=""
VITE_ONESTATS_API_URL= npm run build
```

This produces `apps/desktop/dist/` (the built SPA). The empty `VITE_ONESTATS_API_URL` makes the client
use a relative API base, so the same build works no matter the host or port.

## 2. Run the backend with web-app serving on

Set two environment variables and start the backend bound to all interfaces:

```bash
# tell the backend to serve the built SPA, and where it is
# PowerShell:
#   $env:ONESTATS_SERVE_FRONTEND = "true"
#   $env:ONESTATS_FRONTEND_DIST  = "C:\OneProjects\OneStats\apps\desktop\dist"
#   $env:ONESTATS_DB_PASSWORD    = "<your db password>"
# bash:
export ONESTATS_SERVE_FRONTEND=true
export ONESTATS_FRONTEND_DIST="$PWD/apps/desktop/dist"
export ONESTATS_DB_PASSWORD="<your db password>"

cd services/api
./.venv/Scripts/python -m uvicorn onestats.main:app --host 0.0.0.0 --port 8000
```

- `ONESTATS_SERVE_FRONTEND=true` turns on SPA serving (it is **off by default**, so the packaged desktop
  build and existing setups are unaffected). If the build folder is missing, the backend falls back to
  the JSON root rather than failing to start.
- `--host 0.0.0.0` lets other machines on your LAN reach it (omit for localhost-only).
- Keep PostgreSQL where it is; no data moves.

Open `http://localhost:8000/` (or `http://<your-pc-ip>:8000/` from another machine on the same network).
The whole app loads and signs in against the same origin.

### Run it always-on

Make the backend start with Windows and stay running. Either a **Startup shortcut** that runs the uvicorn
command above, or a service wrapper (e.g. [NSSM](https://nssm.cc/)) pointing at the same command. Keep the
PC awake (power settings → never sleep) so the app stays reachable.

## 3. Reaching it from elsewhere (securely)

**Do not port-forward a home PC to the internet.** Use a tunnel, which also gives you HTTPS (required once
auth tokens leave your LAN):

- **Tailscale** — best when the other users are a small known group. Installs a private mesh; they reach
  `http://<tailscale-name>:8000` with nothing exposed publicly.
- **Cloudflare Tunnel** — best for a public address like `https://yourclub.example`. Free, provides HTTPS
  and a stable hostname, and nothing on your PC is directly exposed.

Either way, once the app is reachable off-LAN: use HTTPS (the tunnel provides it), strong per-user
passwords, and automated PostgreSQL backups.

## Going cloud (later)

Design choices already in place that make a lift-and-shift easy when you want to drop the home-PC
dependency:

- **Config is all environment variables** (pydantic settings) — no code change to retarget.
- **Sessions live in the database**, not memory — the backend is stateless and horizontally scalable.
- **Migrations are Alembic** — run on deploy.
- **Media is behind a provider abstraction** — add an S3 / Cloudflare R2 provider to move uploads off the
  local disk.

The cloud move is then: containerize the backend, point `ONESTATS_DB_*` at a managed PostgreSQL, set the
media provider to object storage, and deploy. The SPA is unchanged (still same-origin, or point
`VITE_ONESTATS_API_URL` at the cloud API).

## Notes

- The desktop app is unaffected: `serve_frontend` defaults off, and the updater page simply detects it is
  running in a browser and hides the in-app updater.
- One origin means **no CORS configuration** is needed. If you instead host the SPA on a *different* origin
  (e.g. Netlify) pointing at this backend, add that origin to `ONESTATS_CORS_ORIGINS`.
