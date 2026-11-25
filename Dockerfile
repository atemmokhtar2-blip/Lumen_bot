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

# Apply Trixie updates, then pin only the Sid security-fixed runtime packages.
RUN apt-get update \
    && apt-get upgrade -y --no-install-recommends \
    && printf 'deb http://deb.debian.org/debian sid main\n' > /etc/apt/sources.list.d/sid.list \
    && apt-get update \
    && apt-get install -y --no-install-recommends -t sid \
        ncurses-bin=6.6+20260608-2 \
        openssl-provider-legacy=3.6.5-1 \
        libsqlite3-0=3.54.1-2 \
        libudev1=262.2-1 \
        libacl1=2.4.0-1 \
        util-linux=2.42.4-1 \
        perl-base=5.44.0-3 \
    && rm -f /etc/apt/sources.list.d/sid.list \
    && dpkg-query -W -f='${Package}=${Version}\\n' \
        ncurses-bin openssl-provider-legacy libsqlite3-0 libudev1 libacl1 util-linux perl-base \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

RUN groupadd --gid 10001 appuser \
    && useradd --uid 10001 --gid appuser --shell /usr/sbin/nologin --create-home appuser

COPY requirements.txt requirements.lock ./
RUN pip install --no-cache-dir --upgrade pip==25.3 setuptools==84.2.1 \
    && pip install --no-cache-dir -r requirements.lock \
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
