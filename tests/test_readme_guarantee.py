"""Tests for the mandatory README guarantee (weakness #6 root fix).

Every delivered project MUST have a clear README with token setup + run
instructions, regardless of whether the agent wrote one. This closes the
'generated but not production-ready' gap: the market judges 'does the bot
run first time? is there a clear README? is the token easy to set?'.
"""
from __future__ import annotations

from pathlib import Path

from lumen.bot.generation_steps.helpers import ensure_project_readme


# ---------------------------------------------------------------------------
# Minimal README template (Arabic + English, token setup, run instructions)
# ---------------------------------------------------------------------------
_README_TEMPLATE = """\
# {title}

## نظرة عامة
بوت تيليجرام تم توليده. للحصول على التوكن تحدث مع [@BotFather](https://t.me/BotFather).

## إعداد التوكن
1. افتح @BotFather على تيليجرام.
2. أرسل /newbot واتبع الخطوات.
3. ضع التوكن في متغير البيئة BOT_TOKEN:
   ```bash
   export BOT_TOKEN="123456:ABC..."
   ```

## التشغيل
```bash
pip install -r requirements.txt
python main.py
```

## Docker (اختياري)
```bash
docker build -t my-bot .
docker run --env BOT_TOKEN="..." my-bot
```

## ملاحظات
- تأكد من عدم تشغيل نسخة أخرى من نفس البوت لتفادي 409 Conflict.
- التوكن يجب أن يأتي من BotFather فقط.
"""


def _ensure_project_readme(project_path: Path, *, request: str = "") -> Path:
    """Inject a clear README.md if missing or too thin (< 200 chars / no token)."""
    readme = project_path / "README.md"
    existing = ""
    if readme.is_file():
        try:
            existing = readme.read_text(encoding="utf-8", errors="replace")
        except Exception:
            existing = ""
    _low = existing.lower()
    _adequate = (
        len(existing.strip()) >= 200
        and ("token" in _low or "bot_token" in _low or "telegram_bot_token" in _low)
        and ("python" in _low or "docker" in _low or "run" in _low)
    )
    if _adequate:
        return readme
    title = (request.strip()[:80] if request.strip() else "Telegram Bot")
    try:
        readme.write_text(_README_TEMPLATE.format(title=title), encoding="utf-8")
    except Exception:
        pass
    return readme


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------
class TestReadmeGuarantee:
    """The README guarantee must work for: missing, thin, and adequate READMEs."""

    def test_injects_readme_when_missing(self, tmp_path):
        """If no README.md exists, one must be injected with token + run instructions."""
        (tmp_path / "main.py").write_text("print('hi')", encoding="utf-8")
        result = ensure_project_readme(tmp_path, request="بوت طقس")
        assert result.is_file(), "README.md was not created"
        content = result.read_text(encoding="utf-8")
        # Must contain token setup instructions.
        assert "BOT_TOKEN" in content or "token" in content.lower(), \
            "README missing token setup instructions"
        # Must contain run instructions.
        assert "python" in content.lower() or "docker" in content.lower(), \
            "README missing run instructions"
        # Must be substantial (not a one-liner stub).
        assert len(content.strip()) >= 200, \
            f"README too thin ({len(content.strip())} chars)"

    def test_replaces_thin_readme(self, tmp_path):
        """If README.md exists but is too thin (< 200 chars / no token), replace it."""
        (tmp_path / "README.md").write_text("# Bot\n\nA bot.", encoding="utf-8")
        result = ensure_project_readme(tmp_path, request="weather bot")
        content = result.read_text(encoding="utf-8")
        assert "BOT_TOKEN" in content or "token" in content.lower(), \
            "Thin README was not upgraded with token instructions"
        assert len(content.strip()) >= 200

    def test_preserves_adequate_readme(self, tmp_path):
        """If README.md already has token + run instructions (>= 200 chars), keep it."""
        good = (
            "# My Awesome Bot\n\n"
            "## Setup\n\n"
            "Set the BOT_TOKEN environment variable:\n\n"
            "```bash\nexport BOT_TOKEN=...\n```\n\n"
            "## Run\n\n"
            "```bash\npython main.py\n```\n\n"
            "## Docker\n\n"
            "```bash\ndocker build -t bot .\ndocker run --env BOT_TOKEN=... bot\n```\n"
        )
        (tmp_path / "README.md").write_text(good, encoding="utf-8")
        result = ensure_project_readme(tmp_path, request="awesome bot")
        content = result.read_text(encoding="utf-8")
        assert content == good, "Adequate README was modified — should be preserved"

    def test_readme_includes_docker_section_when_dockerfile_present(self, tmp_path):
        """When a Dockerfile exists, the README should mention Docker deployment."""
        (tmp_path / "main.py").write_text("print('hi')", encoding="utf-8")
        (tmp_path / "Dockerfile").write_text("FROM python:3.12-slim\n", encoding="utf-8")
        result = ensure_project_readme(tmp_path, request="deploy bot")
        content = result.read_text(encoding="utf-8")
        assert "docker" in content.lower(), \
            "README should mention Docker when Dockerfile is present"

    def test_readme_works_without_request(self, tmp_path):
        """ensure_project_readme must work even with an empty request string."""
        (tmp_path / "main.py").write_text("print('hi')", encoding="utf-8")
        result = ensure_project_readme(tmp_path, request="")
        assert result.is_file()
        content = result.read_text(encoding="utf-8")
        assert "BOT_TOKEN" in content or "token" in content.lower()
