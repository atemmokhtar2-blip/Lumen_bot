"""Plan-driven code generation through Hugging Face.

The model receives an execution plan, not raw prose, and returns the complete
file tree. There are no domain templates or fallback placeholder emitters.
"""
from __future__ import annotations

import ast
import json
import os
from pathlib import Path
from typing import Any

from . import hf_provider as hf


_CODE_SYSTEM = r"""You are a senior software engineer implementing a custom Telegram bot.
The user plan is the sole source of truth. Return ONE JSON object:
{"files":[{"path":"relative/path","content":"complete file content"}],"notes":["..."]}

Implement every required file from the plan. Write real, runnable code: handlers,
conversation state, validation, persistence, services, integrations, error
handling, configuration, migrations, tests, Docker files, and README whenever
specified. Do not use templates, TODO, pass, ..., NotImplementedError, fake
success responses, or claims that a feature works without implementing it.
Use environment variables for secrets. Keep imports consistent and make every
Python file compile. Do not add files not justified by the plan. If a required
technical detail is unresolved, implement a safe explicit configuration error
and mention it in notes instead of silently faking behavior.
"""


def _extract_json(text: str) -> dict[str, Any] | None:
    try:
        value = json.loads(text)
        return value if isinstance(value, dict) else None
    except Exception:
        start, end = (text or "").find("{"), (text or "").rfind("}")
        if start < 0 or end <= start:
            return None
        try:
            value = json.loads(text[start:end + 1])
            return value if isinstance(value, dict) else None
        except Exception:
            return None


def _validate_files(files: Any) -> tuple[list[dict[str, str]], list[str]]:
    errors: list[str] = []
    clean: list[dict[str, str]] = []
    forbidden = ("NotImplementedError", "TODO", "pass\n", "...\n", "Reserved path", "fake")
    for item in files if isinstance(files, list) else []:
        if not isinstance(item, dict) or not item.get("path") or not isinstance(item.get("content"), str):
            errors.append("invalid_file_record")
            continue
        path = str(item["path"]).replace("\\", "/")
        if path.startswith("/") or ".." in Path(path).parts:
            errors.append(f"unsafe_path:{path}")
            continue
        content = item["content"]
        if not content.strip():
            errors.append(f"empty_file:{path}")
        if any(marker in content for marker in forbidden):
            errors.append(f"placeholder_marker:{path}")
        if path.endswith(".py"):
            try:
                ast.parse(content, filename=path)
            except SyntaxError as exc:
                errors.append(f"syntax:{path}:{exc.msg}")
        clean.append({"path": path, "content": content})
    if not clean:
        errors.append("no_files_returned")
    return clean, list(dict.fromkeys(errors))


def generate_project_from_plan(plan: dict[str, Any], out_dir: str | Path, *, timeout: int = 240) -> dict[str, Any]:
    if not hf.enabled():
        return {"ok": False, "errors": ["HF_TOKEN not configured"], "files": []}
    required = [x.get("path") for x in plan.get("files") or [] if isinstance(x, dict) and x.get("required", True)]
    prompt = (
        "IMPLEMENTATION PLAN:\n" + json.dumps(plan, ensure_ascii=False, indent=2) +
        "\n\nRequired paths must be present: " + json.dumps(required, ensure_ascii=False)
    )
    try:
        content, model = hf.chat(
            [{"role": "system", "content": _CODE_SYSTEM}, {"role": "user", "content": prompt[:90000]}],
            timeout=timeout,
            max_tokens=int(os.environ.get("HF_CODEGEN_MAX_TOKENS", "24000")),
            temperature=0.0,
            json_mode=True,
        )
    except Exception as exc:
        return {"ok": False, "errors": [f"hf_codegen_failed:{type(exc).__name__}:{exc}"[:1200]], "files": []}
    payload = _extract_json(content)
    if payload is None:
        return {"ok": False, "errors": ["hf_codegen_json_parse_failed"], "files": [], "model": model}
    files, errors = _validate_files(payload.get("files"))
    returned = {f["path"] for f in files}
    missing = [p for p in required if p not in returned]
    errors.extend(f"missing_required_file:{p}" for p in missing)
    if errors:
        return {"ok": False, "errors": list(dict.fromkeys(errors)), "files": files, "model": model, "notes": payload.get("notes") or []}
    root = Path(out_dir)
    root.mkdir(parents=True, exist_ok=True)
    written: list[str] = []
    for item in files:
        path = root / item["path"]
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(item["content"].replace("\r\n", "\n").rstrip() + "\n", encoding="utf-8")
        written.append(str(path))
    return {"ok": True, "errors": [], "files": written, "model": model, "notes": payload.get("notes") or []}


__all__ = ["generate_project_from_plan"]
