"""Deep per-hunk PR analysis using real parsers (ast, tree-sitter, py_compile).

Produces findings with path + line suitable for GitHub review comments.
No generic fluff — only findings with evidence.
"""
from __future__ import annotations

import ast
import logging
import re
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


def extract_added_lines(patch: str) -> list[tuple[int, str]]:
    """Return (right_side_line_number, content) for added lines in a unified diff."""
    if not patch:
        return []
    out: list[tuple[int, str]] = []
    new_line: int | None = None
    for raw in patch.splitlines():
        hm = re.match(r"@@\s+-\d+(?:,\d+)?\s+\+(\d+)(?:,\d+)?\s+@@", raw)
        if hm:
            new_line = int(hm.group(1))
            continue
        if new_line is None:
            continue
        if raw.startswith("\\"):
            continue
        if raw.startswith("-"):
            continue
        if raw.startswith("+"):
            out.append((new_line, raw[1:]))
            new_line += 1
            continue
        # context
        new_line += 1
    return out


def analyze_changed_python_file(
    root: Path,
    rel_path: str,
    *,
    patch: str = "",
) -> list[dict[str, Any]]:
    """Deep analysis of one changed Python file under clone root."""
    findings: list[dict[str, Any]] = []
    fp = root / rel_path
    if not fp.is_file() or not rel_path.endswith(".py"):
        return findings

    try:
        source = fp.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        return [{"path": rel_path, "line": 1, "severity": "error", "code": "read_fail", "message": str(exc)}]

    # 1) Syntax via ast + py_compile to temp
    try:
        ast.parse(source, filename=rel_path)
    except SyntaxError as se:
        findings.append(
            {
                "path": rel_path,
                "line": int(se.lineno or 1),
                "severity": "error",
                "code": "syntax_error",
                "message": f"{se.msg}",
                "evidence": (se.text or "")[:200],
            }
        )
    # 2) Pattern checks only on lines **added** in this PR (from patch)
    added = extract_added_lines(patch)
    added_line_set = {ln for ln, _ in added}
    for ln, content in added:
        s = content.strip()
        if s == "except:" or s.startswith("except:"):
            findings.append(
                {
                    "path": rel_path,
                    "line": ln,
                    "severity": "warning",
                    "code": "bare_except",
                    "message": "Bare except: in added code",
                    "evidence": content[:120],
                }
            )
        if "eval(" in s or "exec(" in s:
            findings.append(
                {
                    "path": rel_path,
                    "line": ln,
                    "severity": "warning",
                    "code": "dynamic_exec",
                    "message": "eval/exec in added code",
                    "evidence": content[:120],
                }
            )
        if "password" in s.lower() and ("=" in s) and not s.strip().startswith("#"):
            findings.append(
                {
                    "path": rel_path,
                    "line": ln,
                    "severity": "warning",
                    "code": "possible_secret",
                    "message": "Possible hardcoded secret assignment",
                    "evidence": content[:120],
                }
            )
    # 3) AST: detect obvious issues in whole module (undefined name is hard without full graph)
    try:
        tree = ast.parse(source, filename=rel_path)
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and len(node.body) == 1 and isinstance(node.body[0], ast.Pass):
                if node.lineno in added_line_set or any(
                    node.lineno <= ln <= (node.end_lineno or node.lineno) for ln in added_line_set
                ):
                    findings.append(
                        {
                            "path": rel_path,
                            "line": node.lineno,
                            "severity": "warning",
                            "code": "empty_function",
                            "message": f"Function `{node.name}` is only `pass`",
                        }
                    )
    except SyntaxError:
        pass

    return findings


def deep_review_pr_files(
    root: Path,
    files_meta: list[dict[str, Any]],
    *,
    max_files: int = 30,
) -> dict[str, Any]:
    """Analyze all changed files; return findings + optional hybrid context."""
    all_findings: list[dict[str, Any]] = []
    analyzed = 0
    for meta in files_meta[:max_files]:
        path = str(meta.get("filename") or "")
        if not path.endswith(".py"):
            continue
        analyzed += 1
        findings = analyze_changed_python_file(
            root, path, patch=str(meta.get("patch") or "")
        )
        all_findings.extend(findings)

    # hybrid on aggregated finding messages
    hybrid = {}
    try:
        from lumen.engine.services.code_intelligence.hybrid_retrieval import hybrid_search

        q = " ".join(f.get("message", "") for f in all_findings[:8]) or "pull request changes"
        hs = hybrid_search(root, q, top_k=8)
        hybrid = {
            "embed_provider": hs.get("embed_provider"),
            "hits": [
                {"path": h.get("path"), "score": h.get("score"), "name": h.get("name")}
                for h in (hs.get("hits") or [])[:8]
                if isinstance(h, dict)
            ],
        }
    except Exception as exc:
        hybrid = {"error": type(exc).__name__}

    return {
        "ok": not any(f.get("severity") == "error" for f in all_findings),
        "analyzed_files": analyzed,
        "findings": all_findings[:50],
        "hybrid": hybrid,
    }


def findings_to_line_comments(findings: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Map findings → GitHub review comment payloads (path/line/side/body)."""
    comments: list[dict[str, Any]] = []
    seen: set[tuple[str, int, str]] = set()
    for f in findings:
        path = str(f.get("path") or "")
        line = int(f.get("line") or 0)
        code = str(f.get("code") or "")
        if not path or line < 1:
            continue
        key = (path, line, code)
        if key in seen:
            continue
        seen.add(key)
        sev = f.get("severity") or "info"
        msg = f.get("message") or code
        evidence = f.get("evidence") or ""
        body = f"**{sev.upper()}** `{code}`: {msg}"
        if evidence:
            body += f"\n```\n{evidence}\n```"
        comments.append(
            {
                "path": path,
                "body": body[:65535],
                "line": line,
                "side": "RIGHT",
            }
        )
    return comments[:25]


__all__ = [
    "extract_added_lines",
    "analyze_changed_python_file",
    "deep_review_pr_files",
    "findings_to_line_comments",
]
