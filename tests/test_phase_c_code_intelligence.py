"""Phase C — Tree-sitter index, symbol graph, hybrid retrieval, blast radius."""
from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("tree_sitter")
pytest.importorskip("tree_sitter_python")
pytest.importorskip("rank_bm25")


@pytest.fixture()
def sample_repo(tmp_path: Path) -> Path:
    (tmp_path / "pkg").mkdir()
    (tmp_path / "pkg" / "__init__.py").write_text("", encoding="utf-8")
    (tmp_path / "pkg" / "a.py").write_text(
        '''
import os
from pkg.b import helper

class Greeter:
    def hello(self, name: str) -> str:
        return helper(name)

def main():
    g = Greeter()
    return g.hello("x")
''',
        encoding="utf-8",
    )
    (tmp_path / "pkg" / "b.py").write_text(
        '''
def helper(name: str) -> str:
    return f"hi {name}"

def unused():
    return 1
''',
        encoding="utf-8",
    )
    return tmp_path


def test_tree_sitter_parse_symbols(sample_repo: Path):
    from lumen.engine.services.code_intelligence import parse_python_source, index_python_repo

    src = (sample_repo / "pkg" / "a.py").read_text(encoding="utf-8")
    syms = parse_python_source(src, path="pkg/a.py")
    kinds = {s.kind for s in syms}
    assert "class" in kinds
    assert "function" in kinds or "method" in kinds
    idx = index_python_repo(sample_repo)
    assert idx["files_indexed"] >= 2
    assert idx["symbol_count"] >= 5
    assert idx["engine"] == "tree-sitter-python"


def test_symbol_graph_edges(sample_repo: Path):
    from lumen.engine.services.code_intelligence import build_symbol_graph

    g = build_symbol_graph(sample_repo)
    assert g["stats"]["node_count"] >= 5
    assert g["stats"]["edge_count"] >= 1
    rels = set(g["stats"]["by_rel"])
    assert "contains" in rels


def test_hybrid_search_finds_helper(sample_repo: Path):
    from lumen.engine.services.code_intelligence import hybrid_search

    res = hybrid_search(sample_repo, "helper greeting function", top_k=5)
    assert res["ok"] is True
    assert res["hits"]
    names = " ".join(h.get("name", "") for h in res["hits"]).lower()
    assert "helper" in names or "greeter" in names or "hello" in names


def test_blast_radius_from_helper(sample_repo: Path):
    from lumen.engine.services.code_intelligence import blast_radius, build_symbol_graph

    g = build_symbol_graph(sample_repo)
    br = blast_radius(sample_repo, symbol_name="helper", graph=g, max_depth=3)
    assert br["ok"] is True
    assert br["impacted_count"] >= 1


def test_tree_sitter_query_extracts_calls(sample_repo: Path):
    from lumen.engine.services.code_intelligence.ts_queries import extract_calls_and_defs

    src = (sample_repo / "pkg" / "a.py").read_text(encoding="utf-8")
    out = extract_calls_and_defs(src, path="pkg/a.py")
    assert out["engine"] == "tree-sitter-query"
    names = {c["name"] for c in out["calls"]}
    assert "helper" in names or "Greeter" in names or "hello" in names
    assert any(d["kind"] in {"function", "class"} for d in out["defs"])


def test_jedi_references_real(sample_repo: Path):
    pytest.importorskip("jedi")
    from lumen.engine.services.code_intelligence.jedi_analysis import find_references, names_in_module

    names = names_in_module(sample_repo, "pkg/b.py")
    assert names["ok"] is True
    assert any(n["name"] == "helper" for n in names["names"])
    # column of 'helper' in def helper
    src = (sample_repo / "pkg" / "b.py").read_text(encoding="utf-8")
    line = 2  # def helper
    col = src.splitlines()[line - 1].index("helper")
    refs = find_references(sample_repo, "pkg/b.py", line=line, column=col)
    assert refs["ok"] is True
    assert refs["engine"] == "jedi"
    assert refs["reference_count"] >= 1


def test_persistent_index_roundtrip(sample_repo: Path, tmp_path: Path):
    from lumen.engine.services.code_intelligence.persistent_index import (
        build_and_save_index,
        get_or_build_graph,
        load_index,
    )

    store = tmp_path / "idx"
    info = build_and_save_index(sample_repo, store_dir=store)
    assert info["ok"] is True
    loaded = load_index(sample_repo, store_dir=store)
    assert loaded is not None
    g2 = get_or_build_graph(sample_repo, store_dir=store, rebuild=False)
    assert g2.get("from_cache") is True
    assert g2["stats"]["node_count"] >= 5


def test_preflight_and_edit_file_impact(sample_repo: Path):
    from lumen.engine.services.code_intelligence.preflight import analyze_edit_preflight
    from lumen.engine.services.cline_runtime.agent_fs import edit_file

    pf = analyze_edit_preflight(
        sample_repo,
        "pkg/b.py",
        old_string="def helper",
        new_string="def helper",
    )
    assert pf.get("ok") is True
    assert pf.get("risk") in {"low", "medium", "high"}
    assert "engine" in pf

    # edit should attach preflight
    res = edit_file(
        str(sample_repo),
        "pkg/b.py",
        "def helper(name: str) -> str:",
        "def helper(name: str) -> str:  # touched",
    )
    assert res.get("ok") is True
    assert "preflight" in res
    assert res["preflight"].get("engine")


def test_hybrid_rrf_engine_name(sample_repo: Path):
    from lumen.engine.services.code_intelligence import hybrid_search

    res = hybrid_search(sample_repo, "helper", top_k=3)
    assert res["engine"] == "hybrid-bm25-vector-rrf"
    assert res["hits"]
