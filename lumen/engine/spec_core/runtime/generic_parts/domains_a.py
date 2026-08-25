def _clinic(m, uid, text):
    if m in {"slots", "list", "schedule", "view"}:
        rows = _list("clinic", status="open", limit=20)
        if not rows:
            for h in ("09:00", "11:00", "14:00", "16:00"):
                _insert("clinic", 0, f"Slot {h}", f"Available {h}", "open")
            rows = _list("clinic", status="open", limit=20)
        return _fmt(rows, "No clinic slots")
    if m in {"book", "create", "add", "reserve"}:
        return f"Booked clinic appointment #{_insert('clinic', uid, text or f'Appt {uid}', 'booked', 'booked')}: {text or 'appt'}"
    if m in {"cancel", "delete"}:
        iid = _first_id(text)
        return f"Cancelled #{iid}" if iid and _set_status(iid, "cancelled", user_id=uid) else "Usage: <id>"
    if m in {"my", "mine"}:
        return _fmt(_list("clinic", user_id=uid, status=None, limit=20), "No appointments")
    return ""


def _jobs(m, uid, text):
    if m in {"list", "search", "view"}:
        rows = _list("jobs", status="open", limit=30)
        if not rows:
            for t in ("Backend Engineer", "Product Designer", "Growth Marketer"):
                _insert("jobs", 0, t, "Remote", "open")
            rows = _list("jobs", status="open", limit=30)
        return _fmt(rows, "No jobs")
    if m in {"post", "create", "add"}:
        return f"Job posted #{_insert('jobs', uid, text or 'Job', text, 'open')}"
    if m in {"apply", "submit"}:
        iid = _first_id(text)
        if not iid:
            return "Usage: <job_id> [note]"
        job = _get(iid)
        if not job or job["service"] != "jobs":
            return "Job not found"
        return f"Application #{_insert('job_apps', uid, f'App→#{iid}', _rest(text) or 'app', 'submitted', ref_id=iid)}"
    if m in {"my_apps", "mine", "my"}:
        return _fmt(_list("job_apps", user_id=uid, status=None, limit=30), "No applications")
    return ""


def _edu(m, uid, text):
    if m in {"course_list", "list", "catalog", "view"}:
        rows = _list("courses", status="open", limit=30)
        if not rows:
            for t, p in (("Python 101", 0), ("Bots Pro", 29), ("SQL", 19)):
                _insert("courses", 0, t, f"price={p}", "open", amount=p)
            rows = _list("courses", status="open", limit=30)
        return _fmt(rows, "No courses")
    if m in {"enroll", "course_enroll", "join", "buy"}:
        iid = _first_id(text) or 0
        return f"Enrolled #{_insert('enrollments', uid, _rest(text) or f'course #{iid}', 'enrolled', 'active', ref_id=iid)}"
    if m in {"quiz_start", "quiz"}:
        return f"Quiz #{_insert('quizzes', uid, 'Quiz', text or 'default', 'in_progress')} started"
    if m in {"quiz_score", "score"}:
        score = int(text.split()[0]) if text and text.split()[0].isdigit() else 0
        return f"Score saved #{_insert('quizzes', uid, 'Score', f'score={score}', 'done', amount=score)}"
    if m in {"homework_submit", "submit"}:
        return f"Homework #{_insert('homework', uid, 'HW', text or 'sub', 'submitted')}"
    if m in {"certificate_issue", "certificate"}:
        return f"Certificate #{_insert('certificates', uid, 'Cert', text or 'done', 'issued')}"
    if m in {"progress_view", "progress"}:
        ens = _list("enrollments", user_id=uid, status=None, limit=20)
        qs = _list("quizzes", user_id=uid, status="done", limit=50)
        done = len(qs)
        enrolled = max(len(ens), 1)
        pct = min(100, int(100 * done / max(enrolled * 3, 1)))
        return (
            f"Progress ~{pct}% (quizzes done={done}, enrollments={len(ens)})\n"
            + _fmt(ens, "no enrollments")
        )
    if m in {"lesson_list", "lessons"}:
        return _fmt(_list("lessons", status="open", limit=20), "No lessons")
    if m in {"lesson_open", "open_lesson"}:
        iid = _first_id(text)
        row = _get(iid) if iid else None
        return f"Lesson #{iid}: {row['title']}\n{row['body']}" if row else f"Opened #{_insert('lessons', 0, text or 'Lesson', 'body', 'open')}"
    return ""


def _events(m, uid, text):
    if m in {"list", "view", "search"}:
        rows = _list("events", status="open", limit=30)
        if not rows:
            _insert("events", 0, "Meetup", "soon", "open")
            rows = _list("events", status="open", limit=30)
        return _fmt(rows, "No events")
    if m in {"create", "add"}:
        return f"Event #{_insert('events', uid, text or 'Event', text, 'open')}"
    if m in {"rsvp", "join", "book"}:
        iid = _first_id(text)
        return f"RSVP #{_insert('rsvps', uid, f'RSVP→#{iid}', 'yes', 'confirmed', ref_id=iid or 0)}" if iid else "Usage: <event_id>"
    return ""


def _restaurant(m, uid, text):
    if m in {"menu_view", "menu", "list", "view", "catalog"}:
        rows = _list("menu", status="open", limit=40)
        if not rows:
            for t, p in (("Burger", 45), ("Pasta", 55), ("Salad", 30)):
                _insert("menu", 0, t, f"EGP {p}", "open", amount=p)
            rows = _list("menu", status="open", limit=40)
        return _fmt(rows, "Empty menu")
    if m in {"menu_order", "order", "buy", "create"}:
        return f"Order #{_insert('rest_orders', uid, text or 'Order', text, 'pending')}"
    if m in {"order_status", "status", "track"}:
        iid = _first_id(text)
        if iid:
            row = _get(iid)
            if row:
                return f"Order #{iid}: {row['status']} — {row['title']}"
        return _fmt(_list("rest_orders", user_id=uid, status=None, limit=10), "No orders")
    if m in {"table_book", "book", "reserve"}:
        return f"Table #{_insert('tables', uid, text or 'Table', 'reserved', 'reserved')}"
    return ""


def _auction(m, uid, text):
    if m in {"list", "view", "search"}:
        rows = _list("auctions", status="open", limit=30)
        if not rows:
            _insert("auctions", 0, "Rare Item", "start 100", "open", amount=100)
            rows = _list("auctions", status="open", limit=30)
        return _fmt(rows, "No auctions")
    if m in {"create", "add"}:
        nums = re.findall(r"\d+(?:\.\d+)?", text or "")
        amt = float(nums[0]) if nums else 0.0
        return f"Auction #{_insert('auctions', uid, text or 'Auction', text, 'open', amount=amt)} (start={amt})"
    if m in {"bid", "offer"}:
        iid = _first_id(text)
        nums = re.findall(r"\d+(?:\.\d+)?", _rest(text))
        if not iid or not nums:
            return "Usage: <auction_id> <amount>"
        amt = float(nums[0])
        row = _get(iid)
        if not row or row["service"] != "auctions":
            return "Auction not found"
        if amt <= float(row["amount"] or 0):
            return f"Bid must be > current {row['amount']}"
        with connect() as conn:
            conn.execute("UPDATE domain_items SET amount=?, updated_at=? WHERE id=?", (amt, _now(), iid))
            conn.commit()
        return f"Bid #{_insert('bids', uid, f'Bid→#{iid}', f'amount={amt}', 'active', amount=amt, ref_id=iid)} accepted"
    if m in {"my_bids", "mine"}:
        return _fmt(_list("bids", user_id=uid, status=None, limit=30), "No bids")
    return ""


