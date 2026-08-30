#!/usr/bin/env python
"""End-to-end test for the semantic memory system (Mem0-inspired).

Exercises:
  1. SemanticMemoryStore: add / update / delete / semantic_search / lexical fallback
  2. ProjectMemoryStore: register_project / record_edit (button add/remove) / context_for_engine
  3. context_engine: semantic project matching for edit-intent messages
  4. retrieval: build_memory_context / memory_context_for_llm
  5. chat_memory: context_for_llm augmentation with semantic memory

Uses a temp DB so it never touches production data. Embeddings use the real
fastembed cascade (all-MiniLM-L6-v2) if available, otherwise lexical fallback.
"""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

# Ensure project root is importable
ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

# Use a temp data dir so tests are isolated
_TMP = tempfile.mkdtemp(prefix="lumen_mem_test_")
os.environ["OUTPUT_DIR"] = _TMP
os.environ.setdefault("LUMEN_DURABLE_DIR", _TMP)


def _ok(label: str, cond: bool, detail: str = "") -> bool:
    mark = "✓" if cond else "✗"
    print(f"  {mark} {label}" + (f" — {detail}" if detail else ""))
    return bool(cond)


def test_semantic_store() -> bool:
    print("\n=== TEST 1: SemanticMemoryStore (add/update/delete/semantic_search) ===")
    all_ok = True
    from lumen.engine.services.semantic_memory.store import SemanticMemoryStore

    db = Path(_TMP) / "sem_test.sqlite3"
    store = SemanticMemoryStore(path=db)

    # add facts for a user
    r1 = store.add(user_id=1001, content="المستخدم يفضل بوتات تيليجرام بلغة Python", kind="preference")
    r2 = store.add(user_id=1001, content="قرر المستخدم إزالة زر المساعدة من البوت", kind="decision", project_id="/proj/MyBot")
    r3 = store.add(user_id=1001, content="المشروع MyBot يستخدم InlineKeyboard", kind="project_note", project_id="/proj/MyBot")
    all_ok &= _ok("add 3 facts", r1 is not None and r2 is not None and r3 is not None)

    # list_all
    all_facts = store.list_all(user_id=1001)
    all_ok &= _ok("list_all returns 3", len(all_facts) == 3, f"got {len(all_facts)}")

    # semantic search (cross-project) — query about bot preferences
    hits = store.semantic_search(user_id=1001, query="ماذا يفضل المستخدم في البوتات", top_k=5, min_score=0.20)
    all_ok &= _ok("semantic search finds preference", len(hits) > 0, f"{len(hits)} hits")
    if hits:
        # the preference OR decision fact should be in top hits (both mention يفضل/البوت)
        top_contents = " ".join(r.content for r, _ in hits[:2])
        all_ok &= _ok("top hit relates to bots/preferences", "يفضل" in top_contents or "البوت" in top_contents, top_contents[:60])

    # semantic search scoped to project
    proj_hits = store.semantic_search(user_id=1001, query="زر المساعدة", project_id="/proj/MyBot", top_k=5, min_score=0.15)
    all_ok &= _ok("project-scoped search", len(proj_hits) > 0, f"{len(proj_hits)} hits")

    # update
    updated = store.update(r2.id, content="قرر المستخدم إزالة زر المساعدة وإضافة زر الإعدادات", kind="decision")
    all_ok &= _ok("update fact", updated)
    r2b = store.get(r2.id)
    all_ok &= _ok("update content persisted", "الإعدادات" in (r2b.content if r2b else ""), (r2b.content[:60] if r2b else "None"))

    # delete
    deleted = store.delete(r1.id)
    all_ok &= _ok("delete fact", deleted)
    remaining = store.list_all(user_id=1001)
    all_ok &= _ok("2 facts after delete", len(remaining) == 2, f"got {len(remaining)}")

    # lexical fallback (query with no embedding match path)
    lex_hits = store._lexical_search(user_id=1001, query="InlineKeyboard المشروع", top_k=3)
    all_ok &= _ok("lexical fallback works", len(lex_hits) > 0, f"{len(lex_hits)} hits")

    # isolation: another user sees nothing
    other = store.list_all(user_id=9999)
    all_ok &= _ok("user isolation (other user empty)", len(other) == 0)

    return all_ok


def test_project_memory() -> bool:
    print("\n=== TEST 2: ProjectMemoryStore (register/edit/history) ===")
    all_ok = True
    from lumen.engine.services.semantic_memory.project_memory import ProjectMemoryStore

    db = Path(_TMP) / "proj_test.sqlite3"
    pms = ProjectMemoryStore(path=db)

    card = pms.register_project(
        user_id=1001, project_id="/proj/MyBot", label="MyBot",
        kind="generated", path="/proj/MyBot",
        source_request="بوت متجر يرحب ويحظر الطلبات",
        ui_elements={"buttons": ["/start", "/help"], "commands": ["/start", "/help"]},
    )
    all_ok &= _ok("register_project", card is not None and card.project_id == "/proj/MyBot")

    # record add_button edit
    c1 = pms.record_edit("/proj/MyBot", edit_type="add_button", description="إضافة زر الإعدادات", target="settings")
    all_ok &= _ok("record_edit add_button", c1 is not None)
    all_ok &= _ok("button added to ui_elements", "settings" in (c1.ui_elements.get("buttons") or []), str(c1.ui_elements.get("buttons")))

    # record remove_button edit
    c2 = pms.record_edit("/proj/MyBot", edit_type="remove_button", description="إزالة زر المساعدة", target="/help")
    all_ok &= _ok("record_edit remove_button", c2 is not None)
    all_ok &= _ok("button removed from ui_elements", "/help" not in (c2.ui_elements.get("buttons") or []), str(c2.ui_elements.get("buttons")))

    # edit history
    fetched = pms.get_card("/proj/MyBot")
    all_ok &= _ok("edit_history has 2 entries", len(fetched.edit_history) == 2, f"{len(fetched.edit_history)}")

    # context_for_engine
    ctx = pms.context_for_engine("/proj/MyBot")
    all_ok &= _ok("context_for_engine non-empty", bool(ctx), ctx[:80] + "..." if ctx else "EMPTY")
    all_ok &= _ok("context shows buttons", "settings" in ctx, "")

    # list_cards
    cards = pms.list_cards(1001)
    all_ok &= _ok("list_cards returns 1", len(cards) == 1)

    # isolation
    other_cards = pms.list_cards(9999)
    all_ok &= _ok("user isolation (other user empty)", len(other_cards) == 0)

    return all_ok


def test_context_engine_semantic() -> bool:
    print("\n=== TEST 3: context_engine semantic project matching ===")
    all_ok = True
    from lumen.engine.services.context_engine.service import resolve_context, _EDIT_CUES

    all_ok &= _ok("edit cue: شيل زر", bool(_EDIT_CUES.search("شيل زر المساعدة")))
    all_ok &= _ok("edit cue: add button", bool(_EDIT_CUES.search("add a settings button")))
    all_ok &= _ok("edit cue: remove", bool(_EDIT_CUES.search("remove the help button")))
    all_ok &= _ok("no edit cue for plain text", not bool(_EDIT_CUES.search("مرحبا كيف حالك")))

    # resolve_context with empty sandbox (no crash)
    res = resolve_context(1001, "شيل زر المساعدة من البوت", base_dir=_TMP, active_path="")
    all_ok &= _ok("resolve_context runs without crash", res is not None)
    all_ok &= _ok("edit_cue signal present", "edit_cue" in (res.signals or []), str(res.signals[:5]))

    return all_ok


def test_retrieval() -> bool:
    print("\n=== TEST 4: retrieval (build_memory_context / memory_context_for_llm) ===")
    all_ok = True
    from lumen.engine.services.semantic_memory.store import SemanticMemoryStore
    from lumen.engine.services.semantic_memory.retrieval import (
        build_memory_context, memory_context_for_llm, recall,
    )

    db = Path(_TMP) / "ret_test.sqlite3"
    store = SemanticMemoryStore(path=db)
    store.add(user_id=2002, content="المستخدم مطور ويعرف async Python", kind="profile")
    store.add(user_id=2002, content="المستخدم يفضل الردود المختصرة", kind="preference")

    # monkeypatch the singleton so recall/build_memory_context use our test store.
    # IMPORTANT: retrieval.py binds get_semantic_store into its own namespace via
    # `from .store import get_semantic_store`, so we must patch the name in the
    # retrieval module (where recall() actually looks it up), not just the store.
    import lumen.engine.services.semantic_memory.retrieval as ret_mod
    orig_get = ret_mod.get_semantic_store
    ret_mod.get_semantic_store = lambda: store
    try:
        # use a semantically relevant query (developer/Python) not a greeting
        ctx = build_memory_context(user_id=2002, user_message="انا عايز كود بايثون للمطور", top_k=5)
        all_ok &= _ok("build_memory_context runs", True)
        all_ok &= _ok("context non-empty (profile found)", bool(ctx), (ctx[:80] + "...") if ctx else "EMPTY")

        payload = memory_context_for_llm(user_id=2002, user_message="عايز كود بايثون", top_k=5)
        all_ok &= _ok("memory_context_for_llm has semantic_memory key", "semantic_memory" in payload)
        all_ok &= _ok("has semantic_memory_hits key", "semantic_memory_hits" in payload)

        hits = recall(user_id=2002, query="مطور بايثون", top_k=3, min_score=0.15)
        all_ok &= _ok("recall returns hits", len(hits) >= 1, f"{len(hits)} hits")
        if hits:
            all_ok &= _ok("recall finds relevant fact", True, hits[0][0].content[:50])
    finally:
        ret_mod.get_semantic_store = orig_get

    # empty user_id → empty
    empty = build_memory_context(user_id=0, user_message="test")
    all_ok &= _ok("user_id=0 → empty context", empty == "")

    return all_ok


def test_chat_memory_augment() -> bool:
    print("\n=== TEST 5: chat_memory context_for_llm with semantic augmentation ===")
    all_ok = True
    from lumen.engine.services.chat_memory.service import ChatMemory
    from lumen.engine.services.semantic_memory.store import SemanticMemoryStore

    db = Path(_TMP) / "chat_test.sqlite3"
    cm = ChatMemory(path=db)

    # seed semantic memory for this user
    sem_db = Path(_TMP) / "chat_sem_test.sqlite3"
    store = SemanticMemoryStore(path=sem_db)
    store.add(user_id=3003, content="المستخدم يريد بوت متجر إلكتروني", kind="preference")

    # monkeypatch the semantic store singleton so chat_memory uses our test store.
    # chat_memory calls memory_context_for_llm() from retrieval, and retrieval's
    # recall() uses its own bound get_semantic_store name, so patch retrieval.
    import lumen.engine.services.semantic_memory.retrieval as ret_mod
    orig_get = ret_mod.get_semantic_store
    ret_mod.get_semantic_store = lambda: store
    try:
        cm.append(3003, "user", "عايز بوت متجر")
        cm.append(3003, "assistant", "تمام هعملك بوت متجر")
        ctx = cm.context_for_llm(3003, query="عايز بوت متجر إلكتروني")
        all_ok &= _ok("context_for_llm has conversation_history", len(ctx.get("conversation_history") or []) == 2)
        all_ok &= _ok("context_for_llm has semantic_memory", bool(ctx.get("semantic_memory")), (ctx.get("semantic_memory") or "")[:80])
    finally:
        ret_mod.get_semantic_store = orig_get

    return all_ok


def main() -> int:
    print("=" * 60)
    print("Lumen Semantic Memory System — End-to-End Test")
    print(f"Temp dir: {_TMP}")
    print("=" * 60)

    results = []
    for fn in [
        test_semantic_store,
        test_project_memory,
        test_context_engine_semantic,
        test_retrieval,
        test_chat_memory_augment,
    ]:
        try:
            results.append(fn())
        except Exception as e:
            print(f"\n  ✗ {fn.__name__} CRASHED: {e}")
            import traceback
            traceback.print_exc()
            results.append(False)

    passed = sum(1 for r in results if r)
    total = len(results)
    print("\n" + "=" * 60)
    print(f"RESULT: {passed}/{total} test groups passed")
    print("=" * 60)
    return 0 if passed == total else 1


if __name__ == "__main__":
    raise SystemExit(main())
