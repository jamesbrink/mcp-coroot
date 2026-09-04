# syntax=docker/dockerfile:1

FROM ghcr.io/astral-sh/uv:python3.13-bookworm-slim AS builder

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never

WORKDIR /app

# Install dependencies first so the layer is cached across source changes.
RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    uv sync --locked --no-install-project --no-dev

COPY pyproject.toml uv.lock README.md ./
COPY src/ ./src/

RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-dev


FROM python:3.13-slim-bookworm AS runtime

# stdout carries the MCP protocol on stdio; keep it unbuffered and clean.
ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    COROOT_BASE_URL=http://localhost:8080

RUN useradd --create-home --uid 1000 coroot
WORKDIR /app

COPY --from=builder --chown=coroot:coroot /app/.venv /app/.venv

USER coroot

# Credentials come from the environment at run time, never baked into the image:
#   COROOT_USERNAME / COROOT_PASSWORD, or COROOT_SESSION_COOKIE, or COROOT_API_KEY.
ENTRYPOINT ["mcp-coroot"]
