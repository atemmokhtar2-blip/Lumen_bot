def cart_add(user_id: int, product_id: int, qty: int = 1) -> bool:
    ensure()
    seed_demo_catalog()
    qty = max(1, int(qty))
    prod = get_product(product_id)
    if not prod:
        return False
    with connect() as conn:
        conn.execute(
            "INSERT INTO cart_items (user_id, product_id, qty) VALUES (?,?,?) "
            "ON CONFLICT(user_id, product_id) DO UPDATE SET qty=qty+excluded.qty",
            (user_id, product_id, qty),
        )
        conn.commit()
    return True


def cart_view(user_id: int) -> str:
    ensure()
    with connect() as conn:
        rows = conn.execute(
            "SELECT c.product_id, c.qty, p.title, p.price_cents, p.currency "
            "FROM cart_items c LEFT JOIN products p ON p.id=c.product_id "
            "WHERE c.user_id=?",
            (user_id,),
        ).fetchall()
    if not rows:
        return "Cart empty"
    lines = []
    total = 0
    cur = "USD"
    for r in rows:
        line_total = int(r["price_cents"] or 0) * int(r["qty"])
        total += line_total
        cur = r["currency"] or cur
        lines.append(f"#{r['product_id']} {r['title']} x{r['qty']} = {line_total/100:.2f}")
    lines.append(f"Total: {total/100:.2f} {cur}")
    return "\n".join(lines)


def cart_clear(user_id: int) -> int:
    ensure()
    with connect() as conn:
        cur = conn.execute("DELETE FROM cart_items WHERE user_id=?", (user_id,))
        conn.commit()
        return int(cur.rowcount)


def cart_checkout(user_id: int) -> str:
    """Create pending orders for cart lines. Only clear lines that succeeded.

    Stock is reserved atomically inside place_order — partial success keeps
    failed lines in the cart (no silent overselling + wipe).
    """
    ensure()
    seed_demo_catalog()
    with connect() as conn:
        rows = conn.execute(
            "SELECT product_id, qty FROM cart_items WHERE user_id=?",
            (user_id,),
        ).fetchall()
    if not rows:
        return "Cart empty — add items with /cartadd <product_id>"
    order_ids: list[int] = []
    failed: list[str] = []
    for r in rows:
        pid = int(r["product_id"])
        qty = int(r["qty"] or 1)
        ok_qty = 0
        for _ in range(max(1, qty)):
            oid = place_order(user_id, str(pid))
            if oid:
                order_ids.append(oid)
                ok_qty += 1
            else:
                failed.append(f"#{pid}")
                break
        with connect() as conn:
            if ok_qty >= max(1, qty):
                conn.execute(
                    "DELETE FROM cart_items WHERE user_id=? AND product_id=?",
                    (user_id, pid),
                )
            elif ok_qty > 0:
                conn.execute(
                    "UPDATE cart_items SET qty = qty - ? WHERE user_id=? AND product_id=?",
                    (ok_qty, user_id, pid),
                )
            conn.commit()
    if not order_ids:
        return "Checkout failed — stock unavailable for cart items"
    msg = f"Checkout OK — orders: {', '.join(f'#{i}' for i in order_ids)}"
    if failed:
        msg += f" | partial fail (no stock): {', '.join(sorted(set(failed)))}"
    return msg


def wishlist_add(user_id: int, product_id: int) -> str:
    ensure()
    seed_demo_catalog()
    prod = get_product(product_id)
    if not prod:
        return f"Product #{product_id} not found. /shop to list."
    with connect() as conn:
        conn.execute(
            "INSERT INTO extras_kv (user_id, kind, body, status) VALUES (?,?,?, 'open')",
            (user_id, "wishlist", f"{product_id}:{prod['title']}"),
        )
        conn.commit()
    return f"Wishlist + {prod['title']}"


def wishlist_view(user_id: int) -> str:
    ensure()
    with connect() as conn:
        rows = conn.execute(
            "SELECT id, body FROM extras_kv WHERE user_id=? AND kind='wishlist' AND status='open' ORDER BY id DESC LIMIT 30",
            (user_id,),
        ).fetchall()
    if not rows:
        return "Wishlist empty"
    return "\n".join(f"#{r['id']} {r['body']}" for r in rows)


def refund_request(user_id: int, order_id: int) -> str:
    ensure()
    order = get_order(order_id)
    if not order or int(order["user_id"]) != int(user_id):
        return "Order not found"
    with connect() as conn:
        conn.execute(
            "INSERT INTO extras_kv (user_id, kind, body, status) VALUES (?,?,?, 'open')",
            (user_id, "refund", f"order:{order_id}"),
        )
        conn.commit()
    return f"Refund requested for order #{order_id} (pending staff review)"


def digital_deliver(user_id: int, order_id: int) -> str:
    """Ownership-safe digital delivery — only the order owner can redeem."""
    ensure()
    order = get_user_order(int(user_id), int(order_id))
    if not order:
        return "Order not found"
    if order["status"] != "paid":
        return f"Order #{order_id} status={order['status']} — pay first"
    return f"Digital delivery for order #{order_id}: unlock code DL-{order_id}-{user_id % 10000:04d}"


def shipping_set(user_id: int, address: str) -> str:
    ensure()
    address = (address or "").strip()
    if len(address) < 5:
        return "Usage: send address text after the command"
    with connect() as conn:
        conn.execute(
            "INSERT INTO extras_kv (user_id, kind, body, status) VALUES (?,?,?, 'open')",
            (user_id, "shipping", address[:500]),
        )
        conn.commit()
    return "Shipping address saved"


def review_add(user_id: int, text: str) -> str:
    ensure()
    text = (text or "").strip()
    if len(text) < 2:
        return "Usage: /reviewadd <product_id> <text>"
    with connect() as conn:
        conn.execute(
            "INSERT INTO extras_kv (user_id, kind, body, status) VALUES (?,?,?, 'open')",
            (user_id, "review", text[:1000]),
        )
        conn.commit()
    return "Review saved — thank you"



# ═══════════════════════════════════════════════════════════════════
# Enterprise depth layer — multi-step commerce, SaaS, marketplace, audit
# ═══════════════════════════════════════════════════════════════════


