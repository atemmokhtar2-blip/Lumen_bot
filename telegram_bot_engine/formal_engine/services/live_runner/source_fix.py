"""
Pre-run source repair + env discovery (deterministic, no LLM).

1) Fix common SyntaxError patterns (escaped quotes written literally)
2) Discover token-related env var names from source via AST + regex
"""

from __future__ import annotations

import ast
import re
from pathlib import Path
from typing import Iterable

# Common token-ish env names we always include if present in code or as defaults
_DEFAULT_TOKEN_ENVS = (
    "TELEGRAM_BOT_TOKEN",
    "BOT_TOKEN",
    "TOKEN",
    "TG_TOKEN",
    "API_TOKEN",
    "TELEGRAM_TOKEN",
    "BOTTOKEN",
)

_TOKEN_NAME_HINT = re.compile(
    r"(TOKEN|BOT|TELEGRAM|TG_|API_TOKEN)",
    re.I,
)


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
    Fix literal backslash-quotes that break Python parsing:
      format=\'...\'  -> format='...'
      \"...\" inside normal code lines when file was double-escaped.
    """
    notes: list[str] = []
    original = text

    # Pattern: =\'...\'  or (\'...\') on a line — replace \' with '
    def repl_single(m: re.Match) -> str:
        return m.group(0).replace("\\'", "'")

    new = re.sub(r"\\'([^\\'\\n]*)\\'", lambda m: "'" + m.group(1) + "'", text)
    if new != text:
        notes.append("fixed_escaped_single_quotes")
        text = new

    # Also handle format=\'...\' where only opening/closing escaped
    new2 = text.replace("\\'", "'")
    # Avoid breaking valid escape sequences in real strings that use \\'
    # Only apply full replace if file still doesn't parse and original had the bad pattern
    if "\\'" in original:
        try:
            ast.parse(original)
            # original already valid — don't touch
            return original, []
        except SyntaxError:
            text = original.replace("\\'", "'")
            notes.append("replaced_all_escaped_single_quotes")

    # Fix \" -> " only when file has SyntaxError with line continuation
    try:
        ast.parse(text)
        return text, notes
    except SyntaxError:
        if '\\"' in text:
            candidate = text.replace('\\"', '"')
            try:
                ast.parse(candidate)
                notes.append("fixed_escaped_double_quotes")
                return candidate, notes
            except SyntaxError:
                pass
    return text, notes


def repair_python_file(path: Path) -> list[str]:
    """Attempt in-place repair of common syntax issues. Returns notes."""
    notes: list[str] = []
    try:
        raw = path.read_text(encoding="utf-8", errors="replace")
    except Exception as e:
        return [f"read_failed:{e}"]

    try:
        ast.parse(raw)
        return []  # already valid
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
        notes.append(f"still_broken:{e.msg}@line{e.lineno}")
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

    # Regex fast path
    for m in re.finditer(
        r"""(?:os\.getenv|os\.environ\.get|getenv)\s*\(\s*['"]([A-Z][A-Z0-9_]{1,64})['"]""",
        src,
    ):
        names.add(m.group(1))
    for m in re.finditer(
        r"""os\.environ\s*\[\s*['"]([A-Z][A-Z0-9_]{1,64})['"]\s*\]""",
        src,
    ):
        names.add(m.group(1))
    for m in re.finditer(
        r"""(?:os\.environ\.get|getenv)\s*\(\s*['"]([A-Za-z_][A-Za-z0-9_]{1,64})['"]""",
        src,
    ):
        names.add(m.group(1))

    # AST path
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
            # os.environ["X"]
            if isinstance(node.value, ast.Attribute) and node.value.attr == "environ":
                sl = node.slice
                if isinstance(sl, ast.Constant) and isinstance(sl.value, str):
                    names.add(sl.value)
            self.generic_visit(node)

    V().visit(tree)
    return names


def discover_token_env_names(root: Path) -> list[str]:
    """
    Return ordered unique env var names likely used for the bot token.
    Token-ish names first, then other discovered envs.
    """
    found: set[str] = set()
    for p in _iter_py_files(root, limit=30):
        found |= discover_env_vars_from_file(p)

    tokenish = []
    other = []
    for n in sorted(found):
        if _TOKEN_NAME_HINT.search(n):
            tokenish.append(n)
        else:
            other.append(n)

    # Always ensure defaults are available for injection order
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
