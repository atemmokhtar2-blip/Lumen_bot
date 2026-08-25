# Observability (world-class)

## Stack

| Signal | Tool | How |
|--------|------|-----|
| Logs | Structured JSON (`LOG_FORMAT=json`) | stdout → Loki / ELK / Cloud Logging |
| Traces | OpenTelemetry SDK | OTLP HTTP → collector → Jaeger/Tempo/Datadog |
| Metrics | `prometheus_client` + optional OTEL | `GET /metrics` scrape |

## Env

```bash
OTEL_SERVICE_NAME=lumen-api
OTEL_EXPORTER_OTLP_ENDPOINT=http://otel-collector:4318
OTEL_TRACES_EXPORTER=otlp
OTEL_METRICS_EXPORTER=none
LOG_FORMAT=json
LOG_LEVEL=INFO
```

## Endpoints

- `GET /metrics` — Prometheus exposition
- Traces export via OTLP (no app endpoint)

## Install

```bash
pip install -r requirements.lock
# observability extras are in requirements.txt
```
