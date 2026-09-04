
"""Cancel issued before agent_loop must still be visible inside the loop."""
from pathlib import Path
from unittest.mock import patch


def test_cancel_not_cleared_by_agent_loop_start(tmp_path: Path):
    import os
    os.environ["OPENAI_API_KEY"] = "sk-test"
    os.environ["CLINE_ROUTER"] = "local"
    for k in ("AZURE_FOUNDRY_KEY", "AZURE_FOUNDRY_ENDPOINT", "DEEPSEEK_API_KEY"):
        os.environ.pop(k, None)

    from lumen.engine.services.generation_cancel import (
        request_cancel, clear_cancel, is_cancelled,
    )
    from lumen.engine.services.cline_runtime.agent_loop import run_agent
    from lumen.engine.services.cline_runtime import agent_brain

    uid = 55501
    clear_cancel(uid)
    # Simulate: generation started (heartbeat cleared), then user cancelled
    # BEFORE first agent step — flag must remain when loop begins.
    request_cancel(uid)
    assert is_cancelled(uid)

    with patch.object(
        agent_brain,
        "_invoke_choice",
        return_value='{"tool":"finish","summary":"x"}',
    ):
        state = run_agent(
            work_dir=tmp_path,
            goal="echo",
            ir_dict={"user_id": uid, "preferred_keys": ["echo"]},
            max_steps=2,
        )

    assert is_cancelled(uid), "agent_loop must not clear cancel at start"
    assert state.stop_reason == "cancelled_by_user" or state.metadata.get("cancelled")
    clear_cancel(uid)
