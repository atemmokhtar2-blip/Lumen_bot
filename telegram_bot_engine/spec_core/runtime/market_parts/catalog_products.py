def catalog() -> str:
    ensure()
    seed_demo_catalog()
    with connect() as conn:
        rows = conn.execute(
            "SELECT id, title, price_cents, currency, stock FROM products "
            "WHERE active=1 ORDER BY id DESC LIMIT 50"
        ).fetchall()
    if not rows:
        return "No products yet. Admin: /addproduct Title|price_cents"
    return "\n".join(
        f"#{r['id']} {r['title']} — {r['price_cents']/100:.2f} {r['currency']} (stock {r['stock']})"
        for r in rows
    )


def product_search(query: str, limit: int = 20) -> str:
    """Search products by title/category/description substring."""
    ensure()
    seed_demo_catalog()
    q = (query or "").strip()
    if not q:
        return "Usage: /productsearch <keyword>\n" + catalog()
    like = f"%{q}%"
    with connect() as conn:
        try:
            rows = conn.execute(
                "SELECT id, title, price_cents, currency, stock, category FROM products "
                "WHERE active=1 AND (title LIKE ? OR IFNULL(category,'') LIKE ? "
                "OR IFNULL(description,'') LIKE ?) ORDER BY id DESC LIMIT ?",
                (like, like, like, int(limit)),
            ).fetchall()
        except Exception:
            rows = conn.execute(
                "SELECT id, title, price_cents, currency, stock FROM products "
                "WHERE active=1 AND title LIKE ? ORDER BY id DESC LIMIT ?",
                (like, int(limit)),
            ).fetchall()
    if not rows:
        return f"No products matching «{q}»"
    lines = [f"نتائج البحث عن «{q}»:"]
    for r in rows:
        cat = ""
        try:
            if r["category"]:
                cat = f" [{r['category']}]"
        except Exception:
            cat = ""
        lines.append(
            f"#{r['id']} {r['title']}{cat} — {r['price_cents']/100:.2f} {r['currency']} (stock {r['stock']})"
        )
    lines.append("أضف للسلة: /cartadd <id>")
    return "\n".join(lines)


def product_info(product_id: int) -> str:
    """Detailed product card by id."""
    ensure()
    seed_demo_catalog()
    prod = get_product(int(product_id))
    if not prod:
        return f"Product #{product_id} not found. /shop to list."
    lines = [
        f"【 منتج #{prod['id']} 】",
        f"الاسم: {prod.get('title')}",
        f"السعر: {int(prod.get('price_cents') or 0)/100:.2f} {prod.get('currency') or 'EGP'}",
        f"المخزون: {prod.get('stock')}",
    ]
    if prod.get("category"):
        lines.append(f"التصنيف: {prod['category']}")
    if prod.get("description"):
        lines.append(f"الوصف: {prod['description']}")
    try:
        with connect() as conn:
            rev = conn.execute(
                "SELECT COUNT(*) c, AVG(rating) a FROM reviews WHERE product_id=?",
                (int(product_id),),
            ).fetchone()
            if rev and int(rev["c"] or 0) > 0:
                lines.append(f"التقييم: {float(rev['a'] or 0):.1f}/5 ({rev['c']} مراجعة)")
    except Exception:
        pass
    lines.append("أضف للسلة: /cartadd " + str(product_id))
    return "\n".join(lines)


def add_item(admin_id: int, text: str) -> int:
    """Admin-only product create. Returns 0 if unauthorized or invalid."""
    ensure()
    if not role_require(int(admin_id), "staff"):
        return 0
    title, _, price = (text or "").partition("|")
    title = title.strip() or "Item"
    try:
        price_cents = int((price or "0").strip() or "0")
    except ValueError:
        price_cents = 0
    with connect() as conn:
        cur = conn.execute(
            "INSERT INTO products (title, price_cents) VALUES (?, ?)",
            (title[:200], max(0, price_cents)),
        )
        conn.commit()
        pid = int(cur.lastrowid)
    try:
        _audit(int(admin_id), "add_item", "product", pid, title[:80])
    except Exception:
        pass
    return pid


def add_item_structured(
    admin_id: int,
    *,
    title: str,
    price_cents: int = 0,
    category: str = "",
    description: str = "",
    photo_file_id: str = "",
) -> int:
    """Multi-step flow product create — staff/admin only. Returns 0 if unauthorized."""
    ensure()
    if not role_require(int(admin_id), "staff"):
        return 0
    title = (title or "Item").strip()[:200]
    price_cents = max(0, int(price_cents or 0))
    category = (category or "")[:80]
    description = (description or "")[:2000]
    photo_file_id = (photo_file_id or "")[:200]
    with connect() as conn:
        # optional columns — ignore if schema is minimal
        try:
            cur = conn.execute(
                "INSERT INTO products (title, price_cents, category, description, photo_file_id) "
                "VALUES (?,?,?,?,?)",
                (title, price_cents, category, description, photo_file_id),
            )
        except Exception:
            cur = conn.execute(
                "INSERT INTO products (title, price_cents) VALUES (?, ?)",
                (title, price_cents),
            )
        conn.commit()
        return int(cur.lastrowid)


def seed_demo_catalog() -> int:
    """Insert a few demo products if catalog empty. Returns count added."""
    ensure()
    with connect() as conn:
        n = conn.execute("SELECT COUNT(*) AS c FROM products").fetchone()["c"]
        if int(n) > 0:
            return 0
        demo = [
            ("Starter Pack", 499, "USD", 50),
            ("Pro Pack", 1499, "USD", 30),
            ("VIP Access", 2999, "USD", 10),
        ]
        for title, price, cur, stock in demo:
            conn.execute(
                "INSERT INTO products (title, price_cents, currency, stock) VALUES (?,?,?,?)",
                (title, price, cur, stock),
            )
        conn.commit()
        return len(demo)


def recommend_products(user_id: int = 0, limit: int = 5) -> str:
    """Simple intelligent ranking: in-stock products by lowest id (stable demo rank)."""
    ensure()
    with connect() as conn:
        rows = conn.execute(
            "SELECT id, title, price_cents, currency, stock FROM products "
            "WHERE active=1 AND stock>0 ORDER BY stock DESC, id ASC LIMIT ?",
            (limit,),
        ).fetchall()
    if not rows:
        return catalog()
    return "Recommended:\n" + "\n".join(
        f"#{r['id']} {r['title']} — {r['price_cents']/100:.2f} {r['currency']}"
        for r in rows
    )


