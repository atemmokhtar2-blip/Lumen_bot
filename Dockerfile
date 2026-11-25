# Multi-stage production image:
# - Build locked Python 3.12 dependencies on the official Debian 13 Python image.
# - Run on a freshly security-upgraded Debian 13 Python 3.12 image.
# - Keep the runtime non-root and remove Python packaging/build tooling.
FROM python:3.12-slim-trixie AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /build

COPY requirements.txt requirements.lock ./
RUN python -m pip install --no-cache-dir --upgrade pip==26.2.0 setuptools==84.2.1 \
    && python -m pip install --no-cache-dir -r requirements.lock \
    && python -m pip uninstall -y pip setuptools \
    && python -c "import importlib.util; assert importlib.util.find_spec('pip') is None" \
    && mkdir -p /tmp/lumen_output /home/appuser \
    && chown -R 65532:65532 /tmp/lumen_output /home/appuser

# Use the same official CPython 3.12 image family, but refresh every Debian
# runtime package from the configured security repositories during the build.
# This avoids inheriting the stale Python 3.13 runtime packages from Distroless.
FROM python:3.12-slim-trixie AS runtime

RUN apt-get update \
    && apt-get -y upgrade \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

LABEL org.opencontainers.image.source="https://github.com/atemmokhtar2-blip/Lumen_bot" \
      org.opencontainers.image.title="Lumen" \
      org.opencontainers.image.description="Multi-tenant bot generation API"

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    OUTPUT_DIR=/tmp/lumen_output \
    HOME=/home/appuser \
    PATH="/usr/local/bin:/usr/bin"

WORKDIR /app

# Copy the exact locked Python 3.12 environment built in the previous stage.
COPY --from=builder /usr/local /usr/local
COPY --from=builder --chown=65532:65532 /home/appuser /home/appuser
COPY --from=builder --chown=65532:65532 /tmp/lumen_output /tmp/lumen_output
COPY --chown=65532:65532 . .

# The base image ships pip; remove packaging tools from the final runtime.
RUN rm -rf /usr/local/lib/python3.12/site-packages/pip \
           /usr/local/lib/python3.12/site-packages/pip-*.dist-info \
           /usr/local/lib/python3.12/site-packages/setuptools \
           /usr/local/lib/python3.12/site-packages/setuptools-*.dist-info \
           /usr/local/lib/python3.12/site-packages/wheel \
           /usr/local/lib/python3.12/site-packages/wheel-*.dist-info \
           /usr/local/bin/pip /usr/local/bin/pip3 /usr/local/bin/pip3.12 \
    && /usr/local/bin/python3.12 -c "import importlib.util; assert importlib.util.find_spec('pip') is None"

RUN chown -R 65532:65532 /app /home/appuser /tmp/lumen_output

USER 65532:65532

EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=5s --start-period=40s --retries=3 \
  CMD ["/usr/local/bin/python3.12", "-c", "import os, urllib.request; urllib.request.urlopen('http://127.0.0.1:%s/health' % os.getenv('PORT', '8080'), timeout=4)"]

ENTRYPOINT ["/usr/local/bin/python3.12"]
CMD ["main.py"]
