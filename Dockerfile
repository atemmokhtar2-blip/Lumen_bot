# Multi-stage production image: Wolfi runtime keeps build tooling out of the final image.
# Python 3.12 and runtime libraries are installed from the patched Wolfi package repository.
FROM cgr.dev/chainguard/wolfi-base:latest AS builder

RUN apk add --no-cache python-3.12 py3.12-pip build-base

ENV VIRTUAL_ENV=/opt/venv \
    PATH="/opt/venv/bin:$PATH" \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app
RUN python3.12 -m venv "$VIRTUAL_ENV"

COPY requirements.txt requirements.lock ./
RUN python -m pip install --no-cache-dir --upgrade --force-reinstall pip==26.3 setuptools==84.1.0 \
    && python -m pip install --no-cache-dir -r requirements.lock \
    && python -c "import pip, setuptools; from packaging.version import Version; assert Version(setuptools.__version__) >= Version('84.1.0'), setuptools.__version__; print('pip', pip.__version__, 'setuptools', setuptools.__version__)"

COPY . .
RUN mkdir -p /tmp/lumen_output \
    && chown -R 65532:65532 /app /opt/venv /tmp/lumen_output

# Runtime contains Python and shared libraries only; no compiler, pip, apk, or shell tooling.
FROM cgr.dev/chainguard/wolfi-base:latest AS runtime

RUN apk add --no-cache python-3.12 ca-certificates-bundle libstdc++ libgcc libgomp

ENV VIRTUAL_ENV=/opt/venv \
    PATH="/opt/venv/bin:$PATH" \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    OUTPUT_DIR=/tmp/lumen_output

WORKDIR /app
COPY --from=builder /opt/venv /opt/venv
COPY --from=builder /app /app
RUN mkdir -p /tmp/lumen_output \
    && chown -R 65532:65532 /app /opt/venv /tmp/lumen_output

USER 65532:65532

EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=5s --start-period=40s --retries=3 \
  CMD ["/opt/venv/bin/python", "-c", "import os, urllib.request; urllib.request.urlopen('http://127.0.0.1:%s/health' % os.getenv('PORT', '8080'), timeout=4)"]

CMD ["/opt/venv/bin/python", "main.py"]
