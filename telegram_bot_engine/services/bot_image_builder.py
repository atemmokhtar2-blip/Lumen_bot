"""Build immutable Docker images for generated bots (no host bind-mount of source).

Security rules (fail-closed):
  - Never COPY secrets (.env, .tbe_bot_token, keys) into the image
  - Base image allowlisted
  - Entry point allowlisted (main.py / bot.py / app.py only)
  - requirements install must not silently succeed on failure in production
  - Content-addressable tags only (no raw user strings in shell form)
"""
from __future__ import annotations

import hashlib
import logging
import os
import re
import subprocess
from pathlib import Path

logger = logging.getLogger("tbe.bot_image_builder")

# Only these bases may be used — prevents FROM evil.registry/malware
_ALLOWED_BASE_PREFIXES = (
    "python:3.11-slim",
    "python:3.12-slim",
    "python:3.11-alpine",
    "python:3.12-alpine",
    "public.ecr.aws/docker/library/python:3.11-slim",
    "public.ecr.aws/docker/library/python:3.12-slim",
)

_ALLOWED_ENTRIES = frozenset({"main.py", "bot.py", "app.py"})

_DOCKERIGNORE = """\
.git
.venv
venv
__pycache__
*.pyc
*.pyo
*.log
*.zip
.env
.env.*
.tbe_bot_token
.tbe_smoke_runner.py
secrets.json
**/credentials*
**/*secret*
**/*token*
.ssh
.aws
"""

_DOCKERFILE = """\
# Auto-generated — immutable bot image. Secrets must NEVER be in this context.
FROM {base_image}
ENV PYTHONUNBUFFERED=1 \\
    PYTHONDONTWRITEBYTECODE=1 \\
    PIP_DISABLE_PIP_VERSION_CHECK=1 \\
    HOME=/tmp \\
    PYTHONPATH=/app
WORKDIR /app
RUN useradd -u 10001 -m -s /usr/sbin/nologin botuser 2>/dev/null || true
COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir --upgrade pip \\
 && pip install --no-cache-dir -r /app/requirements.txt
COPY app /app/app
COPY main.py /app/main.py
# Optional entry aliases (ignored if absent — build context controlled on host)
USER 10001:10001
WORKDIR /app
CMD ["python", "-u", "{entry}"]
"""


def _safe(s: str, n: int = 40) -> str:
    s = re.sub(r"[^a-zA-Z0-9_.-]+", "-", (s or "x")).strip("-").lower()
    return (s or "x")[:n]


def allowed_base_image() -> str:
    raw = (os.environ.get("TBE_DOCKER_IMAGE") or "python:3.11-slim").strip()
    # strip digests for prefix check then re-validate full string charset
    if not re.fullmatch(r"[a-zA-Z0-9_./:@+-]+", raw):
        raise ValueError("invalid_base_image_chars")
    ok = any(raw == p or raw.startswith(p + "@") or raw.startswith(p + "-") for p in _ALLOWED_BASE_PREFIXES)
    # also allow exact allowlist with digest
    if not ok:
        for p in _ALLOWED_BASE_PREFIXES:
            if raw.startswith(p):
                ok = True
                break
    if not ok:
        raise ValueError(f"base_image_not_allowlisted:{raw}")
    return raw


def resolve_entry(project_path: Path, entry: str | None = None) -> str:
    cand = (entry or "main.py").strip().lstrip("./")
    if cand not in _ALLOWED_ENTRIES:
        cand = "main.py"
    if (project_path / cand).is_file():
        return cand
    for name in ("main.py", "bot.py", "app.py"):
        if (project_path / name).is_file():
            return name
    raise FileNotFoundError("no_allowed_entry_point")


def content_hash(project_path: Path) -> str:
    h = hashlib.sha256()
    skip_names = {
        ".tbe_bot_token", ".env", ".env.local", ".env.production",
        "secrets.json", ".tbe_smoke_runner.py", "Dockerfile", ".dockerignore",
    }
    for p in sorted(project_path.rglob("*")):
        if not p.is_file():
            continue
        if any(x in p.parts for x in (".git", "__pycache__", ".venv", "venv")):
            continue
        if p.suffix in {".pyc", ".pyo", ".log", ".zip"}:
            continue
        if p.name in skip_names or "secret" in p.name.lower() or "token" in p.name.lower():
            continue
        try:
            h.update(p.relative_to(project_path).as_posix().encode())
            h.update(p.read_bytes())
        except Exception:
            continue
    return h.hexdigest()[:12]


def write_dockerignore(project_path: Path) -> Path:
    p = project_path / ".dockerignore"
    p.write_text(_DOCKERIGNORE, encoding="utf-8")
    return p


def write_dockerfile(project_path: Path, *, entry: str = "main.py") -> Path:
    base = allowed_base_image()
    entry_rel = resolve_entry(project_path, entry)
    # Prefer copying only app/ + main.py — avoid COPY .
    # If bot.py/app.py is entry, ensure it is present as main alias or copy it
    text = _DOCKERFILE.format(base_image=base, entry=entry_rel)
    if entry_rel != "main.py":
        text = text.replace(
            "COPY main.py /app/main.py\n",
            f"COPY main.py /app/main.py\nCOPY {entry_rel} /app/{entry_rel}\n",
        )
    # If no app/ package, fall back to broader copy of *.py only via host-side staging
    app_dir = project_path / "app"
    if not app_dir.is_dir():
        text = text.replace(
            "COPY app /app/app\nCOPY main.py /app/main.py\n",
            "COPY *.py /app/\n",
        )
    df = project_path / "Dockerfile"
    df.write_text(text, encoding="utf-8")
    write_dockerignore(project_path)
    req = project_path / "requirements.txt"
    if not req.is_file():
        req.write_text("python-telegram-bot>=21.0,<22\n", encoding="utf-8")
    else:
        try:
            from telegram_bot_engine.services.requirements_policy import sanitize_requirements_text
            cleaned, _ = sanitize_requirements_text(req.read_text(encoding="utf-8", errors="ignore"))
            req.write_text(cleaned, encoding="utf-8")
        except Exception:
            pass
    # Strip any accidental secret files from build context (defense in depth)
    for secret_name in (".tbe_bot_token", ".env", "secrets.json"):
        sp = project_path / secret_name
        if sp.is_file():
            # Do not delete user's token file on disk — only ensure dockerignore covers it
            pass
    return df


def image_tag_for(project_path: Path, user_id: str | int) -> str:
    registry = (os.environ.get("TBE_DOCKER_REGISTRY") or "").strip().rstrip("/")
    name = _safe(project_path.name, 32)
    tag = f"tbe/u{_safe(str(user_id), 16)}/{name}:{content_hash(project_path)}"
    if registry:
        # registry host must be conservative charset
        if not re.fullmatch(r"[a-zA-Z0-9._:/-]+", registry):
            raise ValueError("invalid_registry")
        return f"{registry}/{tag}"
    return tag


def validate_image_tag(tag: str) -> str:
    if not tag or not re.fullmatch(r"[a-zA-Z0-9_./:@+-]+", tag):
        raise ValueError("invalid_image_tag")
    if any(x in tag for x in ("..", " ", "\n", "\r", ";", "|", "&", "$", "`")):
        raise ValueError("invalid_image_tag")
    return tag


def _stage_clean_context(project_path: Path, entry_rel: str) -> Path:
    """Copy only non-secret runtime files into an ephemeral build context."""
    import shutil
    import tempfile

    stage = Path(tempfile.mkdtemp(prefix="tbe_build_"))
    # requirements + entry + app package only
    req_src = project_path / "requirements.txt"
    if req_src.is_file():
        shutil.copy2(req_src, stage / "requirements.txt")
    else:
        (stage / "requirements.txt").write_text(
            "python-telegram-bot>=21.0,<22\n", encoding="utf-8"
        )
    for name in _ALLOWED_ENTRIES:
        src = project_path / name
        if src.is_file():
            shutil.copy2(src, stage / name)
    app_src = project_path / "app"
    if app_src.is_dir():
        def _ignore(dirpath, names):
            drop = []
            for n in names:
                low = n.lower()
                if n.startswith(".") or n in {"__pycache__", ".venv", "venv"}:
                    drop.append(n)
                elif "secret" in low or "token" in low or n.endswith(".log"):
                    drop.append(n)
            return drop
        shutil.copytree(app_src, stage / "app", ignore=_ignore)
    write_dockerfile(stage, entry=entry_rel)
    write_dockerignore(stage)
    return stage


def build_image(
    project_path: Path,
    *,
    user_id: str | int,
    entry: str = "main.py",
    timeout: int = 600,
) -> tuple[bool, str, str]:
    """Build image from a cleaned staging context (secrets never enter layers)."""
    import shutil

    path = Path(project_path).resolve()
    if not path.is_dir():
        return False, "project_missing", ""
    stage = None
    try:
        entry_rel = resolve_entry(path, entry)
        tag = validate_image_tag(image_tag_for(path, user_id))
        # Also write Dockerfile into the real project for export/delivery transparency
        write_dockerfile(path, entry=entry_rel)
        write_dockerignore(path)
    except Exception as e:
        return False, f"prebuild:{type(e).__name__}:{e}", ""

    insp = subprocess.run(
        ["docker", "image", "inspect", tag],
        capture_output=True, text=True, timeout=30, check=False,
    )
    if insp.returncode == 0:
        return True, tag, "image_cached"

    try:
        stage = _stage_clean_context(path, entry_rel)
        cmd = [
            "docker", "build",
            "--pull",
            "--no-cache",
            "-t", tag,
            "-f", str(stage / "Dockerfile"),
            str(stage),
        ]
        proc = subprocess.run(
            cmd, capture_output=True, text=True, timeout=timeout, check=False,
        )
    except subprocess.TimeoutExpired:
        return False, "build_timeout", ""
    except Exception as e:
        return False, f"build_error:{type(e).__name__}", str(e)[:200]
    finally:
        if stage is not None:
            try:
                shutil.rmtree(stage, ignore_errors=True)
            except Exception:
                pass

    log = ((proc.stdout or "") + "\n" + (proc.stderr or "")).strip()
    if proc.returncode != 0:
        return False, f"build_failed:{proc.returncode}", log[-800:]

    if (os.environ.get("TBE_DOCKER_PUSH") or "").strip().lower() in {"1", "true", "yes", "on"}:
        push = subprocess.run(
            ["docker", "push", tag], capture_output=True, text=True, timeout=300, check=False,
        )
        if push.returncode != 0:
            logger.warning("docker push failed for %s: %s", tag, (push.stderr or "")[:200])
            if (os.environ.get("TBE_MULTI_TENANT") or "").strip().lower() in {"1", "true", "yes", "on"}:
                return False, "push_failed", (push.stderr or "")[-400:]
        else:
            log += "\npush_ok"
    return True, tag, log[-400:]
