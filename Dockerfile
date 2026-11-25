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
    HOME=/home/appuser \
    PATH="/home/appuser/.local/bin:$PATH"

# Apply Trixie updates, then pin only the Sid security-fixed runtime packages.
RUN apt-get update \
    && apt-get upgrade -y --no-install-recommends \
    && printf 'deb http://deb.debian.org/debian sid main\n' > /etc/apt/sources.list.d/sid.list \
    && apt-get update \
    && apt-get -t sid install -y --no-install-recommends \
        ncurses-bin=6.6+20260608-2 \
        libsqlite3-0=3.54.1-2 \
        libudev1=262.2-1 \
        libacl1=2.4.0-1 \
        util-linux=2.42.4-1 \
        perl-base=5.44.0-3 \
        dpkg=1.23.12 \
        libc6=2.43-7 \
        libc-bin=2.43-7 \
        libseccomp2=2.6.2-1 \
        openssl-provider-legacy=3.6.5-1 \
        account-utils=1.4.0-1 \
        account-utils-passwd=1.4.0-1 \
    && rm -f /etc/apt/sources.list.d/sid.list \
    && dpkg-query -W -f='${Package}=${Version}\\n' \
        ncurses-bin libsqlite3-0 libudev1 libacl1 util-linux perl-base dpkg libc6 libc-bin libseccomp2 account-utils account-utils-passwd \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Use a fixed numeric non-root identity; no account-management utilities needed.
RUN mkdir -p /home/appuser \
    && chown 10001:10001 /home/appuser

COPY requirements.txt requirements.lock ./
RUN pip install --no-cache-dir --upgrade pip==25.3 setuptools==84.2.1 \
    && pip install --no-cache-dir -r requirements.lock \
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
