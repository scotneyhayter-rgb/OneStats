# Deploying OneStats to Render (free tier)

This is a concrete, copy-paste path to put OneStats fully in the cloud — no home PC, no local Docker — on
[Render](https://render.com). It uses the repo's [`render.yaml`](../render.yaml) Blueprint: a web service
that builds the [Dockerfile](../Dockerfile) (backend + built SPA on one origin) plus a managed PostgreSQL.

It builds on [docs/77-web-app.md](77-web-app.md) and [docs/78-cloud-deploy.md](78-cloud-deploy.md); read
those for the architecture. Nothing here affects the desktop build.

## Before you start

- A free Render account (sign in with GitHub).
- This repo on GitHub (it is) with `render.yaml` on the branch you'll deploy (merge the PR that adds it).
- Two secrets you'll generate below. You do **not** need Docker installed.

## 1. Create the Blueprint

1. In Render: **New** → **Blueprint**.
2. Connect this GitHub repo and pick the branch (`main`).
3. Render reads `render.yaml` and shows two resources to create: the **onestats-web** web service and the
   **onestats-db** PostgreSQL. Approve it.
   - Optional: change the `region` in `render.yaml` (and keep the DB in the **same** region) before this
     step if Oregon isn't nearest you.

## 2. Set the two secrets

The Blueprint marks these `sync: false`, so Render asks you to fill them in (they never live in git). On the
**onestats-web** service → **Environment**:

- **`ONESTATS_ENCRYPTION_KEY`** — encrypts stored integration credentials (Trove / PlayHQ) at rest.
  Generate a Fernet key:
  ```bash
  python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
  ```
- **`ONESTATS_SETUP_TOKEN`** — a strong, one-time value **you choose** to create the first Super Admin.
  ```bash
  openssl rand -hex 24
  ```
  (Render's filesystem is ephemeral, so the usual first-run token *file* can't be read — supplying the
  token via this env var is the headless equivalent. Only its hash is stored; it's never logged.)

The database env vars (`ONESTATS_DB_*`) are wired automatically from the managed Postgres — leave them.

## 3. Deploy and watch it boot

Render builds the image (first build ~5–10 min) and starts the container. In the service **Logs** you'll
see the entrypoint run migrations then serve:

```
OneStats: applying database migrations...
OneStats: starting server on :10000
```

When the health check (`/api/v1/health`) goes green, open the service URL
(`https://onestats-web-xxxx.onrender.com`). The app loads over HTTPS from one origin.

## 4. First-run setup (create the Super Admin)

1. On the loaded app, go through first-run setup.
2. Enter the **setup token** = the `ONESTATS_SETUP_TOKEN` value you set, and choose an admin username +
   strong password.
3. On success the token is consumed (its hash is cleared). **Remove `ONESTATS_SETUP_TOKEN`** from the
   service environment — it's no longer needed.

You're live. Add users and workspaces from the admin area as normal.

## Free-tier caveats (and how to remove them)

- **The web service sleeps after ~15 min idle** and cold-starts on the next request (~1 minute). Fine for a
  club; upgrade the web service to a paid instance (from ~US$7/mo) to keep it always-on.
- **Render's free PostgreSQL is suspended after 30 days.** Two options:
  - Upgrade the `onestats-db` to a paid plan (from ~US$7/mo), **or**
  - Use a non-expiring free Postgres such as **[Neon](https://neon.tech)**: create a database there, then
    on the web service set `ONESTATS_DB_HOST`, `ONESTATS_DB_PORT`, `ONESTATS_DB_NAME`, `ONESTATS_DB_USER`,
    `ONESTATS_DB_PASSWORD` to Neon's values (and delete the `databases:` block from `render.yaml` so Render
    doesn't create its own). The app assembles the connection itself, so Neon's host/credentials are all it
    needs.
- **Uploaded media does not persist on free.** The container disk is ephemeral, so `internal` media is lost
  on redeploy/restart. For durable media set the `ONESTATS_S3_*` vars and `ONESTATS_MEDIA_PROVIDER=s3`
  (Cloudflare **R2** has a free 10 GB S3-compatible tier) — see docs/78. Logos/photos/scans then live in
  object storage, independent of the container.

## Updating

With `autoDeploy: true`, every push to the connected branch triggers a rebuild and redeploy; the entrypoint
re-runs `alembic upgrade head`, so schema changes apply automatically. To deploy a specific tested image
instead of rebuilding, you can later switch the service to pull `ghcr.io/scotneyhayter-rgb/onestats-web`
(published by the `Docker image` workflow) — but the Dockerfile build above needs no extra setup.

## Notes

- One origin ⇒ **no CORS** to configure. HTTPS is provided by Render.
- Sessions live in the database, so the service is stateless; you can scale to multiple instances on a paid
  plan (put media on S3/R2 first — required when running more than one instance).
- Back up the database with Render's (or Neon's) automated backups.
