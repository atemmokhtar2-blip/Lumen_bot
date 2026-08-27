# Production image — hardened (Phase 3 + Phase 4 policy)
FROM python:3.12-slim-bookworm

LABEL org.opencontainers.image.source="https://github.com/atemmokhtar2-blip/Lumen_bot" \
      org.opencontainers.image.title="Lumen" \
      org.opencontainers.image.description="Multi-tenant bot generation API"

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    OUTPUT_DIR=/tmp/lumen_output \
    PATH="/home/appuser/.local/bin:$PATH"

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        ca-certificates curl \
        libcurl4-openssl-dev libssl-dev \
        gcc g++ make \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd --gid 10001 appuser \
    && useradd --uid 10001 --gid appuser --shell /usr/sbin/nologin --create-home appuser

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt \
    && mkdir -p /tmp/lumen_output \
    && chown -R appuser:appuser /app /tmp/lumen_output

COPY --chown=appuser:appuser . .

USER appuser

# Tokens MUST come from runtime env — never build args / image layers.
EXPOSE 8080

# Liveness for orchestrators + satisfies policy engines requiring HEALTHCHECK
HEALTHCHECK --interval=30s --timeout=5s --start-period=40s --retries=3 \
  CMD curl -fsS "http://127.0.0.1:${PORT:-8080}/health" || exit 1

CMD ["python", "main.py"]
