# Production image — hardened for Phase 3 supply-chain admission
# - slim base, no apt bloat
# - non-root runtime user
# - no secrets baked in (tokens via env at runtime only)
FROM python:3.12-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    OUTPUT_DIR=/tmp/capability_maestro_output \
    PATH="/home/appuser/.local/bin:$PATH"

WORKDIR /app

# System: only CA certs (TLS). No compilers in final image.
RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd --gid 10001 appuser \
    && useradd --uid 10001 --gid appuser --shell /usr/sbin/nologin --create-home appuser

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt \
    && mkdir -p /tmp/capability_maestro_output \
    && chown -R appuser:appuser /app /tmp/capability_maestro_output

COPY --chown=appuser:appuser . .

USER appuser

# Tokens (TELEGRAM_BOT_TOKEN, PLATFORM_ADMIN_TOKEN, …) MUST come from runtime env — never build args.
EXPOSE 8080
CMD ["python", "main.py"]
