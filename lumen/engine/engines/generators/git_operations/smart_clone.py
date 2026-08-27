"""
Smart clone engine — production-grade repo pull.

Root responsibilities:
  - Normalize messy user URLs (github web paths, ssh→https, host/owner/repo)
  - Shallow, single-branch clone with multi-strategy retry
  - Honest success: verify .git + HEAD (never report ok on silent failure)
  - Safe update of existing clones (fail closed if refresh fails)
  - Token injection only into validated HTTPS allow-listed hosts
  - No shell=True; scrubbed environment via secure_exec
"""
from __future__ import annotations

import logging
import os
import re
import shutil
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional
from urllib.parse import urlparse, urlunparse

logger = logging.getLogger(__name__)

_URL_RE = re.compile(
    r"https?://(?:www\.)?(?:github\.com|gitlab\.com|bitbucket\.org|codeberg\.org|gitea\.com)"
    r"/[^\s<>'\"）】\]]+",
    re.I,
)
_SSH_RE = re.compile(
    r"git@(?:github\.com|gitlab\.com|bitbucket\.org|codeberg\.org|gitea\.com):[^\s]+",
    re.I,
)
_BARE_GH_RE = re.compile(
    r"(?:^|[\s/])((?:github|gitlab|bitbucket|codeberg|gitea)\.com)/([A-Za-z0-9_.-]+)/([A-Za-z0-9_.-]+)(?:\.git)?(?:\b|/|$)",
    re.I,
)
_TOKEN_RE = re.compile(
    r"\b("
    r"ghp_[A-Za-z0-9]{20,}|"
    r"github_pat_[A-Za-z0-9_]{20,}|"
    r"glpat-[A-Za-z0-9\-_]{20,}|"
    r"gho_[A-Za-z0-9]{20,}|"
    r"ghu_[A-Za-z0-9]{20,}|"
    r"ghs_[A-Za-z0-9]{20,}"
    r")\b"
)

_AUTH_HINTS = (
    "authentication failed",
    "could not read username",
    "invalid username or password",
    "repository not found",
    "access denied",
    "403",
    "401",
    "permission denied",
    "terminal prompts disabled",
    "could not read password",
    "error: repository not found",
    "the requested url returned error: 403",
    "the requested url returned error: 401",
    "remote: write access to repository not granted",
    "remote: repository not found",
)

_PATH_STRIP = re.compile(
    r"/(?:tree|blob|commit|pulls?|issues?|actions|settings|wiki|releases|tags|"
    r"pulse|graphs|network|security|projects|discussions)(?:/.*)?$",
    re.I,
)


@dataclass
class CloneResult:
    ok: bool
    path: Optional[str] = None
    url: Optional[str] = None
    message: str = ""
    stderr: str = ""
    needs_auth: bool = False
    strategy: str = ""
    attempts: int = 0
    file_count: int = 0
    elapsed_sec: float = 0.0
    meta: dict[str, Any] = field(default_factory=dict)


def extract_token(text: str) -> Optional[str]:
    m = _TOKEN_RE.search(text or "")
    return m.group(1) if m else None


def looks_like_git_token(text: str) -> bool:
    return extract_token(text or "") is not None


def extract_repo_url(text: str) -> Optional[str]:
    """Pull the best candidate URL from free text (not yet security-validated)."""
    text = text or ""
    m = _URL_RE.search(text)
    if m:
        return _normalize_raw_url(m.group(0))
    m = _SSH_RE.search(text)
    if m:
        return _ssh_to_https(m.group(0).rstrip(").,]>\"'"))
    m = _BARE_GH_RE.search(text)
    if m:
        host, owner, repo = m.group(1), m.group(2), m.group(3)
        repo = repo.removesuffix(".git")
        return f"https://{host.lower()}/{owner}/{repo}.git"
    return None


def _ssh_to_https(ssh: str) -> str:
    m = re.match(r"git@([^:]+):(.+)$", ssh.strip())
    if not m:
        return ssh
    host, path = m.group(1), m.group(2).lstrip("/")
    if not path.endswith(".git"):
        path = path + ".git"
    return f"https://{host}/{path}"


def _normalize_raw_url(raw: str) -> str:
    url = (raw or "").strip().rstrip(").,]>\"'）】")
    url = _PATH_STRIP.sub("", url)
    url = re.sub(r"\.git$", "", url, flags=re.I)
    if not url.endswith(".git"):
        url = url + ".git"
    return url


def normalize_and_validate_url(raw: str) -> tuple[str | None, str]:
    """Return (safe_https_url, error_message)."""
    from lumen.engine.services.secure_exec import validate_git_https_url

    candidate = (raw or "").strip()
    if not candidate:
        return None, "لم يتم العثور على رابط مستودع"
    if candidate.startswith("git@"):
        candidate = _ssh_to_https(candidate)
    if not candidate.startswith("http"):
        extracted = extract_repo_url(candidate)
        if not extracted and "/" in candidate:
            extracted = extract_repo_url("https://github.com/" + candidate.lstrip("/"))
        if extracted:
            candidate = extracted
    candidate = _normalize_raw_url(candidate)
    try:
        # validate without requiring .git suffix first
        base = candidate[:-4] if candidate.endswith(".git") else candidate
        safe = validate_git_https_url(base)
    except ValueError as exc:
        try:
            safe = validate_git_https_url(candidate)
        except ValueError as exc2:
            return None, f"رابط مرفوض أمنيًا: {exc2}"
    if not safe.endswith(".git"):
        safe = safe + ".git"
    return safe, ""


def looks_like_clone_request(text: str) -> bool:
    t = (text or "").lower()
    triggers = (
        "اسحب", "clone", "سحب", "نزل المستودع", "نزل الريبو",
        "git clone", "pull repo", "clone repo", "جيب المستودع",
        "اسحب المستودع", "اسحب الريبو", "سحب المستودع", "clone this",
        "pull this", "download repo", "هاته من جيت", "من جithub",
        "fork", "مستودع", "ريبو",
    )
    has_trigger = any(x in t for x in triggers)
    has_url = extract_repo_url(text) is not None
    if has_url and not has_trigger:
        stripped = (text or "").strip()
        if len(stripped) < 160 and re.search(
            r"github\.com|gitlab\.com|bitbucket\.org", stripped, re.I
        ):
            non_url = _URL_RE.sub("", stripped).strip()
            if len(non_url) < 48:
                return True
    return bool(has_trigger and has_url)


def _inject_token(url: str, token: Optional[str] = None) -> str:
    """Never embed credentials in the remote URL (SSRF / log leakage).

    Kept as a compatibility name for callers; always returns the clean HTTPS URL.
    Authentication must use apply_git_auth_env → GIT_ASKPASS.
    """
    if not url:
        return url or ""
    # Strip any accidental userinfo
    try:
        p = urlparse(url)
        if p.username or p.password or "@" in (p.netloc or ""):
            host = p.hostname or ""
            netloc = host if not p.port else f"{host}:{p.port}"
            return urlunparse((p.scheme or "https", netloc, p.path, "", "", ""))
    except Exception:
        pass
    return url


def apply_git_auth_env(env: dict, token: Optional[str]) -> Optional[str]:
    """Install GIT_ASKPASS for private repos. Returns askpass path to unlink later."""
    tok = (token or "").strip()
    if not tok:
        return None
    import tempfile
    fd, path = tempfile.mkstemp(prefix="lumen_git_askpass_", suffix=".sh")
    os.close(fd)
    Path(path).write_text(
        "#!/bin/sh\n"
        'case "$1" in\n'
        "  *Username*|username*) printf '%s\\n' 'x-access-token' ;;\n"
        '  *Password*|password*) printf \'%s\\n\' "$LUMEN_GIT_TOKEN" ;;\n'
        "  *) printf '\\n' ;;\n"
        "esac\n",
        encoding="utf-8",
    )
    os.chmod(path, 0o700)
    env["GIT_ASKPASS"] = path
    env["SSH_ASKPASS"] = path
    env["GIT_ASKPASS_REQUIRE"] = "force"
    env["GIT_TERMINAL_PROMPT"] = "0"
    env["LUMEN_GIT_TOKEN"] = tok
    env["GCM_INTERACTIVE"] = "never"
    return path


def _redact(text: str, token: Optional[str]) -> str:
    out = text or ""
    if token:
        out = out.replace(token, "***")
    out = _TOKEN_RE.sub("***", out)
    return out


def _is_auth_failure(stderr: str, returncode: int) -> bool:
    if returncode == 0:
        return False
    s = (stderr or "").lower()
    return any(h in s for h in _AUTH_HINTS)


def _diagnose(stderr: str, returncode: int, has_token: bool) -> str:
    s = (stderr or "").lower()
    if any(
        x in s
        for x in (
            "could not resolve host",
            "name resolution",
            "network is unreachable",
            "temporary failure",
        )
    ):
        return "مشكلة شبكة/DNS — السيرفر لا يصل لاستضافة Git"
    if any(x in s for x in ("ssl", "certificate", "tls")):
        return "مشكلة شهادة SSL أثناء الاتصال بالمستودع"
    if "disk" in s or "no space" in s:
        return "مساحة القرص ممتلئة على السيرفر"
    if any(x in s for x in ("repository not found", "not found")):
        if has_token:
            return "المستودع غير موجود أو التوكن بلا صلاحية repo على هذا الرابط"
        return "المستودع غير موجود أو خاص — أرسل رابطًا صحيحًا أو PAT بصلاحية repo"
    if _is_auth_failure(stderr, returncode):
        if has_token:
            return "فشل المصادقة بالتوكن — أنشئ PAT جديد بصلاحية repo"
        return "المستودع خاص — أرسل توكن GitHub/GitLab (PAT) في رسالة منفصلة"
    if "timeout" in s or returncode in {-9, 124}:
        return "انتهت مهلة السحب — المستودع كبير أو الشبكة بطيئة"
    if "already exists" in s:
        return "المجلد موجود مسبقًا وتعذر التحديث"
    return f"فشل السحب (code={returncode}): {(stderr or '')[:220]}"


def _disk_ok(path: Path, min_mb: int = 200) -> tuple[bool, str]:
    try:
        usage = shutil.disk_usage(str(path if path.exists() else path.parent))
        free_mb = usage.free // (1024 * 1024)
        if free_mb < min_mb:
            return False, f"مساحة القرص غير كافية ({free_mb}MB متاحة، يلزم ≥{min_mb}MB)"
        return True, ""
    except Exception:
        return True, ""


def _safe_repo_name(url: str) -> str:
    path = urlparse(url).path or "repo"
    name = Path(path).stem or "repo"
    name = "".join(c if c.isalnum() or c in "-_." else "_" for c in name)[:80]
    return name or "repo"


def _count_files(root: Path) -> int:
    n = 0
    try:
        for p in root.rglob("*"):
            if p.is_file() and ".git" not in p.parts:
                n += 1
                if n >= 50000:
                    break
    except Exception:
        pass
    return n


def _verify_clone(target: Path) -> tuple[bool, str, dict[str, Any]]:
    git_dir = target / ".git"
    if not git_dir.exists():
        return False, "لا يوجد مجلد .git بعد السحب", {}
    meta: dict[str, Any] = {}
    try:
        from lumen.engine.services.secure_exec import run_git

        head = run_git(["git", "-C", str(target), "rev-parse", "HEAD"], timeout=30)
        if head.returncode != 0:
            empty = run_git(
                ["git", "-C", str(target), "status", "--porcelain"], timeout=30
            )
            meta["empty_repo"] = True
            if empty.returncode != 0:
                return False, "تعذر قراءة حالة المستودع بعد السحب", meta
        else:
            meta["head"] = (head.stdout or "").strip()[:40]
        br = run_git(
            ["git", "-C", str(target), "branch", "--show-current"], timeout=15
        )
        if br.returncode == 0:
            meta["branch"] = (br.stdout or "").strip()
        remote = run_git(
            ["git", "-C", str(target), "remote", "get-url", "origin"], timeout=15
        )
        if remote.returncode == 0:
            meta["origin"] = _redact((remote.stdout or "").strip(), None)
    except Exception as exc:
        return False, f"فشل التحقق بعد السحب: {exc}", meta
    n = _count_files(target)
    meta["file_count"] = n
    try:
        from lumen.engine.services.secure_exec import neutralize_git_hooks
        neutralize_git_hooks(target)
        meta["hooks_neutralized"] = True
    except Exception:
        meta["hooks_neutralized"] = False
    return True, "", meta


def _run_clone_argv(
    argv: list[str],
    *,
    timeout: int,
    token: Optional[str],
) -> tuple[int, str]:
    from lumen.engine.services.secure_exec import clean_child_environ, _git_safe_config_args

    # Prefer ephemeral Docker clone (RCE isolation). Host clone only if explicitly allowed.
    import os as _os
    allow_host = (_os.getenv("TBE_GIT_CLONE_ALLOW_HOST") or "").strip().lower() in {
        "1", "true", "yes", "on",
    }
    try:
        from lumen.engine.services.git_clone_isolated import prefer_docker_clone, clone_isolated
        if argv and argv[0] == "git" and "clone" in argv and len(argv) >= 3:
            url = argv[-2]
            target = Path(argv[-1])
            branch = None
            depth = 1
            if "--branch" in argv:
                i = argv.index("--branch")
                if i + 1 < len(argv):
                    branch = argv[i + 1]
            if "--depth" in argv:
                i = argv.index("--depth")
                if i + 1 < len(argv):
                    try:
                        depth = int(argv[i + 1])
                    except ValueError:
                        depth = 1
            if prefer_docker_clone():
                ok, msg = clone_isolated(url, target, branch=branch, depth=depth, timeout=timeout)
                if ok:
                    return 0, msg
                # Docker path failed — never silent host fallback
                if not allow_host:
                    return 1, msg or "docker_clone_failed"
            elif not allow_host:
                return 1, "docker_required_for_git_clone"
    except Exception as _iso_exc:
        logger.warning("isolated clone path error: %s", type(_iso_exc).__name__)
        if not allow_host:
            return 1, f"isolated_clone_error:{type(_iso_exc).__name__}"

    if not allow_host:
        return 1, "host_git_clone_forbidden"

    env = clean_child_environ()
    askpass = apply_git_auth_env(env, token)
    # Inject safe git -c flags after 'git'; disable credential helpers that might log
    final = list(argv)
    if final and final[0] == "git":
        final = ["git", "-c", "credential.helper=", *_git_safe_config_args(), *final[1:]]
    try:
        proc = subprocess.run(
            final,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
            env=env,
        )
        err = _redact((proc.stderr or "") + "\n" + (proc.stdout or ""), token)
        return proc.returncode, err.strip()
    except subprocess.TimeoutExpired:
        return 124, "timeout"
    except Exception as exc:
        return 1, _redact(str(exc), token)
    finally:
        if askpass:
            try:
                os.unlink(askpass)
            except OSError:
                pass
        env.pop("LUMEN_GIT_TOKEN", None)


def _clone_strategies(
    auth_url: str,
    target: Path,
    *,
    branch: Optional[str],
    depth: int,
) -> list[tuple[str, list[str]]]:
    strategies: list[tuple[str, list[str]]] = []
    base = ["git", "clone", "--single-branch", "--no-tags"]
    if branch:
        base += ["--branch", branch]

    s1 = base + ["--filter=blob:none"]
    if depth > 0:
        s1 += ["--depth", str(depth)]
    s1 += [auth_url, str(target)]
    strategies.append(("partial_shallow", s1))

    s2 = list(base)
    if depth > 0:
        s2 += ["--depth", str(depth)]
    s2 += [auth_url, str(target)]
    strategies.append(("shallow", s2))

    s3 = ["git", "clone", "--single-branch", "--no-tags"]
    if branch:
        s3 += ["--branch", branch]
    s3 += [auth_url, str(target)]
    strategies.append(("full_single_branch", s3))
    return strategies


def _prepare_target(dest: Path, repo_name: str) -> Path:
    dest.mkdir(parents=True, exist_ok=True)
    target = (dest / repo_name).resolve()
    try:
        target.relative_to(dest.resolve())
    except ValueError as exc:
        raise ValueError("مسار الاستنساخ خارج الوجهة المسموحة") from exc
    if target.exists() and not (target / ".git").exists():
        suffix = time.strftime("%Y%m%d_%H%M%S")
        target = (dest / f"{repo_name}_{suffix}").resolve()
        target.relative_to(dest.resolve())
    return target


def _update_existing(
    target: Path,
    *,
    token: Optional[str],
    branch: Optional[str],
    timeout: int,
) -> CloneResult:
    from lumen.engine.services.secure_exec import run_git, neutralize_git_hooks
    try:
        neutralize_git_hooks(target)
    except Exception:
        pass

    t0 = time.monotonic()
    try:
        fetch = run_git(
            ["git", "-C", str(target), "fetch", "--depth", "1", "--prune", "origin"],
            timeout=min(timeout, 120),
        )
        if fetch.returncode != 0:
            err = _redact((fetch.stderr or fetch.stdout or ""), token)
            needs = _is_auth_failure(err, fetch.returncode) and not token
            return CloneResult(
                ok=False,
                path=str(target),
                message=_diagnose(err, fetch.returncode, bool(token)),
                stderr=err[:500],
                needs_auth=needs,
                strategy="update_fetch",
                elapsed_sec=time.monotonic() - t0,
            )
        if branch:
            co = run_git(
                ["git", "-C", str(target), "checkout", "-B", branch, f"origin/{branch}"],
                timeout=60,
            )
            if co.returncode != 0:
                co = run_git(
                    ["git", "-C", str(target), "checkout", branch],
                    timeout=60,
                )
            if co.returncode != 0:
                err = _redact((co.stderr or co.stdout or ""), token)
                return CloneResult(
                    ok=False,
                    path=str(target),
                    message=f"تعذر الانتقال للفرع {branch}: {err[:160]}",
                    stderr=err[:500],
                    strategy="update_checkout",
                    elapsed_sec=time.monotonic() - t0,
                )
        else:
            reset = run_git(
                ["git", "-C", str(target), "reset", "--hard", "origin/HEAD"],
                timeout=60,
            )
            if reset.returncode != 0:
                for ref in ("origin/main", "origin/master"):
                    reset = run_git(
                        ["git", "-C", str(target), "reset", "--hard", ref],
                        timeout=60,
                    )
                    if reset.returncode == 0:
                        break
                if reset.returncode != 0:
                    err = _redact((reset.stderr or reset.stdout or ""), token)
                    return CloneResult(
                        ok=False,
                        path=str(target),
                        message=f"تعذر تحديث الملفات المحلية: {err[:160]}",
                        stderr=err[:500],
                        strategy="update_reset",
                        elapsed_sec=time.monotonic() - t0,
                    )
    except Exception as exc:
        return CloneResult(
            ok=False,
            path=str(target),
            message=f"فشل تحديث المستودع الموجود: {exc}",
            strategy="update_exception",
            elapsed_sec=time.monotonic() - t0,
        )

    ok, verr, meta = _verify_clone(target)
    if not ok:
        return CloneResult(
            ok=False,
            path=str(target),
            message=verr or "فشل التحقق بعد التحديث",
            strategy="update_verify",
            elapsed_sec=time.monotonic() - t0,
            meta=meta,
        )
    n = int(meta.get("file_count") or 0)
    return CloneResult(
        ok=True,
        path=str(target),
        message=f"تم تحديث المستودع الموجود: {target} ({n} ملف)",
        strategy="update_existing",
        file_count=n,
        elapsed_sec=time.monotonic() - t0,
        meta=meta,
    )



def smart_clone(
    text: str,
    dest_dir: str | Path,
    token: Optional[str] = None,
    depth: Optional[int] = 1,
    url_override: Optional[str] = None,
    branch: Optional[str] = None,
    timeout_sec: Optional[int] = None,
    sparse_paths: Optional[list[str]] = None,
    prefer_mirror: bool = True,
) -> CloneResult:
    """Clone or refresh via Power Git multi-strategy engine (honest verify).

    Strategy chain (circuit breaker):
      1. Local bare mirror materialize (no network when warm)
      2. HTTPS shallow clone (+ optional sparse-checkout)
      3. ZIP archive fallback
    Success only after structural verification.
    """
    t0 = time.monotonic()
    extracted = extract_repo_url(text) if not url_override else None
    raw = (url_override or extracted or "").strip()
    url, err = normalize_and_validate_url(raw)
    if not url:
        return CloneResult(ok=False, message=err or "لم يتم العثور على رابط مستودع صالح")

    tok = token or extract_token(text)
    depth_i = 1 if depth is None else max(0, min(int(depth), 50))
    br = (branch or "").strip() or None
    if br and (len(br) > 200 or not re.match(r"^[A-Za-z0-9._/-]+$", br)):
        return CloneResult(ok=False, url=url, message="اسم الفرع غير صالح")

    dest = Path(dest_dir).expanduser().resolve()
    disk_ok, disk_msg = _disk_ok(dest)
    if not disk_ok:
        return CloneResult(ok=False, url=url, message=disk_msg)

    try:
        target = _prepare_target(dest, _safe_repo_name(url))
    except ValueError as exc:
        return CloneResult(ok=False, url=url, message=str(exc))

    if target.exists() and (target / ".git").exists():
        result = _update_existing(target, token=tok, branch=br, timeout=int(timeout_sec or 300))
        result.url = url
        result.elapsed_sec = time.monotonic() - t0
        return result

    try:
        from .power.strategies import clone_multi_strategy
        from .power.security import ensure_strict_gitignore

        eng = clone_multi_strategy(
            url,
            target,
            token=tok,
            branch=br,
            depth=depth_i,
            sparse_paths=sparse_paths,
            prefer_mirror=prefer_mirror,
        )
        if eng.ok and eng.path:
            try:
                ensure_strict_gitignore(Path(eng.path))
            except Exception:
                pass
            return CloneResult(
                ok=True,
                path=eng.path,
                url=url,
                message=eng.message if eng.message and eng.message not in {"ok", "clone_ok"} else "تم سحب المستودع",
                strategy=eng.strategy_used or "power",
                attempts=eng.attempts or 1,
                file_count=int(eng.files_changed_count or 0),
                elapsed_sec=time.monotonic() - t0,
                meta=dict(eng.metadata or {}),
            )
        return CloneResult(
            ok=False,
            url=url,
            message=eng.message or eng.redacted_error or "clone_failed",
            stderr=(eng.redacted_error or "")[:500],
            needs_auth=bool(eng.needs_auth),
            strategy=eng.strategy_used or "",
            attempts=int(eng.attempts or 0),
            elapsed_sec=time.monotonic() - t0,
            meta=dict(eng.metadata or {}),
        )
    except Exception:
        logger.exception("power clone path failed; legacy strategies")

    auth_url = _inject_token(url, tok)
    attempts = 0
    last_err = ""
    used = ""
    for name, argv in _clone_strategies(auth_url, target, branch=br, depth=depth_i):
        if target.exists():
            shutil.rmtree(target, ignore_errors=True)
        attempts += 1
        used = name
        code, err_text = _run_clone_argv(argv, timeout=int(timeout_sec or 300), token=tok)
        last_err = err_text
        if code == 0:
            ok, verr, meta = _verify_clone(target)
            if ok:
                return CloneResult(
                    ok=True,
                    path=str(target),
                    url=url,
                    message="تم سحب المستودع",
                    strategy=used,
                    attempts=attempts,
                    file_count=int(meta.get("file_count") or 0),
                    elapsed_sec=time.monotonic() - t0,
                    meta=meta,
                )
            last_err = verr or last_err
        if _is_auth_failure(err_text, code) and not tok:
            return CloneResult(
                ok=False,
                url=url,
                message=_diagnose(err_text, code, False),
                stderr=err_text[:500],
                needs_auth=True,
                strategy=used,
                attempts=attempts,
                elapsed_sec=time.monotonic() - t0,
            )

    return CloneResult(
        ok=False,
        url=url,
        message=_diagnose(last_err, 1, bool(tok)),
        stderr=last_err[:500],
        strategy=used,
        attempts=attempts,
        elapsed_sec=time.monotonic() - t0,
    )



__all__ = [
    "CloneResult",
    "smart_clone",
    "extract_repo_url",
    "extract_token",
    "looks_like_git_token",
    "looks_like_clone_request",
    "normalize_and_validate_url",
]
