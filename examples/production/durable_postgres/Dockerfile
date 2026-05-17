# syntax=docker/dockerfile:1.7
# Pin base image by digest, not tag (spec §5.1, advisor #1).
# Refresh digest quarterly OR on CVE alert. Document version in README.
#
# To find the current digest:
#   docker pull python:3.11-slim
#   docker inspect python:3.11-slim --format='{{index .RepoDigests 0}}'
#
FROM python:3.11-slim@sha256:9a7765b36773a37061455b332f18e265e7f58f6fea9c419a550d2a8b0e9db834

# Non-root user (UID 10001, no shell, no home write).
RUN groupadd -r app -g 10001 && \
    useradd -r -u 10001 -g app -m -s /sbin/nologin appuser

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# Stage 1: install pinned third-party deps (hash-checked, wheel-only).
# Build context is repo root (see compose service.build.context).
COPY examples/production/durable_postgres/requirements.txt /tmp/requirements.txt
RUN pip install --require-hashes --only-binary=:all: -r /tmp/requirements.txt && \
    rm /tmp/requirements.txt

# Stage 2: install the library from local source.
# --no-deps prevents re-resolving the locked third-party deps.
# --no-build-isolation uses the already-installed build backend.
# Migrates to PyPI install once adv-multi-agent ships (spec §2.7).
COPY pyproject.toml /repo/pyproject.toml
COPY src/ /repo/src/
RUN pip install --no-deps --no-build-isolation /repo

# Stage 3: app code (excluding .env via .dockerignore).
COPY --chown=appuser:app examples/production/durable_postgres/ /app/

USER appuser

# Healthcheck port (internal network only; not exposed to host).
EXPOSE 8080

# No core dumps. Default cmd is the daemon entry point.
ENTRYPOINT ["sh", "-c", "ulimit -c 0 && exec python -m daemon"]
