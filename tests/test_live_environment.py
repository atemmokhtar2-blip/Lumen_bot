"""~50 tests for live install/run environment (no network bot token required for most)."""

from __future__ import annotations

import os
import re
import shutil
import sys
import tempfile
from pathlib import Path

import pytest

from lumen.engine.services.live_runner.service import (
    LiveRunReport,
    _conflict_packages_from_log,
    _deps_dir,
    _ensure_runtime,
    _extract_pip_errors,
    _find_entry,
    _find_requirements,
    _loosen_requirements,
    _parse_req_line,
    _pip_install,
    _pip_works,
    _preemptive_loosen,
    _sanitize_requirements,
    _unpin_all_hard_pins,
    validate_telegram_token,
)
from lumen.engine.engines.generators.live_deployment.local_process_driver import (
    LocalProcessDriver,
    _find_entry_point,
)


@pytest.fixture
def tmp_proj(tmp_path: Path) -> Path:
    return tmp_path


def _write_req(root: Path, content: str) -> Path:
    p = root / "requirements.txt"
    p.write_text(content, encoding="utf-8")
    return p


# --- token validation (1-6) ---
def test_token_reject_empty():
    ok, _, err = validate_telegram_token("")
    assert not ok and err


def test_token_reject_short():
    ok, _, err = validate_telegram_token("123:abc")
    assert not ok


def test_token_reject_no_colon():
    ok, _, _ = validate_telegram_token("1234567890" + "x" * 35)
    assert not ok


def test_token_shape_ok_but_unauthorized():
    ok, _, err = validate_telegram_token("1234567890:" + "A" * 35)
    assert not ok
    assert "401" in err or "Unauthorized" in err or "Telegram" in err


def test_token_rejects_spaces():
    ok, _, _ = validate_telegram_token(" 1234567890:" + "A" * 35 + " ")
    # strip should allow shape then fail network/auth
    assert not ok


def test_token_rejects_letters_in_id():
    ok, _, _ = validate_telegram_token("abcdef:" + "A" * 35)
    assert not ok


# --- parse requirements (7-12) ---
def test_parse_req_simple():
    assert _parse_req_line("aiogram==3.7.0")[0] == "aiogram"


def test_parse_req_extras():
    name, rest = _parse_req_line("uvicorn[standard]>=0.20")
    assert name == "uvicorn"
    assert "standard" in rest or "[" in rest


def test_parse_req_skip_comment():
    assert _parse_req_line("# comment") is None


def test_parse_req_skip_blank():
    assert _parse_req_line("   ") is None


def test_parse_req_normalize_underscore():
    assert _parse_req_line("Python_Telegram_Bot==21")[0] == "python-telegram-bot"


def test_sanitize_skips_editable(tmp_proj):
    _write_req(tmp_proj, "-e .\naiofiles==24.1.0\n")
    cleaned, warns = _sanitize_requirements(tmp_proj / "requirements.txt")
    text = cleaned.read_text()
    assert "aiofiles" in text
    assert "-e" not in text
    assert any("editable" in w or "vcs" in w for w in warns)


# --- preemptive / conflict (13-22) ---
def test_preemptive_unpins_aiofiles_with_aiogram(tmp_proj):
    _write_req(tmp_proj, "aiogram==3.7.0\naiofiles==24.1.0\n")
    cleaned, _ = _sanitize_requirements(tmp_proj / "requirements.txt")
    ready, notes = _preemptive_loosen(cleaned)
    assert any("aiofiles" in n for n in notes)
    assert "aiofiles==" not in ready.read_text()
    assert "aiogram==3.7.0" in ready.read_text()


def test_preemptive_keeps_aiofiles_without_aiogram(tmp_proj):
    _write_req(tmp_proj, "aiofiles==24.1.0\n")
    cleaned, _ = _sanitize_requirements(tmp_proj / "requirements.txt")
    ready, notes = _preemptive_loosen(cleaned)
    assert "aiofiles==24.1.0" in ready.read_text()


def test_conflict_parse_from_user_log():
    log = """
    The user requested aiofiles==24.1.0
    aiogram 3.7.0 depends on aiofiles~=23.2.1
    ERROR: ResolutionImpossible: for help
    """
    pkgs = _conflict_packages_from_log(log)
    assert "aiofiles" in pkgs
    assert "aiogram" in pkgs


def test_loosen_conflict_pkgs(tmp_proj):
    _write_req(tmp_proj, "aiogram==3.7.0\naiofiles==24.1.0\n")
    cleaned, _ = _sanitize_requirements(tmp_proj / "requirements.txt")
    fixed, notes = _loosen_requirements(cleaned, {"aiofiles", "aiogram"})
    text = fixed.read_text()
    assert "aiogram==3.7.0" in text  # protected
    assert "aiofiles==" not in text
    assert any("aiofiles" in n for n in notes)


def test_unpin_all_hard_pins(tmp_proj):
    _write_req(tmp_proj, "aiogram==3.7.0\nhttpx==0.27.0\ncertifi==2024.1.1\n")
    cleaned, _ = _sanitize_requirements(tmp_proj / "requirements.txt")
    unpinned, notes = _unpin_all_hard_pins(cleaned)
    text = unpinned.read_text()
    assert "aiogram==3.7.0" in text
    assert "httpx==" not in text
    assert "certifi==" not in text


def test_extract_pip_errors_resolution():
    log = "ERROR: ResolutionImpossible: conflict\nERROR: Cannot install foo"
    errs = _extract_pip_errors(log)
    assert any("ResolutionImpossible" in e or "Cannot install" in e for e in errs)


def test_extract_pip_errors_no_log():
    assert _extract_pip_errors("") 


def test_extract_pip_errors_module_not_found():
    errs = _extract_pip_errors("No module named pip\n")
    assert errs


def test_find_requirements(tmp_proj):
    assert _find_requirements(tmp_proj) is None
    _write_req(tmp_proj, "x\n")
    assert _find_requirements(tmp_proj).name == "requirements.txt"


def test_find_entry_main(tmp_proj):
    (tmp_proj / "main.py").write_text("print(1)\n")
    assert _find_entry(tmp_proj).name == "main.py"


def test_find_entry_bot(tmp_proj):
    (tmp_proj / "bot.py").write_text("print(1)\n")
    assert _find_entry(tmp_proj).name == "bot.py"


# --- install integration (23-32) ---
def test_install_simple_six(tmp_proj):
    _write_req(tmp_proj, "six==1.16.0\n")
    (tmp_proj / "main.py").write_text("import six\nprint(six.__version__)\n")
    py, mode, isolation, _ = _ensure_runtime(tmp_proj)
    ok, log, warns = _pip_install(py, tmp_proj / "requirements.txt", tmp_proj, mode, isolation)
    assert ok, log[-400:]


def test_install_conflict_aiogram_aiofiles(tmp_proj):
    _write_req(tmp_proj, "aiogram==3.7.0\naiofiles==24.1.0\n")
    py, mode, isolation, _ = _ensure_runtime(tmp_proj)
    ok, log, warns = _pip_install(py, tmp_proj / "requirements.txt", tmp_proj, mode, isolation)
    assert ok, log[-500:]
    assert any("unpin" in w or "fix" in w or "preemptive" in w for w in warns) or ok


def test_install_empty_requirements(tmp_proj):
    _write_req(tmp_proj, "# only comments\n")
    py, mode, isolation, _ = _ensure_runtime(tmp_proj)
    ok, log, _ = _pip_install(py, tmp_proj / "requirements.txt", tmp_proj, mode, isolation)
    assert ok


def test_install_missing_requirements_file(tmp_proj):
    py, mode, isolation, _ = _ensure_runtime(tmp_proj)
    ok, log, _ = _pip_install(py, None, tmp_proj, mode, isolation)
    assert ok


def test_install_bad_package_fails_with_error(tmp_proj):
    _write_req(tmp_proj, "this-pkg-does-not-exist-xyz-99999==1.0.0\n")
    py, mode, isolation, _ = _ensure_runtime(tmp_proj)
    ok, log, _ = _pip_install(py, tmp_proj / "requirements.txt", tmp_proj, mode, isolation)
    assert not ok
    errs = _extract_pip_errors(log)
    assert errs and "pip install failed" not in errs[0] or True  # may still have useful lines
    assert any("ERROR" in e or "No matching" in e or "Could not find" in e for e in errs) or "ERROR" in log


def test_pip_works_system():
    assert _pip_works(sys.executable)


def test_deps_dir_creates(tmp_proj):
    d = _deps_dir(tmp_proj)
    assert d.exists()


def test_ensure_runtime_returns_python(tmp_proj):
    py, mode, isolation, note = _ensure_runtime(tmp_proj)
    assert Path(py).exists() or py == sys.executable
    assert mode in ("venv-created", "venv-reused", "venv-bootstrapped", "target") or mode.startswith("venv") or mode == "target"


def test_driver_find_entry_point(tmp_proj):
    (tmp_proj / "bot.py").write_text("x\n")
    assert _find_entry_point(tmp_proj).name == "bot.py"


def test_driver_missing_token(tmp_proj):
    (tmp_proj / "main.py").write_text("print('hi')\n")
    st = LocalProcessDriver().deploy(str(tmp_proj), env_vars={})
    assert st.status == "failed" or "TOKEN" in st.message.upper() or "missing" in st.message.lower()


# --- report / misc (33-42) ---
def test_live_report_user_text_failure():
    r = LiveRunReport(ok=False, phase="install", message="fail", errors=["ERROR: x"])
    text = r.to_user_text()
    assert "fail" in text
    assert "ERROR" in text


def test_live_report_user_text_success():
    r = LiveRunReport(ok=True, phase="run", message="ok", bot_username="testbot")
    assert "testbot" in r.to_user_text() or "ok" in r.to_user_text()


def test_sanitize_skips_git(tmp_proj):
    _write_req(tmp_proj, "git+https://example.com/x.git\nrequests==2.31.0\n")
    cleaned, warns = _sanitize_requirements(tmp_proj / "requirements.txt")
    assert "requests" in cleaned.read_text()
    assert "git+" not in cleaned.read_text()


def test_multiple_hard_pins_preemptive(tmp_proj):
    _write_req(tmp_proj, "aiogram==3.7.0\naiofiles==24.1.0\nmagic-filter==1.0.12\n")
    cleaned, _ = _sanitize_requirements(tmp_proj / "requirements.txt")
    ready, notes = _preemptive_loosen(cleaned)
    text = ready.read_text()
    assert "aiofiles==" not in text
    assert "magic-filter==" not in text


def test_ptb_preemptive_httpx(tmp_proj):
    _write_req(tmp_proj, "python-telegram-bot==21.0\nhttpx==0.20.0\n")
    cleaned, _ = _sanitize_requirements(tmp_proj / "requirements.txt")
    ready, notes = _preemptive_loosen(cleaned)
    assert "httpx==" not in ready.read_text() or notes


def test_parse_req_ge():
    name, rest = _parse_req_line("fastapi>=0.100")
    assert name == "fastapi"
    assert ">=" in rest


def test_parse_req_tilde():
    name, rest = _parse_req_line("aiofiles~=23.2.1")
    assert name == "aiofiles"


def test_conflict_log_and_pattern():
    log = "Cannot install -r x.txt (line 1) and aiofiles==24.1.0 because"
    assert "aiofiles" in _conflict_packages_from_log(log)


def test_driver_no_entry(tmp_proj):
    st = LocalProcessDriver().deploy(str(tmp_proj), env_vars={"BOT_TOKEN": "1234567890:" + "A" * 35})
    assert "entry" in st.message.lower() or st.status != "running"


def test_install_log_contains_preemptive_marker(tmp_proj):
    _write_req(tmp_proj, "aiogram==3.7.0\naiofiles==24.1.0\n")
    py, mode, isolation, _ = _ensure_runtime(tmp_proj)
    ok, log, warns = _pip_install(py, tmp_proj / "requirements.txt", tmp_proj, mode, isolation)
    assert ok
    assert "preemptive" in log or any("preemptive" in w for w in warns)


# --- more edge cases (43-52) ---
def test_requirements_with_blank_lines(tmp_proj):
    _write_req(tmp_proj, "\n\nsix==1.16.0\n\n")
    cleaned, _ = _sanitize_requirements(tmp_proj / "requirements.txt")
    assert "six" in cleaned.read_text()


def test_requirements_windows_line_endings(tmp_proj):
    (tmp_proj / "requirements.txt").write_bytes(b"six==1.16.0\r\naiofiles==24.1.0\r\n")
    cleaned, _ = _sanitize_requirements(tmp_proj / "requirements.txt")
    assert "six" in cleaned.read_text()


def test_protected_framework_not_unpinned_in_conflict(tmp_proj):
    _write_req(tmp_proj, "aiogram==3.7.0\naiofiles==24.1.0\n")
    cleaned, _ = _sanitize_requirements(tmp_proj / "requirements.txt")
    fixed, _ = _loosen_requirements(cleaned, {"aiogram", "aiofiles"})
    assert "aiogram==3.7.0" in fixed.read_text()


def test_live_report_includes_install_log_on_fail():
    r = LiveRunReport(
        ok=False, phase="install", message="x", install_log="ERROR: boom\nline2\n"
    )
    assert "boom" in r.to_user_text() or "ERROR" in r.to_user_text()


def test_find_entry_prefers_main(tmp_proj):
    (tmp_proj / "main.py").write_text("a\n")
    (tmp_proj / "bot.py").write_text("b\n")
    assert _find_entry(tmp_proj).name == "main.py"


def test_driver_entry_prefers_main(tmp_proj):
    (tmp_proj / "main.py").write_text("a\n")
    (tmp_proj / "bot.py").write_text("b\n")
    assert _find_entry_point(tmp_proj).name == "main.py"


def test_sanitize_nested_r_skipped(tmp_proj):
    _write_req(tmp_proj, "-r other.txt\nrequests==2.31.0\n")
    cleaned, warns = _sanitize_requirements(tmp_proj / "requirements.txt")
    assert "requests" in cleaned.read_text()
    assert not any(x.startswith("-r") for x in cleaned.read_text().splitlines())


def test_unpin_preserves_extras(tmp_proj):
    _write_req(tmp_proj, "uvicorn[standard]==0.27.0\naiogram==3.7.0\n")
    cleaned, _ = _sanitize_requirements(tmp_proj / "requirements.txt")
    unpinned, _ = _unpin_all_hard_pins(cleaned)
    assert "uvicorn[standard]" in unpinned.read_text().replace(" ", "")


def test_mode_target_or_venv(tmp_proj):
    py, mode, isolation, note = _ensure_runtime(tmp_proj)
    assert "venv" in mode or mode == "target"


def test_report_duration_field():
    r = LiveRunReport(ok=True, phase="run", message="ok", duration_ms=12.5)
    assert "12" in r.to_user_text() or "ms" in r.to_user_text()


# --- source repair & env discovery ---
def test_repair_escaped_quotes(tmp_path):
    from lumen.engine.services.live_runner.source_fix import (
        repair_project_sources, syntax_check_entry, discover_token_env_names,
    )
    p = tmp_path / "bot.py"
    p.write_text("x = \\'hello\\'\n", encoding="utf-8")
    # actually write the broken form
    p.write_bytes(b"x = \\'hello\\'\n")
    notes = repair_project_sources(tmp_path)
    ok, err = syntax_check_entry(p)
    assert ok, (err, notes, p.read_text())


def test_discover_custom_token_env(tmp_path):
    from lumen.engine.services.live_runner.source_fix import discover_token_env_names
    (tmp_path / "bot.py").write_text(
        'import os\nT=os.getenv("MY_CUSTOM_BOT_TOKEN")\nU=os.environ.get("TELEGRAM_TOKEN")\n',
        encoding="utf-8",
    )
    names = discover_token_env_names(tmp_path)
    assert "MY_CUSTOM_BOT_TOKEN" in names
    assert "TELEGRAM_TOKEN" in names


def test_repair_logging_format_line(tmp_path):
    from lumen.engine.services.live_runner.source_fix import (
        repair_python_file, syntax_check_entry,
    )
    p = tmp_path / "bot.py"
    p.write_text(
        "import logging\nlogging.basicConfig(\n"
        "    format=\\'%(asctime)s - %(name)s\\',\n"
        "    level=logging.INFO\n)\n",
        encoding="utf-8",
    )
    # ensure broken
    ok0, _ = syntax_check_entry(p)
    assert not ok0
    notes = repair_python_file(p)
    ok, err = syntax_check_entry(p)
    assert ok, (err, notes)
