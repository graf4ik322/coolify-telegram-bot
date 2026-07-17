# ── Builder stage ─────────────────────────────────────────────────────────────
FROM python:3.12-alpine AS builder

WORKDIR /app
COPY pyproject.toml .

RUN pip install --no-cache-dir uv \
    && uv venv /venv \
    && . /venv/bin/activate \
    && uv pip install --no-cache-dir ".[dev]"

# ── Runtime stage ────────────────────────────────────────────────────────────
FROM python:3.12-alpine AS runtime

RUN apk add --no-cache tini

WORKDIR /app
RUN mkdir -p /app/data
COPY --from=builder /venv /venv
COPY bot/ ./bot/

ENV PATH="/venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=10s --start-period=10s --retries=3 \
    CMD wget --no-verbose --tries=1 --spider http://localhost:8080/health || exit 1

ENTRYPOINT ["/sbin/tini", "--"]
CMD ["python", "-m", "bot.main"]
