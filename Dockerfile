# Production image — hardened (Phase 3 + Phase 4 policy)
FROM python:3.12-slim-trixie

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
    && apt-get upgrade -y --no-install-recommends \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd --gid 10001 appuser \
    && useradd --uid 10001 --gid appuser --shell /usr/sbin/nologin --create-home appuser

COPY requirements.txt requirements.lock ./
RUN python -m pip install --no-cache-dir --upgrade --force-reinstall pip==26.3 setuptools==84.1.0 \
    && python -m pip install --no-cache-dir -r requirements.lock \
    && python -c "import pip, setuptools; from packaging.version import Version; assert Version(setuptools.__version__) >= Version('84.1.0'), setuptools.__version__; print('pip', pip.__version__, 'setuptools', setuptools.__version__)" \
    && mkdir -p /tmp/lumen_output \
    && chown -R appuser:appuser /app /tmp/lumen_output

COPY . .

USER appuser

# Tokens MUST come from runtime env — never build args / image layers.
EXPOSE 8080

# Liveness for orchestrators + satisfies policy engines requiring HEALTHCHECK
HEALTHCHECK --interval=30s --timeout=5s --start-period=40s --retries=3 \
  CMD python -c "import os, urllib.request; urllib.request.urlopen('http://127.0.0.1:%s/health' % os.getenv('PORT', '8080'), timeout=4)"

CMD ["python", "main.py"]
