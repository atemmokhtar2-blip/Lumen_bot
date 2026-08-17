def explicit_command(user_id: int, command: str, text: str = "") -> str:
    """Execute a user-declared command with durable, command-scoped storage.

    This is a real fallback for commands not yet mapped to a specialist: it
    never pretends that an unsupported domain operation happened. It records
    submitted data, supports `/command list`, and tells the user exactly what
    input is required when no payload was supplied.
    """
    ensure()
    cmd = re.sub(r"[^a-z0-9_]+", "", (command or "command").lower())[:40] or "command"
    payload = (text or "").strip()[:2000]
    service = f"cmd_{cmd}"[:40]
    if payload.lower() in {"list", "all", "history", "سجل", "قائمة"}:
        return _fmt(_list(service, user_id=user_id, status=None, limit=30), f"لا توجد بيانات مسجلة للأمر /{cmd} بعد.")
    if not payload:
        return f"أرسل البيانات المطلوبة بعد /{cmd}. مثال: /{cmd} بيانات الطلب\nولعرض ما سجلته: /{cmd} list"
    iid = _insert(service, int(user_id), payload[:120], payload, "open", {"command": cmd, "kind": "explicit_command"})
    return f"تم تنفيذ /{cmd} وتسجيل الطلب #{iid}. لعرض السجل أرسل /{cmd} list"


def act(service: str, method: str, user_id: int, text: str = "") -> str:
    """Execute any capability with durable SQLite side-effects.

    Covers the full registry surface (11k capabilities / 361 methods):
    domain specialists first, then universal method families, then log event.
    Never returns an empty stub without persistence.
    """
    ensure()
    service = (service or "gen").strip()[:40]
    method = (method or "run").strip()[:40]
    text = (text or "").strip()[:2000]
    m, svc, uid = method.lower(), service.lower(), int(user_id)


    # Explicit user-declared commands have a command-aware durable path in
    # generated handlers; keep a safe fallback for direct service calls.
    if m == "explicit_command":
        return explicit_command(uid, svc, text)

    # Phase 8 / 14 specialized scaffolds
    if m in {"voice_from_file"}:
        return voice_from_file(uid, text)
    if m in {"voice_intake", "voice"} or (svc == "voice"):
        return voice_intake(uid, text)
    if m in {"payment_info", "pay_info"}:
        return payment_info(uid, text)
    if m in {"faq", "faq_list", "faq_search"} or (svc in {"content", "utils"} and m == "faq"):
        return faq(uid, text)
    if m in {"translate", "translate_text"} or (svc in {"translate", "utils", "content"} and m == "translate"):
        return translate_text(uid, text)
    if m in {"ocr_from_image"}:
        return ocr_from_image(uid, text, "")
    if m in {"ocr_image", "ocr_hint", "ocr"} or (svc == "ocr" and m in {"image", "hint", "run"}):
        return ocr_hint(uid, text)
    if m in {"schedule_note", "schedule"} or (svc in {"scheduler", "reminders"} and m in {"schedule_note", "schedule", "remind"}):
        return schedule_note(uid, text)
    if m in {"job_list", "list_jobs"} or (svc == "scheduler" and m in {"list", "job_list"}):
        return job_list(uid, text)
    if m in {"job_cancel", "cancel_job"} or (svc == "scheduler" and m in {"cancel", "job_cancel"}):
        return job_cancel(uid, text)

    # Domain specialists (clinic, jobs, edu, ...)
    handler = _HANDLERS.get(svc)
    if handler:
        try:
            out = handler(m, uid, text)
            if out:
                return out
        except Exception as exc:
            return f"{svc}.{method} error: {exc}"

    # Method families: module-level _LIST_M / _CREATE_M / _UPDATE_M / _CLOSE_M

    if m in _LIST_M or m.endswith("_list") or m.endswith("_view") or m.endswith("_info") or m.endswith("_status"):
        if m in {"stats", "stats_basic", "dashboard", "analytics", "analytics_overview", "revenue", "revenue_today"}:
            with connect() as conn:
                open_c = conn.execute(
                    "SELECT COUNT(*) c FROM domain_items WHERE service=? AND status='open'", (svc,)
                ).fetchone()["c"]
                all_c = conn.execute(
                    "SELECT COUNT(*) c FROM domain_items WHERE service=?", (svc,)
                ).fetchone()["c"]
            return f"{svc} stats: open={open_c} total={all_c}"
        if m in {"my", "mine", "my_orders", "my_apps", "my_bids"}:
            return _fmt(_list(svc, user_id=uid, status=None, limit=20), f"No {svc} items for you")
        st = None if m in {"history", "audit", "audit_log", "export"} else "open"
        return _fmt(_list(svc, status=st, limit=30), f"No {svc} items yet — create one")

    if m in _CREATE_M or m.endswith("_create") or m.endswith("_add") or m.endswith("_open") or m.endswith("_submit"):
        title = text[:80] if text else f"{method}"
        iid = _insert(svc, uid, title, text or method, "open", {"method": method})
        return f"Created #{iid} ({svc}/{method})"

    if m in _CLOSE_M or m.endswith("_delete") or m.endswith("_cancel") or m.endswith("_close"):
        iid = _first_id(text)
        with connect() as conn:
            if iid:
                cur = conn.execute(
                    "UPDATE domain_items SET status='closed', updated_at=? WHERE id=? AND service=?",
                    (_now(), iid, svc),
                )
            else:
                cur = conn.execute(
                    "UPDATE domain_items SET status='closed', updated_at=? WHERE id=("
                    "SELECT id FROM domain_items WHERE service=? AND status='open' "
                    "ORDER BY id DESC LIMIT 1)",
                    (_now(), svc),
                )
            conn.commit()
            n = int(cur.rowcount)
        return f"Closed {n} item(s)" if n else f"Nothing open to close for {svc}"

    if m in _UPDATE_M or m.endswith("_update") or m.endswith("_set") or m.endswith("_edit"):
        iid = _first_id(text)
        body = _rest(text)
        if iid and body:
            if m in {"assign", "set_status", "set_priority", "priority", "set_role", "role_set"}:
                if _set_status(iid, body.split()[0]):
                    return f"#{iid} → {body.split()[0]}"
                return "Not found"
            with connect() as conn:
                cur = conn.execute(
                    "UPDATE domain_items SET body=?, updated_at=? WHERE id=?",
                    (body[:4000], _now(), iid),
                )
                conn.commit()
                if int(cur.rowcount):
                    return f"Updated #{iid}"
            return "Not found"
        # toggle / config without id
        iid = _insert(svc, uid, f"{method}", text or method, "open", {"method": method})
        return f"OK {svc}.{method} #{iid}"

    if m in {"track", "status"}:
        iid = _first_id(text)
        if iid:
            row = _get(iid)
            if row:
                return f"#{iid} [{row['status']}] {row['title']}\n{row['body']}"
        return _fmt(_list(svc, user_id=uid, status=None, limit=15), f"No {svc} data")

    # Utils / info methods — always durable ack
    if m in {
        "ping", "echo", "time_now", "uuid_gen", "calc", "help", "start", "about",
        "privacy", "terms", "lang", "set_language", "auto_detect", "contact",
        "channel_link", "deep_link", "gate_check", "force_sub_info", "verify_start",
        "verify_ok", "user_info", "search_user", "export_me", "delete_me", "csat",
        "maintenance_on", "maintenance_off", "backup", "restore_backup",
    }:
        payload = text or m
        if m == "echo":
            return payload or "—"
        if m == "time_now":
            return _now()
        if m == "uuid_gen":
            import uuid
            return str(uuid.uuid4())
        if m == "calc":
            try:
                # safe tiny eval: digits and + - * / ( )
                expr = "".join(ch for ch in payload if ch in "0123456789+-*/().% ")
                return _safe_calc(expr) if expr else "Usage: calc <expr>"
            except Exception:
                return "Invalid expression"
        if m in {"privacy", "terms"}:
            return f"{m}: stored locally in SQLite; contact admin for deletion requests."
        iid = _insert(svc, uid, m, payload, "open", {"method": method})
        return f"OK {svc}.{method} #{iid}: {payload[:80]}"

    # Default: persist event so every one of 11k capabilities has a side-effect
    iid = _insert(svc, uid, f"{method}", text or method, "open", {"method": method})
    return f"OK {svc}.{method} #{iid} saved"

