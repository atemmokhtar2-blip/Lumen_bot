"""git_safe_import must use normal imports — no sys.modules pollution."""
from pathlib import Path


def test_git_safe_import_source_has_no_sys_modules_hack():
    src = Path("lumen/engine/services/git_safe_import.py").read_text()
    assert "sys.modules[" not in src
    assert "exec_module" not in src
    assert "importlib.import_module" in src


def test_get_smart_clone_returns_real_module():
    from lumen.engine.services.git_safe_import import get_smart_clone
    m = get_smart_clone()
    assert hasattr(m, "smart_clone")
    assert callable(m.smart_clone)


def test_gemini_has_function_declarations():
    src = Path("lumen/engine/services/gemini_client.py").read_text()
    assert "functionDeclarations" in src
    assert "_gemini_tools" in src
    assert "_apply_function_calls" in src
    assert "system_instruction" in src
    assert "text[:20000]" not in src
