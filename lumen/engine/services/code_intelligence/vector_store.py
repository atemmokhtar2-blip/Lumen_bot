"""Persistent local vector store for code chunks (numpy — no mock).

Production can swap to Qdrant/PGVector via CODE_VECTOR_BACKEND later.
"""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

import numpy as np

from .embeddings import cosine, embed_texts


def _store_dir(root: Path, store_dir: str | Path | None = None) -> Path:
    base = Path(store_dir) if store_dir else root / ".lumen_code_index"
    base.mkdir(parents=True, exist_ok=True)
    return base


class CodeVectorStore:
    def __init__(self, root: str | Path, *, store_dir: str | Path | None = None) -> None:
        self.root = Path(root).resolve()
        self.dir = _store_dir(self.root, store_dir)
        self.meta_path = self.dir / "vectors_meta.json"
        self.vec_path = self.dir / "vectors.npy"
        self.ids: list[str] = []
        self.metas: list[dict[str, Any]] = []
        self.matrix: np.ndarray | None = None
        self._load()

    def _load(self) -> None:
        if self.meta_path.is_file() and self.vec_path.is_file():
            try:
                meta = json.loads(self.meta_path.read_text(encoding="utf-8"))
                self.ids = list(meta.get("ids") or [])
                self.metas = list(meta.get("metas") or [])
                self.matrix = np.load(self.vec_path)
            except Exception:
                self.ids, self.metas, self.matrix = [], [], None

    def save(self) -> None:
        payload = {"ids": self.ids, "metas": self.metas, "updated_at": time.time()}
        self.meta_path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        if self.matrix is not None:
            np.save(self.vec_path, self.matrix)

    def upsert(self, ids: list[str], texts: list[str], metas: list[dict[str, Any]] | None = None) -> dict[str, Any]:
        emb = embed_texts(texts)
        vectors = emb.get("vectors") or []
        if not vectors:
            return {"ok": False, "error": "no_vectors", "provider": emb.get("provider")}
        arr = np.array(vectors, dtype=np.float32)
        metas = metas or [{} for _ in ids]
        # rebuild simple store (full replace for MVP correctness)
        id_to_idx = {i: n for n, i in enumerate(self.ids)}
        for i, _id in enumerate(ids):
            if _id in id_to_idx and self.matrix is not None:
                idx = id_to_idx[_id]
                # resize dim mismatch
                if self.matrix.shape[1] != arr.shape[1]:
                    self.ids, self.metas, self.matrix = [], [], None
                    id_to_idx = {}
                    break
                self.matrix[idx] = arr[i]
                self.metas[idx] = metas[i]
            else:
                self.ids.append(_id)
                self.metas.append(metas[i])
                if self.matrix is None:
                    self.matrix = arr[i : i + 1]
                else:
                    if self.matrix.shape[1] != arr.shape[1]:
                        self.ids, self.metas = [_id], [metas[i]]
                        self.matrix = arr[i : i + 1]
                    else:
                        self.matrix = np.vstack([self.matrix, arr[i : i + 1]])
                id_to_idx[_id] = len(self.ids) - 1
        # if broke mid-way, full rebuild
        if self.matrix is None or len(self.ids) != len(self.metas):
            self.ids = list(ids)
            self.metas = list(metas)
            self.matrix = arr
        self.save()
        result = {
            "ok": True,
            "count": len(self.ids),
            "provider": emb.get("provider"),
            "dims": int(self.matrix.shape[1]) if self.matrix is not None else 0,
            "backend": "numpy",
        }
        # Production path: also mirror to Qdrant when configured
        try:
            import os
            if (os.getenv("CODE_VECTOR_BACKEND") or "").strip().lower() in {"qdrant", "qdrant-client"}:
                from .qdrant_backend import qdrant_upsert
                q = qdrant_upsert(ids, [list(map(float, v)) for v in vectors], metas)
                result["qdrant"] = q
                if q.get("ok"):
                    result["backend"] = "qdrant+numpy"
        except Exception as exc:
            result["qdrant_error"] = type(exc).__name__
        return result

    def search(self, query: str, *, top_k: int = 10) -> list[dict[str, Any]]:
        emb = embed_texts([query])
        qv = (emb.get("vectors") or [[]])[0]
        if not qv:
            return []
        # Prefer Qdrant in production when available
        try:
            import os
            if (os.getenv("CODE_VECTOR_BACKEND") or "").strip().lower() in {"qdrant", "qdrant-client"}:
                from .qdrant_backend import qdrant_search
                hits = qdrant_search(qv, top_k=top_k)
                if hits and not (len(hits) == 1 and hits[0].get("error")):
                    return hits
        except Exception:
            pass
        if self.matrix is None or not self.ids:
            return []
        q = np.array(qv, dtype=np.float32)
        # cosine via normalized dot
        mats = self.matrix
        # handle dim mismatch
        if mats.shape[1] != q.shape[0]:
            return []
        denom = (np.linalg.norm(mats, axis=1) * (np.linalg.norm(q) or 1.0)) + 1e-9
        scores = (mats @ q) / denom
        idx = np.argsort(-scores)[: max(1, min(top_k, 50))]
        out = []
        for i in idx:
            out.append(
                {
                    "id": self.ids[int(i)],
                    "score": float(scores[int(i)]),
                    **(self.metas[int(i)] if int(i) < len(self.metas) else {}),
                }
            )
        return out


def build_vector_index_from_symbols(
    root: str | Path,
    symbols: list[dict[str, Any]],
    *,
    store_dir: str | Path | None = None,
    max_chunks: int = 500,
) -> dict[str, Any]:
    root_p = Path(root).resolve()
    store = CodeVectorStore(root_p, store_dir=store_dir)
    ids: list[str] = []
    texts: list[str] = []
    metas: list[dict[str, Any]] = []
    for s in symbols:
        if s.get("kind") not in {"function", "method", "class", "module"}:
            continue
        path = str(s.get("path") or "")
        snippet = ""
        fp = root_p / path
        if fp.is_file() and s.get("start_line"):
            try:
                lines = fp.read_text(encoding="utf-8", errors="replace").splitlines()
                a = max(0, int(s["start_line"]) - 1)
                b = min(len(lines), int(s.get("end_line") or a + 30))
                snippet = "\n".join(lines[a:b])[:3000]
            except OSError:
                snippet = str(s.get("name") or "")
        text = f"{s.get('kind')} {s.get('name')} {path}\n{snippet}"
        ids.append(str(s["id"]))
        texts.append(text)
        metas.append(
            {
                "name": s.get("name"),
                "path": path,
                "kind": s.get("kind"),
                "start_line": s.get("start_line"),
                "lang": (s.get("extras") or {}).get("lang") or "python",
            }
        )
        if len(ids) >= max_chunks:
            break
    if not ids:
        return {"ok": False, "error": "no_chunks"}
    return store.upsert(ids, texts, metas)


__all__ = ["CodeVectorStore", "build_vector_index_from_symbols"]
