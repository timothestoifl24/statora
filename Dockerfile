# syntax=docker/dockerfile:1

# ---- build: resolve dependencies into a virtualenv -------------------------------------------
FROM docker.io/library/python:3.13-slim AS build
COPY --from=ghcr.io/astral-sh/uv:0.13.0 /uv /usr/local/bin/uv
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never
WORKDIR /app

COPY pyproject.toml uv.lock README.md ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --extra saml --no-install-project

COPY src ./src
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --extra saml --no-editable

# ---- runtime ---------------------------------------------------------------------------------
FROM docker.io/library/python:3.13-slim
LABEL org.opencontainers.image.title="statora" \
      org.opencontainers.image.description="Self-hosted uptime monitoring and status pages"

RUN useradd --system --uid 10001 --no-create-home --home-dir /app statora
WORKDIR /app
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
