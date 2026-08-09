"""
Pre-run source repair + env discovery.

Designed for repos where every quote was wrongly written as \\' / \\".
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


def _global_unescape_quotes(text: str) -> tuple[str, int]:
    """Replace \\' and \\" repeatedly until stable. Returns (text, rounds)."""
    rounds = 0
    while rounds < 20 and ("\\'" in text or '\\"' in text):
        text = text.replace("\\'", "'").replace('\\"', '"')
        rounds += 1
    return text, rounds


def _fix_broken_fstrings(text: str) -> tuple[str, int]:
    """
    Fix f\"... \"{x}\" ...\" that become invalid after unescape:
      f"text "{var}" more"  ->  f'text "{var}" more'
    """
    fixed = 0
    out = []
    for line in text.splitlines(keepends=True):
        nl = ""
        core = line
        if line.endswith("\r\n"):
            nl, core = "\r\n", line[:-2]
        elif line.endswith("\n"):
            nl, core = "\n", line[:-1]

        stripped = core.lstrip()
        if stripped.startswith('f"') and '"{' in core and '}"' in core:
            # switch outer quotes to single
            # find first f" and matching structure
            m = re.match(r'^(\s*)f"(.*)("\s*,?\s*)$', core)
            if m:
                indent, body, end = m.group(1), m.group(2), m.group(3)
                # body may contain " around {expr}
                # end is closing " with optional comma
                # If body has unescaped ", use single-quoted f-string
                if '"' in body:
                    # remove a trailing " that was the original closer left in body? 
                    # pattern: body ends without the closing quote — end has "
                    # end group is `"\s*,?\s*` or just `"`
                    comma = "," if "," in end else ""
                    core = f"{indent}f'{body}'{comma}"
                    fixed += 1
            else:
                # try: f"....", at end
                m2 = re.match(r'^(\s*)f"(.*)",\s*$', core)
                if m2 and '"' in m2.group(2):
                    core = f"{m2.group(1)}f'{m2.group(2)}',"
                    fixed += 1
                else:
                    m3 = re.match(r'^(\s*)f"(.*)"\s*$', core)
                    if m3 and '"' in m3.group(2):
                        core = f"{m3.group(1)}f'{m3.group(2)}'"
                        fixed += 1
        out.append(core + nl)
    return "".join(out), fixed


def _fix_line_continuation_in_sql(text: str) -> tuple[str, int]:
    """
    Fix broken multi-line strings like:
      conn.execute('CREATE TABLE ... \\\n')
    """
    # Join lines that end with unmatched quote and backslash
    lines = text.splitlines(keepends=True)
    fixed = 0
    i = 0
    out = []
    while i < len(lines):
        line = lines[i]
        # if odd number of unescaped quotes and ends with \ then next line continues
        if line.rstrip("\r\n").endswith("\\") and i + 1 < len(lines):
            # merge with next
            merged = line.rstrip("\r\n").rstrip("\\") + lines[i + 1].lstrip()
            out.append(merged if merged.endswith("\n") else merged + ("\n" if line.endswith("\n") else ""))
            i += 2
            fixed += 1
            continue
        out.append(line)
        i += 1
    return "".join(out), fixed




def _fix_ptb_api_misuse(text: str) -> tuple[str, list[str]]:
    """Fix common python-telegram-bot v20+ API mistakes that cause TypeError/NameError at runtime."""
    notes: list[str] = []

    def repl_cmd(m: re.Match) -> str:
        cmd = m.group(1)
        return f"filters.Regex(r'^/{cmd}(?:@\\w+)?$')"

    text2, n = re.subn(
        r"filters\.COMMAND\(\s*['\"]([A-Za-z0-9_]+)['\"]\s*\)",
        repl_cmd,
        text,
    )
    if n:
        notes.append(f"fixed_filters_COMMAND_callable={n}")
        text = text2

    text2, n = re.subn(
        r"MessageHandler\(\s*filters\.CallbackQuery\s*,\s*([A-Za-z_][A-Za-z0-9_]*)\s*\)",
        r"CallbackQueryHandler(\1)",
        text,
    )
    if n:
        notes.append(f"fixed_CallbackQueryHandler={n}")
        text = text2

    if "CallbackQueryHandler" in text and not re.search(
        r"from telegram\.ext import[^\n]*CallbackQueryHandler", text
    ):
        text2, n_imp = re.subn(
            r"(from telegram\.ext import [^\n]+)",
            lambda m: m.group(1)
            if "CallbackQueryHandler" in m.group(1)
            else m.group(1).rstrip() + ", CallbackQueryHandler",
            text,
            count=1,
        )
        if n_imp:
            text = text2
            notes.append("added_CallbackQueryHandler_import")

    return text, notes


def fix_escaped_quotes_in_source(text: str) -> tuple[str, list[str]]:
    notes: list[str] = []
    try:
        ast.parse(text)
        return text, []
    except SyntaxError as e:
        notes.append(f"syntax_error_before:{e.msg}@line{e.lineno}")

    text, rounds = _global_unescape_quotes(text)
    if rounds:
        notes.append(f"global_unescape_rounds={rounds}")

    text, n_fs = _fix_broken_fstrings(text)
    if n_fs:
        notes.append(f"fixed_fstrings={n_fs}")

    text, n_sql = _fix_line_continuation_in_sql(text)
    if n_sql:
        notes.append(f"joined_continuation_lines={n_sql}")

    try:
        ast.parse(text)
        return text, notes
    except SyntaxError as e:
        notes.append(f"after_main_fix:{e.msg}@line{e.lineno}")

    # Line-level surgery on remaining error line
    try:
        lines = text.splitlines(keepends=True)
        if e.lineno and 1 <= e.lineno <= len(lines):
            idx = e.lineno - 1
            old = lines[idx]
            cand = old.replace("\\'", "'").replace('\\"', '"')
            cand = re.sub(r"\\+(['\"])", r"\1", cand)
            # if f" with inner quotes
            if 'f"' in cand and '"' in cand[cand.find('f"') + 2 :]:
                cand2, n = _fix_broken_fstrings(cand)
                if n:
                    cand = cand2
            lines[idx] = cand
            text2 = "".join(lines)
            try:
                ast.parse(text2)
                notes.append(f"line_surgery_ok@{e.lineno}")
                return text2, notes
            except SyntaxError as e2:
                notes.append(f"line_surgery_failed:{e2.msg}@line{e2.lineno}")
                text = text2
                e = e2
    except Exception as ex:
        notes.append(f"surgery_error:{ex}")

    return text, notes


def repair_python_file(path: Path) -> list[str]:
    notes: list[str] = []
    try:
        raw = path.read_text(encoding="utf-8", errors="replace")
    except Exception as e:
        return [f"read_failed:{e}"]

    try:
        ast.parse(raw)
        fixed2, api_notes = _fix_ptb_api_misuse(raw)
        if api_notes:
            try:
                ast.parse(fixed2)
                path.write_text(fixed2, encoding="utf-8")
                return api_notes + ["api_fixed_and_saved"]
            except SyntaxError:
                return api_notes + ["api_fix_broke_syntax"]
        return []
    except SyntaxError as e:
        notes.append(f"syntax_error_before:{e.msg}@line{e.lineno}")

    fixed, fix_notes = fix_escaped_quotes_in_source(raw)
    notes = fix_notes[:] if fix_notes else notes
    if not any(x.startswith("syntax_error_before") for x in notes):
        notes.insert(0, "syntax_error_before:unknown")

    # Apply even when originally valid? also when repaired
    fixed2, api_notes = _fix_ptb_api_misuse(fixed)
    notes.extend(api_notes)
    fixed = fixed2

    try:
        ast.parse(fixed)
        path.write_text(fixed, encoding="utf-8")
        notes.append("repaired_and_saved")
        return notes
    except SyntaxError as e:
        notes.append(f"still_broken:{e.msg}@line{e.lineno}")
        try:
            lines = fixed.splitlines()
            if e.lineno and 1 <= e.lineno <= len(lines):
                notes.append(f"failing_line_repr={lines[e.lineno - 1]!r}"[:240])
        except Exception:
            pass
        # Save partial fix only if fewer syntax issues? Keep strict: don't save invalid.
        # But for debugging progress, write a .tbe_repaired.py sibling
        try:
            path.with_suffix(path.suffix + ".tbe_attempt").write_text(fixed, encoding="utf-8")
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

    # Hardcoded TOKEN = '...'  → still inject defaults; also TOKEN var assignment
    if re.search(r"^\s*TOKEN\s*=", src, re.M):
        names.add("TOKEN")
        names.add("BOT_TOKEN")
        names.add("TELEGRAM_BOT_TOKEN")

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
    tokenish = [n for n in sorted(found) if _TOKEN_NAME_HINT.search(n)]
    ordered = []
    for n in tokenish + list(_DEFAULT_TOKEN_ENVS):
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
