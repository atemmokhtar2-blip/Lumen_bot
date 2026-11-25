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
    HOME=/home/appuser \
    PATH="/home/appuser/.local/bin:$PATH"

# Use the Debian Bookworm slim runtime while Trixie advisories remain unpatched.
# Keep the runtime on one supported Debian release; never mix suites.
RUN apt-get update \
    && apt-get upgrade -y --no-install-recommends \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Use a fixed numeric non-root identity; no account-management utilities needed.
RUN mkdir -p /home/appuser \
    && chown 10001:10001 /home/appuser

COPY requirements.txt requirements.lock ./
# pip is a build-time installer; its vendored libraries are not runtime dependencies.
RUN pip install --no-cache-dir --upgrade pip==26.2.0 setuptools==84.2.1 \
    && pip install --no-cache-dir -r requirements.lock \
    && python -m pip uninstall -y pip \
    && python -c "import importlib.util; assert importlib.util.find_spec('pip') is None" \
    && mkdir -p /tmp/lumen_output \
    && chown -R 10001:10001 /app /tmp/lumen_output /home/appuser

COPY . .

USER 10001:10001

# Tokens MUST come from runtime env — never build args / image layers.
EXPOSE 8080

# Liveness for orchestrators + satisfies policy engines requiring HEALTHCHECK
HEALTHCHECK --interval=30s --timeout=5s --start-period=40s --retries=3 \
  CMD python -c "import os, urllib.request; urllib.request.urlopen('http://127.0.0.1:%s/health' % os.getenv('PORT', '8080'), timeout=4)"

CMD ["python", "main.py"]
