# OneStats — single-image deployment: the FastAPI backend serving the built SPA from one origin.
#
# Stage 1 builds the React/Vite frontend with an empty API URL (so it calls the API relative to its own
# origin). Stage 2 is the Python runtime: it installs the backend (plus the s3 extra for object storage),
# copies the built SPA in, runs migrations on start, then serves the whole app on :8000.
#
# NOTE: this image was authored but not `docker build`-tested in the dev environment; review/iterate on a
# machine with Docker. See docs/78-cloud-deploy.md.

# --- Stage 1: build the SPA -----------------------------------------------------------------------
FROM node:20-bookworm-slim AS frontend
WORKDIR /app/apps/desktop
# install deps against the lockfile first (better layer caching)
COPY apps/desktop/package.json apps/desktop/package-lock.json ./
RUN npm ci
COPY apps/desktop/ ./
# empty API URL → the SPA uses a relative API base (same origin as the backend serves it)
ENV VITE_ONESTATS_API_URL=""
RUN npm run build        # → /app/apps/desktop/dist

# --- Stage 2: Python backend ----------------------------------------------------------------------
FROM python:3.12-slim-bookworm AS backend
ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1
# tesseract is optional — installed so Research Centre OCR works in the cloud too (the code still falls
# back to manual transcription if it is ever absent).
RUN apt-get update \
    && apt-get install -y --no-install-recommends tesseract-ocr \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app/services/api
# install the backend + S3 support (object storage). pyproject/alembic live beside the source.
COPY services/api/ ./
RUN pip install ".[s3]"

# bring in the built SPA and serve it from one origin
COPY --from=frontend /app/apps/desktop/dist /app/frontend
ENV ONESTATS_SERVE_FRONTEND=true \
    ONESTATS_FRONTEND_DIST=/app/frontend \
    PORT=8000

# migrate-then-serve
COPY docker/entrypoint.sh /app/entrypoint.sh
RUN chmod +x /app/entrypoint.sh

EXPOSE 8000
ENTRYPOINT ["/app/entrypoint.sh"]
