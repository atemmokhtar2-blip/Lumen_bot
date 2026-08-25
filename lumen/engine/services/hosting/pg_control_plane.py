"""Managed Postgres control plane for commercial hosting.

Tables:
  tbe_workers      — registered worker nodes + heartbeat + capacity
  tbe_deploy_jobs  — deploy queue (same as pg_deploy_queue)
  tbe_host_instances — optional mirror of running bots

Use a managed Postgres (RDS, Neon, Supabase, Cloud SQL). Point:
  TBE_DATABASE_URL=postgresql://user:pass@host:5432/tbe?sslmode=require
"""
from __future__ import annotations

import logging
import os
import time
from typing import Any, Optional

logger = logging.getLogger("tbe.hosting.pg_control")

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS tbe_workers (
  node_id TEXT PRIMARY KEY,
  hostname TEXT NOT NULL DEFAULT '',
  status TEXT NOT NULL DEFAULT 'online',
  max_bots INT NOT NULL DEFAULT 250,
  running_bots INT NOT NULL DEFAULT 0,
  max_memory_mb INT NOT NULL DEFAULT 49152,
  bot_memory_mb INT NOT NULL DEFAULT 192,
  version TEXT NOT NULL DEFAULT '',
  labels_json TEXT NOT NULL DEFAULT '{}',
  last_heartbeat DOUBLE PRECISION NOT NULL DEFAULT 0,
  registered_at DOUBLE PRECISION NOT NULL DEFAULT 0,
  updated_at DOUBLE PRECISION NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_tbe_workers_status ON tbe_workers(status, last_heartbeat);

CREATE TABLE IF NOT EXISTS tbe_deploy_jobs (
  job_id TEXT PRIMARY KEY,
  user_id BIGINT NOT NULL,
  project_path TEXT NOT NULL,
  token_fp TEXT NOT NULL DEFAULT '',
  sealed_token TEXT NOT NULL DEFAULT '',
  status TEXT NOT NULL DEFAULT 'queued',
  node_id TEXT NOT NULL DEFAULT '',
  deployment_id TEXT NOT NULL DEFAULT '',
  image_tag TEXT NOT NULL DEFAULT '',
  attempts INT NOT NULL DEFAULT 0,
  max_attempts INT NOT NULL DEFAULT 3,
  last_error TEXT NOT NULL DEFAULT '',
  created_at DOUBLE PRECISION NOT NULL,
  updated_at DOUBLE PRECISION NOT NULL,
  claimed_at DOUBLE PRECISION NOT NULL DEFAULT 0,
  heartbeat_at DOUBLE PRECISION NOT NULL DEFAULT 0,
  meta_json TEXT NOT NULL DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS idx_tbe_jobs_status ON tbe_deploy_jobs(status, created_at);
CREATE INDEX IF NOT EXISTS idx_tbe_jobs_user ON tbe_deploy_jobs(user_id);

CREATE TABLE IF NOT EXISTS tbe_host_instances (
  instance_id TEXT PRIMARY KEY,
  user_id BIGINT NOT NULL,
  project_path TEXT NOT NULL DEFAULT '',
  entry_point TEXT NOT NULL DEFAULT '',
  bot_username TEXT NOT NULL DEFAULT '',
  status TEXT NOT NULL DEFAULT 'stopped',
  deployment_id TEXT NOT NULL DEFAULT '',
  image_tag TEXT NOT NULL DEFAULT '',
  node_id TEXT NOT NULL DEFAULT '',
  pid BIGINT,
  started_at DOUBLE PRECISION NOT NULL DEFAULT 0,
  last_error TEXT NOT NULL DEFAULT '',
  token_fp TEXT NOT NULL DEFAULT '',
  updated_at DOUBLE PRECISION NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_tbe_inst_user ON tbe_host_instances(user_id);
CREATE INDEX IF NOT EXISTS idx_tbe_inst_status ON tbe_host_instances(status);
"""


def dsn() -> str:
    return (os.getenv("TBE_DATABASE_URL") or os.getenv("DATABASE_URL") or "").strip()


def is_postgres() -> bool:
    u = dsn().lower()
    return u.startswith("postgres://") or u.startswith("postgresql://")


def connect():
    url = dsn()
    if not is_postgres():
        raise RuntimeError("TBE_DATABASE_URL must be postgresql:// for control plane")
    try:
        import psycopg
        return psycopg.connect(url)
    except ImportError:
        import psycopg2
        return psycopg2.connect(url)


def migrate() -> None:
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute(SCHEMA_SQL)
        conn.commit()
    logger.info("control plane schema ensured")
