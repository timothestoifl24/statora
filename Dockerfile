# syntax=docker/dockerfile:1

ARG PYTHON_VERSION=3.15.0

# ---- build: Python + dependencies in a virtualenv ----------------------------------------------
FROM docker.io/library/debian:trixie-slim AS build
ARG PYTHON_VERSION
COPY --from=ghcr.io/astral-sh/uv:0.13.0 /uv /usr/local/bin/uv

# xmlsec (SAML) and lxml are compiled against the same system libxml2: xmlsec has no wheels for
# every Python version, and mixing lxml's bundled libxml2 with a system one breaks at runtime.
RUN apt-get update \
 && apt-get install -y --no-install-recommends ca-certificates build-essential pkg-config \
      libxml2-dev libxslt1-dev zlib1g-dev libxmlsec1-dev libxmlsec1-openssl \
 && rm -rf /var/lib/apt/lists/*

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_INSTALL_DIR=/opt/python \
    UV_PYTHON_PREFERENCE=only-managed
RUN uv python install "${PYTHON_VERSION}"

WORKDIR /app
COPY pyproject.toml uv.lock README.md ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --extra saml --no-install-project --python "${PYTHON_VERSION}" \
      --no-binary-package xmlsec --no-binary-package lxml

COPY src ./src
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --extra saml --no-editable --python "${PYTHON_VERSION}" \
      --no-binary-package xmlsec --no-binary-package lxml

# Drop debug symbols and build-only files (headers, man pages) to keep the runtime image small.
RUN find /app/.venv /opt/python -type f \( -name '*.so' -o -name '*.so.*' \) -exec strip --strip-unneeded {} + \
 && find /opt/python/*/bin -type f -name 'python3.*' ! -name '*-config' -exec strip --strip-unneeded {} + \
 && rm -rf /opt/python/*/include /opt/python/*/share

# ---- runtime ---------------------------------------------------------------------------------
FROM docker.io/library/debian:trixie-slim
LABEL org.opencontainers.image.title="statora" \
      org.opencontainers.image.description="Self-hosted uptime monitoring and status pages"

# Shared libraries only (no compilers): libxml2/libxslt for lxml, libxmlsec1 for SAML.
RUN apt-get update \
 && apt-get install -y --no-install-recommends ca-certificates libxml2 libxslt1.1 libxmlsec1 libxmlsec1-openssl \
 && rm -rf /var/lib/apt/lists/* \
 && useradd --system --uid 10001 --no-create-home --home-dir /app statora

WORKDIR /app
# The virtualenv links to the interpreter, so both keep the paths they were built with.
COPY --from=build /opt/python /opt/python
COPY --from=build /app/.venv /app/.venv

ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    STATORA_HOST=0.0.0.0 \
    STATORA_PORT=8000 \
    FORWARDED_ALLOW_IPS="*"

USER statora
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
    CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/healthz', timeout=4)"]

ENTRYPOINT ["statora"]
CMD ["serve"]
