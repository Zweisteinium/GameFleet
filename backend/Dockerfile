# Builder stage - resolve and install dependencies into /app/.venv
FROM python:3.14-slim AS builder

# uv from the official image; pin it so builds are reproducible.
COPY --from=ghcr.io/astral-sh/uv:0.12.10 /uv /uvx /bin/

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy

WORKDIR /app
COPY pyproject.toml uv.lock alembic.ini ./
COPY src/ ./src/
RUN uv sync --frozen --no-dev

# Production stage - only the runtime, no uv or pip needed
FROM python:3.14-slim AS prod

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PATH="/app/.venv/bin:$PATH"

WORKDIR /app
COPY --from=builder /app/.venv /app/.venv
COPY src/ ./src/
EXPOSE 8000
CMD ["uvicorn", "gamefleet_backend.main:app", "--host", "0.0.0.0", "--port", "8000"]
