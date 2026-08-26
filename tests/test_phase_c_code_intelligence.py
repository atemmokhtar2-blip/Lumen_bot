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
