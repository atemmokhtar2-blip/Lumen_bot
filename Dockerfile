# Railway production image — no Rasa, lightweight runtime only.
FROM python:3.10-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    OUTPUT_DIR=/tmp/capability_maestro_output

WORKDIR /app

# No apt packages: all pinned deps ship manylinux wheels (faster, more reliable on Railway).
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# TELEGRAM_BOT_TOKEN must be set in Railway Variables.
CMD ["python", "main.py"]
