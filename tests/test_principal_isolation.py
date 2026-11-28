from __future__ import annotations

import json

from lumen.engine.services.multi_agent.blackboard import FileBlackboard, MemoryBlackboard
from lumen.engine.services.multi_agent.state import AgentState
from lumen.engine.services.multi_agent.orchestrator import (
    continue_after_confirm,
    resume_after_confirm,
)
from lumen.engine.services.multi_agent.hitl import (
    confirm_action,
    reject_action,
    consume_execute_grant,
)
from lumen.engine.services.user_sandbox import get_tenant_sandbox


def test_agent_state_principal_round_trip_and_legacy_default() -> None:
    state = AgentState(user_id=42)
    assert state.principal_id == "telegram:42"
    restored = AgentState.from_dict(state.to_dict())
    assert restored.principal_id == state.principal_id

    legacy = AgentState.from_dict({"user_id": 42, "schema_version": 2})
    assert legacy.principal_id == "legacy:user:42"
    assert legacy.schema_version == 3
    try:
        AgentState.from_dict({"schema_version": 999})
    except ValueError as exc:
        assert str(exc) == "unsupported_agent_state_schema"
    else:
        raise AssertionError("future AgentState schema was silently accepted")
    telegram = AgentState(user_id=42, principal_id="telegram:42")
    assert AgentState.from_dict(telegram.to_dict()).principal_id == "telegram:42"


def test_memory_blackboard_scopes_latest_state_by_principal() -> None:
    board = MemoryBlackboard()
    telegram = AgentState(user_id=77, principal_id="telegram:77")
    tenant = AgentState(user_id=77, principal_id="tenant:acme")
    board.put(telegram)
    board.put(tenant)

    assert board.latest_for_principal("telegram:77").state_id == telegram.state_id
    assert board.latest_for_principal("tenant:acme").state_id == tenant.state_id
    assert board.latest_for_user(77).state_id == telegram.state_id


def test_file_blackboard_scopes_principals_and_reads_legacy_index(tmp_path) -> None:
    board = FileBlackboard(tmp_path)
    telegram = AgentState(user_id=88, principal_id="telegram:88")
    tenant = AgentState(user_id=88, principal_id="tenant:org-88")
    board.put(telegram)
    board.put(tenant)

    assert board.latest_for_principal("telegram:88").state_id == telegram.state_id
    assert board.latest_for_principal("tenant:org-88").state_id == tenant.state_id
    assert board.latest_for_user(88).state_id == telegram.state_id

    # Simulate an index entry written by the pre-principal file store.
    legacy = AgentState(user_id=89)
    (tmp_path / f"{legacy.state_id}.json").write_text(
        json.dumps({**legacy.to_dict(), "principal_id": "legacy:user:89"}),
        encoding="utf-8",
    )
    index_path = tmp_path / "_index.json"
    index = json.loads(index_path.read_text(encoding="utf-8"))
    index[legacy.state_id] = {
        "user_id": 89,
        "status": legacy.status,
        "updated_at": legacy.updated_at,
    }
    index_path.write_text(json.dumps(index), encoding="utf-8")
    assert board.latest_for_principal("legacy:user:89").state_id == legacy.state_id
    assert board.latest_for_user(89) is None



def test_tenant_sandbox_uses_full_tenant_digest_not_numeric_user_id(tmp_path) -> None:
    first = get_tenant_sandbox("tenant-alpha", tmp_path)
    second = get_tenant_sandbox("tenant-beta", tmp_path)

    assert first.root != second.root
    assert first.root.parts[-1] != second.root.parts[-1]
    assert 0 <= first.user_id < 2**63
    assert 0 <= second.user_id < 2**63
    assert first.root.is_relative_to(tmp_path / "tenants")
    assert second.root.is_relative_to(tmp_path / "tenants")



def test_state_id_cannot_be_reassigned_to_another_principal(tmp_path) -> None:
    original = AgentState(
        state_id="shared-state",
        user_id=100,
        principal_id="telegram:100",
    )
    attacker = AgentState(
        state_id="shared-state",
        user_id=100,
        principal_id="tenant:other",
    )

    memory = MemoryBlackboard()
    memory.put(original)
    try:
        memory.put(attacker)
    except PermissionError as exc:
        assert str(exc) == "agent_state_owner_mismatch"
    else:
        raise AssertionError("memory store accepted cross-principal overwrite")

    files = FileBlackboard(tmp_path / "file-board")
    files.put(original)
    try:
        files.put(attacker)
    except PermissionError as exc:
        assert str(exc) == "agent_state_owner_mismatch"
    else:
        raise AssertionError("file store accepted cross-principal overwrite")



def test_ambiguous_legacy_states_are_not_exposed_as_telegram_states(tmp_path) -> None:
    legacy = AgentState(user_id=42, principal_id="legacy:user:42")

    memory = MemoryBlackboard()
    memory.put(legacy)
    assert memory.latest_for_principal("legacy:user:42") is legacy
    assert memory.latest_for_user(42) is None

    files = FileBlackboard(tmp_path / "legacy-board")
    files.put(legacy)
    assert files.latest_for_principal("legacy:user:42").state_id == legacy.state_id
    assert files.latest_for_user(42) is None


def test_hitl_rejects_same_numeric_user_with_different_principal(tmp_path) -> None:
    tenant_state = AgentState(
        state_id="tenant-owned-state",
        user_id=42,
        principal_id="tenant:acme",
    )
    board = MemoryBlackboard()
    board.put(tenant_state)

    ok, state, reason = confirm_action(
        tenant_state.state_id,
        "action",
        user_id=42,
        principal_id="telegram:42",
        confirm_token="not-a-valid-token",
        board=board,
    )
    assert not ok and reason == "principal_mismatch"
    assert state.principal_id == "tenant:acme"

    ok, state, reason = reject_action(
        tenant_state.state_id,
        "action",
        user_id=42,
        principal_id="telegram:42",
        board=board,
    )
    assert not ok and reason == "principal_mismatch"
    assert state.principal_id == "tenant:acme"

    resumed = resume_after_confirm(
        tenant_state.state_id,
        "action",
        user_id=42,
        principal_id="telegram:42",
        confirm_token="not-a-valid-token",
        board=board,
        work_dir=tmp_path,
    )
    assert resumed.final_message == "principal_mismatch"

    continued = continue_after_confirm(
        tenant_state.state_id,
        user_id=42,
        principal_id="telegram:42",
        board=board,
        work_dir=tmp_path,
    )
    assert continued.final_message == "principal_mismatch"



def test_hitl_execute_grant_is_bound_to_exact_principal() -> None:
    state = AgentState(user_id=42, principal_id="tenant:acme")
    state.extensions["hitl_execute_grant"] = {
        "tool": "host_start",
        "user_id": 42,
        "principal_id": "telegram:42",
        "params_digest": "",
        "single_use": True,
    }

    assert not consume_execute_grant(
        state,
        "host_start",
        user_id=42,
        principal_id="telegram:42",
        params={},
    )
    assert "hitl_execute_grant" in state.extensions



def test_postgres_payload_cannot_disagree_with_owner_columns() -> None:
    from lumen.engine.services.multi_agent.blackboard import PostgresBlackboardStore

    state = AgentState(user_id=42, principal_id="telegram:42")
    try:
        PostgresBlackboardStore._decode({
            "payload": state.to_dict(),
            "principal_id": "tenant:acme",
            "user_id": 42,
        })
    except ValueError as exc:
        assert str(exc) == "agent_state_principal_column_mismatch"
    else:
        raise AssertionError("PostgreSQL blackboard trusted mismatched principal payload")



def test_file_blackboard_rejects_index_payload_principal_mismatch(tmp_path) -> None:
    board = FileBlackboard(tmp_path)
    state = AgentState(user_id=91, principal_id="telegram:91")
    board.put(state)

    index_path = tmp_path / "_index.json"
    index = json.loads(index_path.read_text(encoding="utf-8"))
    index[state.state_id]["principal_id"] = "tenant:attacker"
    index_path.write_text(json.dumps(index), encoding="utf-8")

    assert board.latest_for_principal("tenant:attacker") is None
