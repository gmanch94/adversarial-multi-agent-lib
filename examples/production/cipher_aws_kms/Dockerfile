# syntax=docker/dockerfile:1.7
# Pin base image by digest, not tag. Refresh digest quarterly OR on CVE alert.
FROM python:3.11-slim@sha256:9a7765b36773a37061455b332f18e265e7f58f6fea9c419a550d2a8b0e9db834

RUN groupadd -r app -g 10001 && \
    useradd -r -u 10001 -g app -m -s /sbin/nologin appuser

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    AWS_EC2_METADATA_V1_DISABLED=true

# Stage 1: pinned third-party deps. Operator runs pip-compile to produce
# requirements.txt with hashes before image build.
COPY examples/production/cipher_aws_kms/requirements.txt /tmp/requirements.txt
RUN pip install --require-hashes --only-binary=:all: -r /tmp/requirements.txt && \
    rm /tmp/requirements.txt

# Stage 2: library from local source.
COPY pyproject.toml /repo/pyproject.toml
COPY src/ /repo/src/
RUN pip install --no-deps --no-build-isolation /repo

# Stage 3: app code (excluding .env via .dockerignore).
COPY --chown=appuser:app examples/production/cipher_aws_kms/ /app/
# Sibling import: daemon does `from ..cipher_gcp_kms.cipher import GcpKmsCipher`
# for migration support. Copy that single module path too.
COPY --chown=appuser:app examples/production/cipher_gcp_kms/cipher.py /app/../cipher_gcp_kms/cipher.py
COPY --chown=appuser:app examples/production/cipher_gcp_kms/__init__.py /app/../cipher_gcp_kms/__init__.py
COPY --chown=appuser:app examples/production/cipher_gcp_kms/dek_cache.py /app/../cipher_gcp_kms/dek_cache.py
COPY --chown=appuser:app examples/production/durable_postgres/ /app/../durable_postgres/

USER appuser

EXPOSE 8080

ENTRYPOINT ["sh", "-c", "ulimit -c 0 && exec python -m daemon"]
