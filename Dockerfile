# Multi-stage production image:
# - Build Python 3.12 dependencies on the official Debian 13 Python image.
# - Run on Google's minimal, non-root Distroless Debian 13 Python runtime.
# The builder, pip, package manager, and build tooling are not shipped.
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

# Distroless Debian 13 supplies only the runtime filesystem and CA trust store.
# Copy the official CPython 3.12 installation and its installed application
# dependencies from the matching Debian 13 builder.
FROM gcr.io/distroless/python3-debian13:nonroot AS runtime

LABEL org.opencontainers.image.source="https://github.com/atemmokhtar2-blip/Lumen_bot" \
      org.opencontainers.image.title="Lumen" \
      org.opencontainers.image.description="Multi-tenant bot generation API"

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    OUTPUT_DIR=/tmp/lumen_output \
    HOME=/home/appuser \
    PATH="/usr/local/bin:/usr/bin"

WORKDIR /app

COPY --from=builder /usr/local /usr/local
COPY --from=builder --chown=65532:65532 /home/appuser /home/appuser
COPY --from=builder --chown=65532:65532 /tmp/lumen_output /tmp/lumen_output
COPY --chown=65532:65532 . .

USER 65532:65532

EXPOSE 8080

# Exec-form healthcheck works without a shell in the Distroless runtime.
HEALTHCHECK --interval=30s --timeout=5s --start-period=40s --retries=3 \
  CMD ["/usr/local/bin/python3.12", "-c", "import os, urllib.request; urllib.request.urlopen('http://127.0.0.1:%s/health' % os.getenv('PORT', '8080'), timeout=4)"]

ENTRYPOINT ["/usr/local/bin/python3.12"]
CMD ["main.py"]
