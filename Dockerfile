# Multi-stage production image: Wolfi runtime keeps build tooling out of the final image.
# Python 3.12 and runtime libraries are installed from the patched Wolfi package repository.
FROM cgr.dev/chainguard/wolfi-base@sha256:6ab86c5e059da41ff1454b6f69ecd7422b94af41969f4e231aa23244e47d4a81 AS builder

RUN apk add --no-cache \
    python-3.12=3.12.16_git20261116-r0 \
    py3.12-pip=26.2.2-r3 \
    py3.12-setuptools=84.2.1-r1 \
    build-base=1-r11

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
FROM cgr.dev/chainguard/wolfi-base@sha256:6ab86c5e059da41ff1454b6f69ecd7422b94af41969f4e231aa23244e47d4a81 AS runtime

RUN apk add --no-cache \
    python-3.12=3.12.16_git20261116-r0 \
    py3.12-setuptools=84.2.1-r1 \
    ca-certificates-bundle=20261020-r1 \
    libstdc++=16.2.0-r5 \
    libgcc=16.2.0-r5 \
    libgomp=16.2.0-r5

# Python ships an unused ensurepip wheel containing setuptools 70.3.0.
# The runtime uses the isolated /opt/venv; remove the stale bootstrap wheel so
# scanners do not report an exploitable package that is not used or installed.
RUN find /usr/lib/python3.12 -type f -name 'setuptools-*.whl' -delete \
    && python3.12 -c "import setuptools; assert setuptools.__version__.startswith('84.'), setuptools.__version__"

ENV VIRTUAL_ENV=/opt/venv \
    PATH="/opt/venv/bin:$PATH" \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    OUTPUT_DIR=/tmp/lumen_output

WORKDIR /app
COPY --from=builder /opt/venv /opt/venv
COPY --from=builder /app /app

# Remove stale setuptools metadata/wheels shipped by the Python bootstrap layer.
RUN /opt/venv/bin/python /app/scripts/security/prune_stale_setuptools.py
RUN mkdir -p /tmp/lumen_output \
    && chown -R 65532:65532 /app /opt/venv /tmp/lumen_output

USER 65532:65532

EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=5s --start-period=40s --retries=3 \
  CMD ["/opt/venv/bin/python", "-c", "import os, urllib.request; urllib.request.urlopen('http://127.0.0.1:%s/health' % os.getenv('PORT', '8080'), timeout=4)"]

CMD ["/opt/venv/bin/python", "main.py"]
