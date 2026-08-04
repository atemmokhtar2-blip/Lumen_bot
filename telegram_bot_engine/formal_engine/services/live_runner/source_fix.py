"""
Pre-run source repair + env discovery (deterministic, no LLM).

Handles multi-escaped quotes that survive a single replace pass.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path
from typing import Iterable

_DEFAULT_TOKEN_ENVS = (
    "TELEGRAM_BOT_TOKEN",
    "BOT_TOKEN",
    "TOKEN",
    "TG_TOKEN",
    "API_TOKEN",
    "TELEGRAM_TOKEN",
    "BOTTOKEN",
)

_TOKEN_NAME_HINT = re.compile(r"(TOKEN|BOT|TELEGRAM|TG_|API_TOKEN)", re.I)


def _iter_py_files(root: Path, limit: int = 40) -> Iterable[Path]:
    preferred = []
    for name in ("bot.py", "main.py", "app.py", "run.py", "config.py", "settings.py"):
        p = root / name
        if p.exists():
            preferred.append(p)
    others = []
    for p in root.rglob("*.py"):
        if any(x in p.parts for x in (".git", ".venv", ".tbe_venv", ".tbe_deps", "__pycache__")):
            continue
        if p in preferred:
            continue
        others.append(p)
        if len(preferred) + len(others) >= limit:
            break
    return preferred + others[: max(0, limit - len(preferred))]


def fix_escaped_quotes_in_source(text: str) -> tuple[str, list[str]]:
    """
    Aggressively normalize broken escaped quotes written into source files.

    Examples that must become valid:
      format=\'...\'
      format=\\'...\\'
      format=\\\'...\\\'
    """
    notes: list[str] = []
    original = text

    try:
        ast.parse(original)
        return original, []
    except SyntaxError:
        pass

    # 1) Repeatedly collapse \'+  sequences before a quote into a bare quote
    #    \\' -> \' -> '
    prev = None
    cur = text
    rounds = 0
    while prev != cur and rounds < 10:
        prev = cur
        # one or more backslashes immediately before a single or double quote
        nxt = re.sub(r"\\+(')", r"\1", cur)
        nxt = re.sub(r'\\+(")', r"\1", nxt)
        cur = nxt
        rounds += 1
    if cur != text:
        notes.append(f"collapsed_backslash_quotes_rounds={rounds}")
        text = cur

    # 2) Line-continuation orphans: trailing \ before non-newline junk on same line
    #    e.g. format=\ 'x'  (backslash space)
    new_lines = []
    changed_lines = 0
    for line in text.splitlines(keepends=True):
        # if line has odd dangling backslash patterns outside strings — hard;
        # focus on `=\s*\\` before quote already handled
        stripped = line.rstrip("\n\r")
        if re.search(r"=\\\s*['\"]", stripped):
            fixed_line = re.sub(r"=\\\s*(['\"])", r"=\1", stripped)
            if line.endswith("\r\n"):
                fixed_line += "\r\n"
            elif line.endswith("\n"):
                fixed_line += "\n"
            line = fixed_line
            changed_lines += 1
        new_lines.append(line)
    if changed_lines:
        notes.append(f"fixed_eq_backslash_quote_lines={changed_lines}")
        text = "".join(new_lines)

    # 3) If still broken, try logging.basicConfig format= rewrite from common template
    try:
        ast.parse(text)
        return text, notes
    except SyntaxError as e:
        notes.append(f"still_after_collapse:{e.msg}@line{e.lineno}")

    # 4) Targeted fix on the failing line: strip all backslashes before quotes on that line
    try:
        lines = text.splitlines(keepends=True)
        # lineno is 1-based
        err = None
        try:
            ast.parse(text)
        except SyntaxError as e:
            err = e
        if err and err.lineno and 1 <= err.lineno <= len(lines):
            idx = err.lineno - 1
            old = lines[idx]
            fixed_line = re.sub(r"\\+(['\"])", r"\1", old)
            # also remove lone backslash before end of assignment fragments
            fixed_line = re.sub(r"=\\+", "=", fixed_line)
            if fixed_line != old:
                lines[idx] = fixed_line
                text2 = "".join(lines)
                try:
                    ast.parse(text2)
                    notes.append(f"line_surgery@{err.lineno}")
                    return text2, notes
                except SyntaxError as e2:
                    notes.append(f"line_surgery_failed:{e2.msg}")
                    text = text2
    except Exception as ex:
        notes.append(f"line_surgery_error:{ex}")

    # 5) Nuclear option for format= lines: rewrite to a safe format string
    text3, n = re.subn(
        r"format\s*=\s*\\*['\"].*?\\*['\"]",
        "format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'",
        text,
        flags=re.S,
    )
    if n:
        notes.append(f"rewrote_format_kwargs={n}")
        try:
            ast.parse(text3)
            return text3, notes
        except SyntaxError as e:
            notes.append(f"format_rewrite_failed:{e.msg}")

    return text, notes


def repair_python_file(path: Path) -> list[str]:
    notes: list[str] = []
    try:
        raw = path.read_text(encoding="utf-8", errors="replace")
    except Exception as e:
        return [f"read_failed:{e}"]

    try:
        ast.parse(raw)
        return []
    except SyntaxError as e:
        notes.append(f"syntax_error_before:{e.msg}@line{e.lineno}")

    fixed, fix_notes = fix_escaped_quotes_in_source(raw)
    notes.extend(fix_notes)
    try:
        ast.parse(fixed)
        path.write_text(fixed, encoding="utf-8")
        notes.append("repaired_and_saved")
        return notes
    except SyntaxError as e:
        # last resort: write fixed anyway if closer? no — keep original if still invalid
        notes.append(f"still_broken:{e.msg}@line{e.lineno}")
        # Show failing line content for diagnostics
        try:
            lines = fixed.splitlines()
            if e.lineno and 1 <= e.lineno <= len(lines):
                notes.append(f"failing_line_repr={lines[e.lineno - 1]!r}"[:200])
        except Exception:
            pass
        return notes


def repair_project_sources(root: Path) -> list[str]:
    all_notes: list[str] = []
    for p in _iter_py_files(root):
        n = repair_python_file(p)
        if n:
            all_notes.append(f"{p.name}: {', '.join(n)}")
    return all_notes


def discover_env_vars_from_file(path: Path) -> set[str]:
    names: set[str] = set()
    try:
        src = path.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return names

    for m in re.finditer(
        r"""(?:os\.getenv|os\.environ\.get|getenv)\s*\(\s*['"]([A-Za-z_][A-Za-z0-9_]{1,64})['"]""",
        src,
    ):
        names.add(m.group(1))
    for m in re.finditer(
        r"""os\.environ\s*\[\s*['"]([A-Za-z_][A-Za-z0-9_]{1,64})['"]\s*\]""",
        src,
    ):
        names.add(m.group(1))

    try:
        tree = ast.parse(src)
    except SyntaxError:
        return names

    class V(ast.NodeVisitor):
        def visit_Call(self, node: ast.Call) -> None:
            func = node.func
            fname = ""
            if isinstance(func, ast.Name):
                fname = func.id
            elif isinstance(func, ast.Attribute):
                fname = func.attr
            if fname in ("getenv", "get") and node.args:
                a0 = node.args[0]
                if isinstance(a0, ast.Constant) and isinstance(a0.value, str):
                    if a0.value.isupper() or _TOKEN_NAME_HINT.search(a0.value):
                        names.add(a0.value)
            self.generic_visit(node)

        def visit_Subscript(self, node: ast.Subscript) -> None:
            if isinstance(node.value, ast.Attribute) and node.value.attr == "environ":
                sl = node.slice
                if isinstance(sl, ast.Constant) and isinstance(sl.value, str):
                    names.add(sl.value)
            self.generic_visit(node)

    V().visit(tree)
    return names


def discover_token_env_names(root: Path) -> list[str]:
    found: set[str] = set()
    for p in _iter_py_files(root, limit=30):
        found |= discover_env_vars_from_file(p)

    tokenish, other = [], []
    for n in sorted(found):
        (tokenish if _TOKEN_NAME_HINT.search(n) else other).append(n)

    ordered = []
    for n in list(tokenish) + list(_DEFAULT_TOKEN_ENVS):
        if n not in ordered:
            ordered.append(n)
    return ordered


def syntax_check_entry(path: Path) -> tuple[bool, str]:
    try:
        ast.parse(path.read_text(encoding="utf-8", errors="replace"), filename=str(path))
        return True, ""
    except SyntaxError as e:
        return False, f"{e.msg} line {e.lineno}"
    except Exception as e:
        return False, str(e)
