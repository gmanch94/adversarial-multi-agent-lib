# syntax=docker/dockerfile:1.7
# Mirrors examples/production/durable_postgres/Dockerfile with an extra
# install layer for OTel deps. Same base image digest, same non-root user,
# same hardening posture.
#
# To refresh the base digest:
#   docker pull python:3.11-slim
#   docker inspect python:3.11-slim --format='{{index .RepoDigests 0}}'
#
FROM python:3.11-slim@sha256:9a7765b36773a37061455b332f18e265e7f58f6fea9c419a550d2a8b0e9db834

RUN groupadd -r app -g 10001 && \
    useradd -r -u 10001 -g app -m -s /sbin/nologin appuser

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# Stage 1: install durable_postgres pinned deps (asyncpg, cryptography, ...)
COPY examples/production/durable_postgres/requirements.txt /tmp/dp-requirements.txt
RUN pip install --require-hashes --only-binary=:all: -r /tmp/dp-requirements.txt && \
    rm /tmp/dp-requirements.txt

# Stage 2: install OTel deps (hash-checked).
# Operator must generate requirements.txt via `pip-compile --generate-hashes`
# before building this image. CI does not exercise this path.
COPY examples/production/durable_postgres_otel/requirements.txt /tmp/otel-requirements.txt
RUN pip install --require-hashes --only-binary=:all: -r /tmp/otel-requirements.txt && \
    rm /tmp/otel-requirements.txt

# Stage 3: install the library from local source.
COPY pyproject.toml /repo/pyproject.toml
COPY src/ /repo/src/
RUN pip install --no-deps --no-build-isolation /repo

# Stage 4: app code from BOTH sibling directories (daemon.py imports both).
COPY --chown=appuser:app examples/production/durable_postgres/ /app/durable_postgres/
COPY --chown=appuser:app examples/production/durable_postgres_otel/ /app/durable_postgres_otel/

# Expose `examples.production.durable_postgres{,_otel}` as importable packages.
ENV PYTHONPATH=/app

USER appuser

EXPOSE 8080

ENTRYPOINT ["sh", "-c", "ulimit -c 0 && exec python -m durable_postgres_otel.daemon"]
