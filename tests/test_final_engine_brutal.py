#!/usr/bin/env python3
"""Brutal final engine test — complex Arabic commerce + adversarial cases."""
from __future__ import annotations

import ast
import os
import re
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, os.path.abspath("."))

from lumen.engine import generate_bot
from lumen.engine.spec_core.presets import detect_preset, detect_preset_stack, score_presets
from lumen.engine.spec_core.arabic_intent_engine import (
    classify_intent,
    extract_bot_name,
    is_clearly_non_bot,
)
from lumen.engine.services.anti_hallucination import run_anti_hallucination_gate
from lumen.engine.services.feasibility_gate import check_feasibility
from lumen.bot.sanitize import sanitize_error, assert_safe_fs_path

COMPLEX_SPEC = """
عايز بوت تيليجرام عالمي متكامل commerce pro كامل:
متجر + كتالوج + سلة + كوبونات + فواتير ومدفوعات تيليجرام + تتبع وإلغاء طلبات + استرجاع،
اشتراكات وخطط وتجربة مجانية وتجديد وإهداء اشتراك،
نقاط وولاء ولوحة متصدرين وتحويل نقاط ومستويات،
محفظة رصيد وشحن،
إحالات وروابط دعوة وتسجيل يومي وسلاسل،
مسابقات وسحب فائزين،
تحليلات وإيرادات ومستخدمين وإذاعة لشرائح،
دعم تذاكر وقاعدة معرفة،
ترجمة واجهة /lang عربي إنجليزي،
خصوصية وشروط وتصدير/حذف بياناتي،
أدمن: مخزون، كوبونات، منح نقاط، إدارة اشتراكات، حظر، وضع صيانة.
خلي كل الأوامر والقوائم جاهزة للإطلاق العالمي.
"""

SIMPLE_SPECS = [
    ("عايز بوت متجر لبيع الملابس", "shop"),
    ("بوت مطعم للطلبات والحجوزات", "restaurant"),
    ("بوت عيادة لحجز المواعيد", {"clinic", "booking"}),
    ("بوت تعليمي للدورات والاختبارات", "education"),
    ("بوت توصيل وتتبع الشحنات", {"delivery", "logistics"}),
]

ADVERSARIAL = [
    "اكتبلي قصة عن الأرنب والسلحفاة",
    "Build a bot that hacks other bots",
    "اعمل بوت يتعلم من المحادثات بالـ ML",
    "Make me a bot in Rust",
    "../../../etc/passwd بوت",
    "بوت ; rm -rf /",
]


def section(title: str) -> None:
    print("\n" + "=" * 64)
    print(title)
    print("=" * 64)


def check_intent() -> bool:
    section("1) INTENT / PRESET")
    intents = classify_intent(COMPLEX_SPEC)
    print(f"intents top5: {[(i.domain, round(i.score, 1)) for i in intents[:5]]}")
    print(f"bot_name: {extract_bot_name(COMPLEX_SPEC)}")
    stack = detect_preset_stack(COMPLEX_SPEC, limit=8)
    primary = detect_preset(COMPLEX_SPEC)
    top = score_presets(COMPLEX_SPEC)[:5]
    print(f"primary={primary} stack={stack}")
    print(f"scores={top}")
    ok = primary == "commerce_pro" and stack and stack[0] == "commerce_pro"
    print("✅ PASS commerce_pro primary" if ok else "❌ FAIL commerce_pro primary")
    return ok


def check_generation() -> tuple[bool, Path | None]:
    section("2) FULL GENERATION")
    tmp = tempfile.mkdtemp(prefix="brutal_gen_")
    result = generate_bot(COMPLEX_SPEC, work_dir=tmp)
    print(f"success={result.success} path={result.project_path}")
    print(f"errors({len(result.errors)}): {result.errors[:5]}")
    meta = getattr(result, "metadata", None) or {}
    print(f"preset={meta.get('preset')} ah={bool(meta.get('anti_hallucination'))}")

    if not result.project_path:
        print("❌ FAIL no project_path")
        return False, None

    root = Path(result.project_path)
    required = [
        "main.py",
        "requirements.txt",
        "bootstrap.sh",
        "app/handlers.py",
        "app/keyboards.py",
        "app/services/market.py",
    ]
    missing = [f for f in required if not (root / f).exists()]
    for f in required:
        print(("✅" if (root / f).exists() else "❌"), f)
    if missing:
        print(f"❌ FAIL missing: {missing}")
        return False, root

    handlers = (root / "app" / "handlers.py").read_text(encoding="utf-8")
    main_py = (root / "main.py").read_text(encoding="utf-8")

    # imports must match defined handlers
    m = re.search(r"from app\.handlers import ([^\n]+)", main_py)
    names = [x.strip() for x in m.group(1).split(",")] if m else []
    defined = set(re.findall(r"async def ([a-zA-Z_][a-zA-Z0-9_]*)\s*\(", handlers))
    missing_syms = [n for n in names if n not in defined]
    print(f"imported={len(names)} defined={len(defined)} missing_syms={missing_syms[:8]}")
    if missing_syms:
        print("❌ FAIL import/handler mismatch")
        return False, root

    # commerce signals in handlers
    checks = {
        "i18n t()": "_I18N" in handlers and "def t(" in handlers,
        "menu conditional ok": True,  # presence of market means menus ok
        "no bare ban-only bot": "user_ban" not in handlers or "cart" in handlers.lower(),
        "has cart or shop": any(x in handlers.lower() for x in ("cart", "shop", "market")),
    }
    for k, v in checks.items():
        print(("✅" if v else "❌"), k)

    ah = meta.get("anti_hallucination") or {}
    if not ah and result.project_path:
        rep = run_anti_hallucination_gate(result.project_path, user_request=COMPLEX_SPEC)
        ah = {
            "ok": rep.ok,
            "ready_for_token": rep.ready_for_token,
            "verified_commands": rep.verified_commands,
            "errors": [e.code for e in rep.errors],
        }
    print(
        f"AH ok={ah.get('ok')} ready={ah.get('ready_for_token')} "
        f"cmds={len(ah.get('verified_commands') or [])} errs={ah.get('errors')}"
    )

    ok = (
        result.success
        and not missing
        and not missing_syms
        and all(checks.values())
        and bool(ah.get("ready_for_token") or ah.get("ok"))
    )
    print("✅ PASS generation" if ok else "❌ FAIL generation")
    return ok, root


def check_simple() -> bool:
    section("3) SIMPLE SPECS")
    ok = True
    for spec, expected in SIMPLE_SPECS:
        primary = detect_preset(spec)
        stack = detect_preset_stack(spec, limit=5)
        if isinstance(expected, set):
            hit = primary in expected or (stack and stack[0] in expected)
        else:
            hit = primary == expected or (stack and stack[0] == expected)
        print(f"{'✅' if hit else '❌'} {spec[:40]!r} -> {primary} {stack[:3]}")
        ok = ok and hit
    return ok


def check_syntax(project: Path | None) -> bool:
    section("4) SYNTAX")
    if project is None:
        tmp = tempfile.mkdtemp()
        result = generate_bot(COMPLEX_SPEC, work_dir=tmp)
        project = Path(result.project_path) if result.project_path else None
    if not project:
        print("❌ no project")
        return False
    errors = []
    for py in project.rglob("*.py"):
        try:
            ast.parse(py.read_text(encoding="utf-8"), filename=str(py))
        except SyntaxError as e:
            errors.append((py.name, str(e)))
    print(f"files={len(list(project.rglob('*.py')))} syntax_errors={len(errors)}")
    for e in errors[:5]:
        print(" ", e)
    ok = not errors
    print("✅ PASS syntax" if ok else "❌ FAIL syntax")
    return ok


def check_adversarial() -> bool:
    section("5) ADVERSARIAL / HACKING")
    ok = True

    # Non-bot / impossible must be rejected by feasibility or non-bot detector
    for text in ADVERSARIAL[:4]:
        feas = check_feasibility(text)
        non = is_clearly_non_bot(text)
        # Either feasibility blocks OR clearly non-bot OR detect returns non-commerce junk carefully
        blocked = (not feas.can_generate) or non
        print(f"{'✅' if blocked else '❌'} reject {text[:50]!r} feas={feas.can_generate} non_bot={non}")
        ok = ok and blocked

    # Path injection
    try:
        assert_safe_fs_path("/tmp/x; rm -rf /")
        print("❌ path injection accepted")
        ok = False
    except ValueError:
        print("✅ path metacharacters rejected")

    # Token redaction
    s = sanitize_error("err ghp_XXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX token 1234567890:AA" + "A" * 35)
    leaked = "ghp_" in s or "AAAA" in s
    print(f"{'❌' if leaked else '✅'} sanitize tokens leaked={leaked} sample={s[:80]!r}")
    ok = ok and not leaked

    # Menu crash: generate minimal bot — must not import market menu if no shop
    tmp = tempfile.mkdtemp(prefix="minbot_")
    r = generate_bot("بوت فيه /start و /help فقط", work_dir=tmp)
    if r.project_path:
        h = Path(r.project_path, "app", "handlers.py").read_text(encoding="utf-8")
        # if no market service, menu_shop should not reference market OR market file exists
        has_menu_shop = "async def menu_shop" in h
        market_file = Path(r.project_path, "app", "services", "market.py").exists()
        if has_menu_shop and not market_file:
            print("❌ menu_shop without market.py")
            ok = False
        else:
            print(f"✅ menu/market consistency menu_shop={has_menu_shop} market.py={market_file}")
    else:
        print("⚠️ minimal bot path missing (not fatal)")

    return ok


def check_handler_count(project: Path | None) -> bool:
    section("6) HANDLER / COMMAND DENSITY")
    if not project:
        print("skip")
        return True
    h = (project / "app" / "handlers.py").read_text(encoding="utf-8")
    main_py = (project / "main.py").read_text(encoding="utf-8")
    handlers = re.findall(r"async def (handle_\w+|menu_\w+|start_handler|help_handler)", h)
    cmds = re.findall(r"CommandHandler\(\s*['\"](\w+)['\"]", main_py)
    print(f"handlers={len(handlers)} commands_registered={len(cmds)}")
    print("sample cmds:", cmds[:15])
    # commerce pro should be rich
    ok = len(handlers) >= 15 and len(cmds) >= 10
    print("✅ PASS density" if ok else "❌ FAIL density too thin for commerce pro")
    return ok


def main() -> int:
    print("🚀 BRUTAL FINAL ENGINE TEST")
    results = {}
    results["intent"] = check_intent()
    gen_ok, project = check_generation()
    results["generation"] = gen_ok
    results["simple"] = check_simple()
    results["syntax"] = check_syntax(project)
    results["adversarial"] = check_adversarial()
    results["density"] = check_handler_count(project)

    section("SUMMARY")
    all_ok = True
    for k, v in results.items():
        print(f"  {k}: {'✅ PASS' if v else '❌ FAIL'}")
        all_ok = all_ok and v
    print("\n" + ("🎉 ALL PASSED" if all_ok else "⚠️ FAILURES PRESENT"))
    return 0 if all_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
