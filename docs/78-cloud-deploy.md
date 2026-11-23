# Deploying OneStats to the cloud (containerised backend + managed PostgreSQL)

This is the final cloud-prep step after [docs/77-web-app.md](77-web-app.md). It packages the whole app
(backend + built SPA, one origin) into a single container image and runs it against a managed PostgreSQL
and (optionally) S3-compatible object storage — removing the dependency on a home PC.

> The `Dockerfile` and `docker-compose.yml` were authored in a dev environment **without** Docker. You do
> **not** need Docker on your own PC to build the image: the `Docker image` GitHub Actions workflow
> (`.github/workflows/docker-image.yml`) builds it in the cloud on every PR and push to `main` — see
> [Build it in CI](#build-it-in-ci-no-local-docker) below. The local commands here are the equivalent flow
> if you do have Docker.

## What's in the image

`Dockerfile` is multi-stage:
1. **frontend** (node) — builds the SPA with an empty `VITE_ONESTATS_API_URL`, so it calls the API
   relative to its own origin.
2. **backend** (python:3.12-slim) — installs the backend with the `s3` extra (`pip install .[s3]`) and
   `tesseract-ocr`, copies the built SPA in, sets `ONESTATS_SERVE_FRONTEND=true`, and on start runs
   `alembic upgrade head` then serves the app on `:8000` (`docker/entrypoint.sh`).

Result: one image = the entire OneStats web app on one origin.

## Try it locally (cloud-like)

Create a `.env` beside `docker-compose.yml`:

```
ONESTATS_DB_PASSWORD=choose-a-strong-password
ONESTATS_ENCRYPTION_KEY=<a persistent key for secrets-at-rest>
```

Then:

```bash
docker compose up --build
```

Open `http://localhost:8000/`. The `db` service is a local PostgreSQL; the `api` service migrates and
serves. This compose file is a **convenience/template**, not a hardened setup.

## Build it in CI (no local Docker)

If you'd rather not install Docker locally, GitHub Actions builds the image for you — free for this repo:

- The **`Docker image`** workflow (`.github/workflows/docker-image.yml`) runs automatically.
  - On **every** run it **builds** the image and then **smoke-tests** it: it starts the container against
    a throwaway Postgres, lets the entrypoint run `alembic upgrade head`, and asserts the API is live
    (`/api/v1/health`), the database is reachable (`/api/v1/health/db` → `database_connected:true`), and
    the SPA is served from the same origin (`GET /` → the app HTML). A container that does not boot fails
    the check.
  - On a **pull request** it stops there — nothing is published.
  - On a **push to `main`** (or a manual **Run workflow** / `workflow_dispatch`), it then **pushes** the
    tested image to **GitHub Container Registry** at `ghcr.io/<owner>/onestats-web`, tagged `latest` and
    with the commit SHA. Because the push happens only after the smoke test, a broken image is never
    published.
- No secrets to configure: it uses the built-in `GITHUB_TOKEN` (with `packages: write`).
- The published package appears under the repo's **Packages**; make it public or pull it while
  authenticated:
  ```bash
  docker pull ghcr.io/scotneyhayter-rgb/onestats-web:latest
  ```

A managed host can then pull that image directly — you never need Docker on your own machine.

## Going to a managed host

1. **Build & push the image** to your registry:
   ```bash
   docker build -t <registry>/onestats:<tag> .
   docker push <registry>/onestats:<tag>
   ```
2. **Managed PostgreSQL** (Neon / Supabase / RDS / Cloud SQL): point the backend at it with either the
   discrete settings (`ONESTATS_DB_HOST`, `ONESTATS_DB_NAME`, `ONESTATS_DB_USER`, `ONESTATS_DB_PASSWORD`,
   `ONESTATS_DB_PORT`) or a full `ONESTATS_DB_URL`. The entrypoint runs migrations on deploy.
3. **Object storage for media** (optional but recommended in the cloud): set the `ONESTATS_S3_*` values
   and `ONESTATS_MEDIA_PROVIDER=s3` so new uploads go straight to object storage (see docs/77). Migrate
   any existing internal media to `s3` via the media migration flow.
4. **Secrets**: provide `ONESTATS_ENCRYPTION_KEY` (and DB/S3 creds) through the platform's secret store,
   never baked into the image.
5. **HTTPS + domain**: terminate TLS at the platform's load balancer / ingress (or put Cloudflare in
   front). Bearer-token auth needs HTTPS in production.
6. Run the container; the platform health-checks `GET /` (or `/api/v1/health`).

## Production notes

- **Database roles**: this repo's design separates a least-privilege app role (`onestats_app`, used at
  runtime under FORCE RLS) from the migration/owner role. The local compose simplifies this (app role owns
  the schema); for a managed DB, create the owner + least-privilege roles per your platform and run
  migrations as the owner.
- **Stateless backend**: sessions live in the database, so you can run multiple replicas behind the load
  balancer. Media must be on object storage (not container-local disk) when running more than one replica.
- **Backups**: use the managed database's automated backups.
- **The desktop build is unaffected** by any of this — `serve_frontend` and the `s3` provider are both off
  unless configured.
