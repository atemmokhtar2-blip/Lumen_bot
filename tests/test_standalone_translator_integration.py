from __future__ import annotations

import os
import tempfile
from pathlib import Path


def main() -> None:
    os.environ.pop("MAESTRO_TRANSLATOR_ENABLED", None)
    from telegram_bot_engine.services.translator_client import translate_request
    assert translate_request("بوت متجر") is None

    # The live standalone-service check is opt-in; the service is not part of
    # the local repository test process. This keeps CI deterministic.
    if os.environ.get("RUN_TRANSLATOR_SERVICE_TESTS") == "1":
        os.environ["MAESTRO_TRANSLATOR_ENABLED"] = "1"
        os.environ["MAESTRO_TRANSLATOR_URL"] = os.environ.get(
            "MAESTRO_TRANSLATOR_URL", "http://127.0.0.1:18082"
        )
        os.environ["MAESTRO_TRANSLATOR_TIMEOUT_SEC"] = "10"
        payload = translate_request("عايز أعمل بوت متجر فيه منتجات ودفع ومتابعة الطلب")
        assert payload and payload["purpose"] == "shop", payload
        assert "shop_catalog" in payload["features_requested"], payload

    os.environ["MAESTRO_TRANSLATOR_ENABLED"] = "0"
    from telegram_bot_engine import generate_bot
    with tempfile.TemporaryDirectory() as root:
        os.environ["OUTPUT_DIR"] = root
        out = Path(root) / "case"
        out.mkdir()
        result = generate_bot("بوت فيه /start و /help فقط", work_dir=out, user_id=0)
        assert result.success, result.errors
        assert Path(result.project_path, "main.py").exists()


if __name__ == "__main__":
    main()
    print("standalone translator integration: OK")
