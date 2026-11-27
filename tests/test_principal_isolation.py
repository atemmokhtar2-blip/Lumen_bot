from __future__ import annotations

import json

from lumen.engine.services.multi_agent.blackboard import FileBlackboard, MemoryBlackboard
from lumen.engine.services.multi_agent.state import AgentState
from lumen.engine.services.user_sandbox import get_tenant_sandbox


def test_agent_state_principal_round_trip_and_legacy_default() -> None:
    state = AgentState(user_id=42)
    assert state.principal_id == "legacy:user:42"
    restored = AgentState.from_dict(state.to_dict())
    assert restored.principal_id == state.principal_id

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
    assert board.latest_for_user(89).state_id == legacy.state_id



def test_tenant_sandbox_uses_full_tenant_digest_not_numeric_user_id(tmp_path) -> None:
    first = get_tenant_sandbox("tenant-alpha", tmp_path)
    second = get_tenant_sandbox("tenant-beta", tmp_path)

    assert first.root != second.root
    assert first.root.parts[-1] != second.root.parts[-1]
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
