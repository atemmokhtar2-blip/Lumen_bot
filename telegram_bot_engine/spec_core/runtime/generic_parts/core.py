def _load_runtime_data() -> dict[str, Any]:
    """Load editable runtime data (method families, FAQ seed, ...).

    Search order:
    1. Beside this module (generated projects ship generic_runtime.json here)
    2. Package data path (source tree, non-gitignored)
    3. Repo root data/templates (local override)
    """
    here = Path(__file__).resolve()
    candidates = [
        here.with_name("generic_runtime.json"),
        here.parents[2] / "data" / "templates" / "generic_runtime.json",  # telegram_bot_engine/data/...
        here.parents[3] / "data" / "templates" / "generic_runtime.json",  # repo root /data/...
    ]
    for path in candidates:
        try:
            if path.is_file():
                value = json.loads(path.read_text(encoding="utf-8"))
                if isinstance(value, dict) and value:
                    return value
        except (OSError, ValueError, TypeError):
            continue
    return {}


_RUNTIME_DATA = _load_runtime_data()


_CALC_OPS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.Mod: operator.mod,
    ast.USub: operator.neg,
    ast.UAdd: operator.pos,
}


def _safe_calc(expression: str) -> str:
    """Evaluate only a small arithmetic AST; never execute arbitrary Python."""
    if len(expression) > 200:
        raise ValueError("expression too long")
    tree = ast.parse(expression, mode="eval")
    nodes = list(ast.walk(tree))
    if len(nodes) > 40:
        raise ValueError("expression too complex")

    def visit(node: ast.AST) -> float:
        if isinstance(node, ast.Expression):
            return visit(node.body)
        if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)) and not isinstance(node.value, bool):
            return node.value
        if isinstance(node, ast.BinOp) and type(node.op) in _CALC_OPS:
            left, right = visit(node.left), visit(node.right)
            if abs(left) > 10**12 or abs(right) > 10**12:
                raise ValueError("number too large")
            return _CALC_OPS[type(node.op)](left, right)
        if isinstance(node, ast.UnaryOp) and type(node.op) in _CALC_OPS:
            return _CALC_OPS[type(node.op)](visit(node.operand))
        raise ValueError("unsupported expression")

    result = visit(tree)
    if abs(result) > 10**12:
        raise ValueError("result too large")
    return str(result)

_ENSURED = False


def ensure() -> None:
    """Idempotent schema bootstrap — runs once per process (hot path safe)."""
    global _ENSURED
    if _ENSURED:
        return
    init_db()
    with connect() as conn:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        conn.execute("PRAGMA temp_store=MEMORY")
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS domain_items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                service TEXT NOT NULL,
                user_id INTEGER NOT NULL DEFAULT 0,
                title TEXT NOT NULL DEFAULT '',
                body TEXT NOT NULL DEFAULT '',
                status TEXT NOT NULL DEFAULT 'open',
                meta TEXT NOT NULL DEFAULT '{}',
                amount REAL NOT NULL DEFAULT 0,
                ref_id INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_domain_svc ON domain_items(service, status)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_domain_user ON domain_items(user_id, service)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_domain_svc_method ON domain_items(service, title)")
        conn.commit()
    _ENSURED = True


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")


def _insert(service: str, user_id: int, title: str, body: str = "", status: str = "open",
            meta: dict[str, Any] | None = None, amount: float = 0.0, ref_id: int = 0) -> int:
    with connect() as conn:
        cur = conn.execute(
            """INSERT INTO domain_items
               (service, user_id, title, body, status, meta, amount, ref_id, updated_at)
               VALUES (?,?,?,?,?,?,?,?,?)""",
            (service[:40], int(user_id), (title or "")[:200], (body or "")[:4000], status[:40],
             json.dumps(meta or {}, ensure_ascii=False), float(amount or 0), int(ref_id or 0), _now()),
        )
        conn.commit()
        return int(cur.lastrowid)


def _list(service: str, *, user_id: int | None = None, status: str | None = "open", limit: int = 30):
    q, args = "SELECT * FROM domain_items WHERE service=?", [service]
    if user_id is not None:
        q += " AND user_id=?"
        args.append(int(user_id))
    if status:
        q += " AND status=?"; args.append(status)
    q += " ORDER BY id DESC LIMIT ?"; args.append(int(limit))
    with connect() as conn:
        return list(conn.execute(q, tuple(args)).fetchall())


def _get(iid: int):
    with connect() as conn:
        return conn.execute("SELECT * FROM domain_items WHERE id=?", (int(iid),)).fetchone()


def _set_status(iid: int, status: str, *, user_id: int | None = None) -> bool:
    with connect() as conn:
        if user_id is None:
            cur = conn.execute("UPDATE domain_items SET status=?, updated_at=? WHERE id=?",
                               (status[:40], _now(), int(iid)))
        else:
            cur = conn.execute(
                "UPDATE domain_items SET status=?, updated_at=? WHERE id=? AND user_id=?",
                (status[:40], _now(), int(iid), int(user_id)),
            )
        conn.commit()
        return int(cur.rowcount) > 0


def _fmt(rows, empty: str) -> str:
    if not rows:
        return empty
    return "\n".join(
        f"#{r['id']} [{r['status']}] {r['title'][:60] or r['body'][:60]}"
        + (f" amt={r['amount']}" if float(r["amount"] or 0) else "")
        for r in rows
    )


def _first_id(text: str):
    parts = (text or "").split()
    if parts and parts[0].lstrip("#").isdigit():
        return int(parts[0].lstrip("#"))
    return None


def _rest(text: str) -> str:
    parts = (text or "").split(None, 1)
    return parts[1] if len(parts) > 1 else ""


