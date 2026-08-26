"""Images → PDF runtime for generated bots.

Uses Pillow (PIL) — real library, not a stub. Users send one or more photos;
we collect file paths and emit a single multi-page PDF.
"""
from __future__ import annotations

import io
import os
import tempfile
import time
from pathlib import Path

from app.db import connect, init_db

# In-memory session fallback when DB unavailable mid-handler
_SESSIONS: dict[int, list[str]] = {}
_MAX_IMAGES = 30


def ensure() -> None:
    init_db()
    with connect() as conn:
        conn.execute(
            "CREATE TABLE IF NOT EXISTS pdf_sessions ("
            "user_id INTEGER NOT NULL, "
            "path TEXT NOT NULL, "
            "ord INTEGER NOT NULL DEFAULT 0, "
            "created_at REAL NOT NULL DEFAULT 0, "
            "PRIMARY KEY (user_id, path))"
        )
        conn.commit()


def start_session(user_id: int, text: str = "") -> str:
    clear_session(user_id)
    return (
        "✅ جاهز لاستقبال الصور.\n"
        "أرسل صورة أو أكثر (بالترتيب اللي تريده).\n"
        "لما تخلّص: /pdfdone لإنشاء ملف PDF.\n"
        "للإلغاء: /pdfclear"
    )


def clear_session(user_id: int) -> str:
    ensure()
    uid = int(user_id)
    paths = list(_SESSIONS.pop(uid, []) or [])
    with connect() as conn:
        rows = conn.execute(
            "SELECT path FROM pdf_sessions WHERE user_id=?", (uid,)
        ).fetchall()
        conn.execute("DELETE FROM pdf_sessions WHERE user_id=?", (uid,))
        conn.commit()
    for r in rows:
        paths.append(r["path"] if isinstance(r, dict) else r[0])
    for p in paths:
        try:
            os.unlink(p)
        except OSError:
            pass
    return "🗑 تم مسح الصور المجمّعة."


def status(user_id: int, text: str = "") -> str:
    ensure()
    uid = int(user_id)
    with connect() as conn:
        n = conn.execute(
            "SELECT COUNT(*) c FROM pdf_sessions WHERE user_id=?", (uid,)
        ).fetchone()["c"]
    mem = len(_SESSIONS.get(uid, []))
    total = max(int(n), mem)
    if total <= 0:
        return "لا صور بعد — أرسل صورة أو اكتب /pdfstart"
    return f"📸 لديك {total} صورة جاهزة. أرسل المزيد أو /pdfdone لإنشاء PDF."


def add_image(user_id: int, file_path: str) -> str:
    """Register a downloaded image path into the user session."""
    ensure()
    uid = int(user_id)
    path = str(file_path or "").strip()
    if not path or not os.path.isfile(path):
        return "❌ تعذّر حفظ الصورة"
    with connect() as conn:
        n = conn.execute(
            "SELECT COUNT(*) c FROM pdf_sessions WHERE user_id=?", (uid,)
        ).fetchone()["c"]
        if int(n) >= _MAX_IMAGES:
            return f"❌ الحد الأقصى {_MAX_IMAGES} صورة لكل PDF"
        conn.execute(
            "INSERT OR REPLACE INTO pdf_sessions (user_id, path, ord, created_at) VALUES (?,?,?,?)",
            (uid, path, int(n), time.time()),
        )
        conn.commit()
        total = int(n) + 1
    _SESSIONS.setdefault(uid, []).append(path)
    return f"✅ تم استلام الصورة ({total}). أرسل المزيد أو /pdfdone"


def build_pdf(user_id: int, text: str = "") -> tuple[str, str | None]:
    """Build PDF from session images.

    Returns (message, pdf_path_or_None).
    """
    ensure()
    uid = int(user_id)
    with connect() as conn:
        rows = conn.execute(
            "SELECT path FROM pdf_sessions WHERE user_id=? ORDER BY ord ASC, created_at ASC",
            (uid,),
        ).fetchall()
    paths = [r["path"] if isinstance(r, dict) else r[0] for r in rows]
    if not paths:
        paths = list(_SESSIONS.get(uid, []))
    if not paths:
        return "❌ لا توجد صور — أرسل صوراً أولاً ثم /pdfdone", None
    try:
        from PIL import Image
    except ImportError:
        return (
            "❌ المكتبة Pillow غير مثبتة. نفّذ: pip install Pillow",
            None,
        )
    images: list = []
    try:
        for p in paths:
            if not os.path.isfile(p):
                continue
            im = Image.open(p)
            if im.mode in ("RGBA", "P"):
                im = im.convert("RGB")
            else:
                im = im.convert("RGB")
            images.append(im)
        if not images:
            return "❌ لم يُعثر على صور صالحة", None
        out_dir = Path(tempfile.gettempdir()) / "lumen_pdf"
        out_dir.mkdir(parents=True, exist_ok=True)
        out_path = str(out_dir / f"pdf_{uid}_{int(time.time())}.pdf")
        first, rest = images[0], images[1:]
        first.save(out_path, "PDF", save_all=bool(rest), append_images=rest)
        clear_session(uid)
        return (
            f"✅ تم إنشاء PDF من {len(images)} صورة — جاهز للتحميل.",
            out_path,
        )
    except Exception as exc:
        return f"❌ فشل التحويل: {type(exc).__name__}", None
    finally:
        for im in images:
            try:
                im.close()
            except Exception:
                pass


def act(entity: str, method: str, user_id: int, text: str = "") -> str:
    m = (method or "").lower()
    if m in {"start_session", "start", "begin"}:
        return start_session(user_id, text)
    if m in {"clear_session", "clear", "reset"}:
        return clear_session(user_id)
    if m in {"status", "count"}:
        return status(user_id, text)
    if m in {"build_pdf", "done", "finish", "convert"}:
        msg, _path = build_pdf(user_id, text)
        return msg
    return f"{method} is not available"
