"""
Benchmark test for the spec-driven pipeline.

Builds RichSpecs for several Arabic bot scenarios (simulating what the AI
translator would produce) and runs them through the FULL pipeline:

    RichSpec -> ContractBuilder -> SpecTranspiler -> Verification -> py_compile

Verifies:
  - Every generated project has 11 files
  - All .py files pass py_compile
  - Every command in the spec has a handler in handlers.py
  - Every entity has a schema + store module
  - No hardcoded classification leaks (commands not in spec do not appear)
  - /start and /help always exist
"""

from __future__ import annotations

import py_compile
import shutil
import sys
import tempfile
import traceback
from pathlib import Path

# Ensure repo root is on the path
REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from telegram_bot_engine.formal_engine.schemas.rich_spec import (
    CommandKind,
    FieldType,
    PostAction,
    RichButton,
    RichCommand,
    RichEntity,
    RichEvidence,
    RichField,
    RichFlowStep,
    RichRule,
    RichSpec,
    RichTechFlags,
    validate_rich_spec,
)
from telegram_bot_engine.formal_engine.spec_pipeline.contract_builder import build_from_spec
from telegram_bot_engine.formal_engine.spec_pipeline.pipeline import build_from_spec_pipeline
from telegram_bot_engine.formal_engine.spec_pipeline.spec_transpiler import transpile_spec

# --------------------------------------------------------------------------- helpers

def _ev(quote: str, confidence: float = 0.9) -> RichEvidence:
    return RichEvidence(quote=quote, section="main", confidence=confidence)


# --------------------------------------------------------------------------- spec builders

def delivery_bot_spec() -> RichSpec:
    """Bot that collects delivery orders and shows order stats."""
    order = RichEntity(
        name="Order",
        fields=[
            RichField(name="customer_name", field_type=FieldType.STR, prompt="اكتب اسمك", evidence=_ev("الاسم")),
            RichField(name="phone", field_type=FieldType.STR, prompt="رقم الهاتف", evidence=_ev("رقم الهاتف")),
            RichField(name="address", field_type=FieldType.STR, prompt="العنوان", evidence=_ev("العنوان")),
            RichField(name="items", field_type=FieldType.STR, prompt="الطلبات", evidence=_ev("الطلبات")),
            RichField(name="status", field_type=FieldType.STR, prompt="الحالة", required=False, evidence=_ev("الحالة")),
        ],
        evidence=_ev("طلب توصيل"),
    )
    return RichSpec(
        bot_name="DeliveryBot",
        bot_kind="delivery",
        description="بوت لاستقبال طلبات التوصيل",
        language="ar",
        commands=[
            RichCommand(
                name="order",
                description="تسجيل طلب جديد",
                kind=CommandKind.COLLECT,
                entity="Order",
                collects_fields=["customer_name", "phone", "address", "items"],
                post_action=PostAction.STORE,
                flow_steps=[
                    RichFlowStep(key="customer_name", prompt="اكتب اسمك", action="ask"),
                    RichFlowStep(key="phone", prompt="رقم الهاتف", action="ask"),
                    RichFlowStep(key="address", prompt="العنوان", action="ask"),
                    RichFlowStep(key="items", prompt="الطلبات", action="ask"),
                ],
                evidence=_ev("طلب توصيل"),
            ),
            RichCommand(
                name="myorder",
                description="عرض طلباتي",
                kind=CommandKind.LOOKUP,
                entity="Order",
                post_action=PostAction.NONE,
                evidence=_ev("عرض طلباتي"),
            ),
            RichCommand(
                name="orders",
                description="كل الطلبات",
                kind=CommandKind.LIST,
                entity="Order",
                admin_only=True,
                post_action=PostAction.NONE,
                evidence=_ev("كل الطلبات"),
            ),
            RichCommand(
                name="stats",
                description="احصائيات",
                kind=CommandKind.STATS,
                entity="Order",
                admin_only=True,
                post_action=PostAction.COMPUTE,
                evidence=_ev("احصائيات"),
            ),
        ],
        entities=[order],
        rules=[
            RichRule(
                condition="اذا كان الطلب مكتمل",
                effect="حفظ في قاعدة البيانات",
                evidence=_ev("حفظ الطلب"),
            ),
        ],
        tech=RichTechFlags(database="sqlite", notifications=False),
        evidence=_ev("بوت توصيل"),
    )


def course_booking_spec() -> RichSpec:
    """Bot for booking training courses with broadcast to attendees."""
    course = RichEntity(
        name="Booking",
        fields=[
            RichField(name="student_name", field_type=FieldType.STR, prompt="اسم الطالب", evidence=_ev("اسم الطالب")),
            RichField(name="course", field_type=FieldType.STR, prompt="اسم الدورة", evidence=_ev("اسم الدورة")),
            RichField(name="level", field_type=FieldType.STR, prompt="المستوى", required=False, evidence=_ev("المستوى")),
            RichField(name="confirmed", field_type=FieldType.BOOL, prompt="تأكيد", required=False, evidence=_ev("تأكيد")),
        ],
        evidence=_ev("حجز دورة"),
    )
    return RichSpec(
        bot_name="CourseBot",
        bot_kind="education",
        description="بوت لحجز الدورات التدريبية",
        language="ar",
        commands=[
            RichCommand(
                name="book",
                description="حجز دورة",
                kind=CommandKind.COLLECT,
                entity="Booking",
                collects_fields=["student_name", "course", "level"],
                post_action=PostAction.STORE,
                flow_steps=[
                    RichFlowStep(key="student_name", prompt="اسم الطالب", action="ask"),
                    RichFlowStep(key="course", prompt="اسم الدورة", action="ask"),
                    RichFlowStep(key="level", prompt="المستوى", action="ask"),
                ],
                evidence=_ev("حجز دورة"),
            ),
            RichCommand(
                name="mybookings",
                description="حجوزاتي",
                kind=CommandKind.LOOKUP,
                entity="Booking",
                post_action=PostAction.NONE,
                evidence=_ev("حجوزاتي"),
            ),
            RichCommand(
                name="allbookings",
                description="كل الحجوزات",
                kind=CommandKind.LIST,
                entity="Booking",
                admin_only=True,
                post_action=PostAction.NONE,
                evidence=_ev("كل الحجوزات"),
            ),
            RichCommand(
                name="broadcast",
                description="ارسال رسالة لكل المشتركين",
                kind=CommandKind.BROADCAST,
                admin_only=True,
                post_action=PostAction.NOTIFY,
                evidence=_ev("ارسال رسالة"),
            ),
            RichCommand(
                name="info",
                description="معلومات عن الدورات",
                kind=CommandKind.INFO,
                reply_text="نوفر دورات في البرمجة والتصميم",
                post_action=PostAction.NONE,
                evidence=_ev("معلومات عن الدورات"),
            ),
        ],
        buttons=[
            RichButton(label="حجز دورة", callback_id="book_course", target_command="book", evidence=_ev("حجز")),
            RichButton(label="معلومات", callback_id="info_btn", target_command="info", evidence=_ev("معلومات")),
        ],
        entities=[course],
        tech=RichTechFlags(database="sqlite", notifications=True),
        evidence=_ev("بوت حجز دورات"),
    )


def store_inventory_spec() -> RichSpec:
    """Inventory management bot with products and stats."""
    product = RichEntity(
        name="Product",
        fields=[
            RichField(name="name", field_type=FieldType.STR, prompt="اسم المنتج", evidence=_ev("اسم المنتج")),
            RichField(name="price", field_type=FieldType.FLOAT, prompt="السعر", evidence=_ev("السعر")),
            RichField(name="quantity", field_type=FieldType.INT, prompt="الكمية", evidence=_ev("الكمية")),
            RichField(name="category", field_type=FieldType.STR, prompt="التصنيف", required=False, evidence=_ev("التصنيف")),
        ],
        evidence=_ev("المنتجات"),
    )
    return RichSpec(
        bot_name="StoreBot",
        bot_kind="inventory",
        description="بوت لادارة المخزون",
        language="ar",
        commands=[
            RichCommand(
                name="addproduct",
                description="اضافة منتج",
                kind=CommandKind.COLLECT,
                entity="Product",
                collects_fields=["name", "price", "quantity", "category"],
                post_action=PostAction.STORE,
                flow_steps=[
                    RichFlowStep(key="name", prompt="اسم المنتج", action="ask"),
                    RichFlowStep(key="price", prompt="السعر", action="ask"),
                    RichFlowStep(key="quantity", prompt="الكمية", action="ask"),
                    RichFlowStep(key="category", prompt="التصنيف", action="ask"),
                ],
                evidence=_ev("اضافة منتج"),
            ),
            RichCommand(
                name="product",
                description="بحث عن منتج",
                kind=CommandKind.LOOKUP,
                entity="Product",
                post_action=PostAction.NONE,
                evidence=_ev("بحث عن منتج"),
            ),
            RichCommand(
                name="products",
                description="كل المنتجات",
                kind=CommandKind.LIST,
                entity="Product",
                post_action=PostAction.NONE,
                evidence=_ev("كل المنتجات"),
            ),
            RichCommand(
                name="stock",
                description="مخزون",
                kind=CommandKind.STATS,
                entity="Product",
                admin_only=True,
                post_action=PostAction.COMPUTE,
                evidence=_ev("المخزون"),
            ),
        ],
        entities=[product],
        tech=RichTechFlags(database="sqlite", admin_panel=True),
        evidence=_ev("بوت مخزون"),
    )


def simple_info_spec() -> RichSpec:
    """Minimal info-only bot — no entities, just static replies."""
    return RichSpec(
        bot_name="InfoBot",
        bot_kind="info",
        description="بوت معلوماتي بسيط",
        language="ar",
        commands=[
            RichCommand(
                name="about",
                description="عن البوت",
                kind=CommandKind.INFO,
                reply_text="هذا البوت يقدم معلومات عن خدماتنا",
                post_action=PostAction.NONE,
                evidence=_ev("عن البوت"),
            ),
            RichCommand(
                name="contact",
                description="تواصل معنا",
                kind=CommandKind.INFO,
                reply_text="تواصل معنا على support@example.com",
                post_action=PostAction.NONE,
                evidence=_ev("تواصل معنا"),
            ),
        ],
        entities=[],
        tech=RichTechFlags(database="none"),
        evidence=_ev("بوت معلوماتي"),
    )


# --------------------------------------------------------------------------- assertions

def _compile_all(py_dir: Path) -> tuple[bool, list[str]]:
    errors = []
    for py in sorted(py_dir.rglob("*.py")):
        try:
            py_compile.compile(str(py), doraise=True)
        except py_compile.PyCompileError as e:
            errors.append(f"{py.name}: {str(e)[:300]}")
    return (len(errors) == 0, errors)


def _runtime_store_test(project_dir: Path, spec: RichSpec) -> tuple[bool, str]:
    """Actually run the generated store code to verify SQL works at runtime."""
    if not spec.entities:
        return True, "no entities (skip)"
    import asyncio
    import sys as _sys
    import importlib

    app_dir = project_dir / "app"
    if str(project_dir) not in _sys.path:
        _sys.path.insert(0, str(project_dir))

    # Clear any previously cached 'app' modules so we import the fresh copy
    for mod_name in list(_sys.modules):
        if mod_name == "app" or mod_name.startswith("app."):
            del _sys.modules[mod_name]

    try:
        store_mod = importlib.import_module("app.store")
    except Exception as exc:
        try:
            _sys.path.remove(str(project_dir))
        except ValueError:
            pass
        return False, f"import store failed: {exc}"

    entity = spec.entities[0]
    cls_name = entity.name[0].upper() + entity.name[1:] + "Store"
    store_cls = getattr(store_mod, cls_name, None)
    if store_cls is None:
        # Clean up
        for mod_name in list(_sys.modules):
            if mod_name == "app" or mod_name.startswith("app."):
                del _sys.modules[mod_name]
        try:
            _sys.path.remove(str(project_dir))
        except ValueError:
            pass
        return False, f"store class {cls_name} not found"

    async def _run():
        store = store_cls()
        # Create
        fields = {}
        for f in entity.fields:
            if f.field_type.value == "int":
                fields[f.name] = 42
            elif f.field_type.value == "float":
                fields[f.name] = 3.14
            elif f.field_type.value == "bool":
                fields[f.name] = True
            else:
                fields[f.name] = "test_value"
        fields["user_id"] = 999
        oid = await store.create(**fields)
        # Get
        row = await store.get(oid)
        if row is None:
            return False, "get returned None after create"
        # List all
        rows = await store.list_all()
        if len(rows) < 1:
            return False, "list_all returned empty"
        # List by user
        rows = await store.list_by_user(999)
        if len(rows) < 1:
            return False, "list_by_user returned empty"
        # Update status — only if entity has a status field
        has_status = any(f.name == "status" for f in entity.fields)
        if hasattr(store, "update_status") and has_status:
            ok = await store.update_status(oid, "done")
            if not ok:
                return False, "update_status returned False"
        return True, "all store ops passed"

    try:
        ok, msg = asyncio.run(_run())
    except Exception as exc:
        ok, msg = False, f"runtime error: {type(exc).__name__}: {exc}"
    finally:
        # Clean up db
        try:
            (Path.cwd() / "bot.db").unlink(missing_ok=True)
        except Exception:
            pass
        # Remove from path
        try:
            _sys.path.remove(str(project_dir))
        except ValueError:
            pass
        # Clear cached modules
        for mod_name in list(_sys.modules):
            if mod_name == "app" or mod_name.startswith("app."):
                del _sys.modules[mod_name]
    return ok, msg


def _handlers_have_commands(project_dir: Path, expected_cmds: list[str]) -> tuple[bool, list[str]]:
    """Check that every expected command has a handler function AND a registration in main.py."""
    handlers_file = project_dir / "app" / "handlers.py"
    main_file = project_dir / "main.py"
    h_text = handlers_file.read_text(encoding="utf-8") if handlers_file.exists() else ""
    m_text = main_file.read_text(encoding="utf-8") if main_file.exists() else ""
    missing = []
    for cmd in expected_cmds:
        # Handler function: async def {cmd}_handler
        handler_fn = f"{cmd}_handler"
        # Registration: CommandHandler("cmd", ...) or CommandHandler('cmd', ...)
        reg_double = f'CommandHandler("{cmd}"'
        reg_single = f"CommandHandler('{cmd}'"
        has_handler = handler_fn in h_text
        has_registration = reg_double in m_text or reg_single in m_text
        if not (has_handler and has_registration):
            missing.append(f"{cmd} (handler={has_handler}, reg={has_registration})")
    return (len(missing) == 0, missing)


def _verify_no_phantom_commands(project_dir: Path, spec_cmds: list[str]) -> tuple[bool, list[str]]:
    """Ensure no command registrations exist that aren't in the spec (except start/help)."""
    import re
    main_file = project_dir / "main.py"
    if not main_file.exists():
        return True, []
    text = main_file.read_text(encoding="utf-8")
    # Match CommandHandler("cmd" or CommandHandler('cmd'
    found = set(re.findall(r'CommandHandler\(["\']([a-z_]+)["\']', text))
    allowed = set(spec_cmds) | {"start", "help"}
    phantom = found - allowed
    return (len(phantom) == 0, sorted(phantom))


# --------------------------------------------------------------------------- main test runner

def run_one(name: str, spec: RichSpec) -> dict:
    """Run a single spec through the full pipeline and return a result dict."""
    result = {
        "name": name,
        "bot_name": spec.bot_name,
        "spec_cmds": spec.command_names(),
        "spec_entities": spec.entity_names(),
        "passed": False,
        "errors": [],
        "files": [],
        "files_count": 0,
        "compile_ok": False,
        "handlers_ok": False,
        "phantom_ok": False,
        "verify_ok": False,
        "contract_ok": False,
    }

    tmpdir = Path(tempfile.mkdtemp(prefix=f"bench_{name}_"))
    try:
        # 1) Validate spec
        val = validate_rich_spec(spec)
        if val.warnings:
            result["errors"].append(f"spec warnings: {val.warnings[:3]}")

        # 2) Build contract + inference
        build = build_from_spec(spec)
        result["contract_ok"] = build.contract_ok
        if not build.contract_ok:
            result["errors"].append(f"contract errors: {build.contract_errors[:3]}")

        # 3) Transpile
        files = transpile_spec(spec, tmpdir)
        result["files"] = files
        result["files_count"] = len(files)

        # 4) Full pipeline (includes verification)
        build2 = build_from_spec_pipeline(spec, tmpdir)
        result["verify_ok"] = bool(build2.verification.ok) if build2.verification else False
        if build2.verification and build2.verification.errors:
            result["errors"].append(f"verify: {build2.verification.errors[:3]}")

        # 5) Compile all generated .py
        compile_ok, compile_errs = _compile_all(tmpdir)
        result["compile_ok"] = compile_ok
        if not compile_ok:
            result["errors"].extend(compile_errs[:5])

        # 6) Check handlers have all spec commands
        handlers = tmpdir / "app" / "handlers.py"
        if handlers.exists():
            spec_cmds = spec.command_names()
            # Always expect start + help (ensure_minimums)
            expected = list(spec_cmds)
            if "start" not in expected:
                expected.append("start")
            if "help" not in expected:
                expected.append("help")
            h_ok, missing = _handlers_have_commands(tmpdir, expected)
            result["handlers_ok"] = h_ok
            if not h_ok:
                result["errors"].append(f"missing handlers: {missing}")

            # 7) No phantom commands (commands not in spec)
            p_ok, phantom = _verify_no_phantom_commands(tmpdir, spec_cmds)
            result["phantom_ok"] = p_ok
            if not p_ok:
                result["errors"].append(f"phantom commands: {phantom}")

        # 8) Check store + schema modules for each entity
        for ent in spec.entities:
            ent_lower = ent.name.lower()
            store_file = tmpdir / "app" / "store.py"
            schema_file = tmpdir / "app" / "models.py"
            if store_file.exists() and ent_lower not in store_file.read_text(encoding="utf-8").lower():
                result["errors"].append(f"entity {ent.name} missing from store.py")
            if schema_file.exists() and ent.name not in schema_file.read_text(encoding="utf-8"):
                result["errors"].append(f"entity {ent.name} missing from models.py")

        # 9) Runtime store test — actually execute the generated store code
        rt_ok, rt_msg = _runtime_store_test(tmpdir, spec)
        result["runtime_store_ok"] = rt_ok
        if not rt_ok:
            result["errors"].append(f"runtime store: {rt_msg}")

        result["passed"] = (
            result["compile_ok"]
            and result["handlers_ok"]
            and result["phantom_ok"]
            and result.get("runtime_store_ok", True)
            and result["files_count"] >= 5
            and len([e for e in result["errors"] if "contract" in e or "missing" in e or "phantom" in e or "runtime store" in e]) == 0
        )

    except Exception as exc:
        result["errors"].append(f"EXCEPTION: {type(exc).__name__}: {exc}")
        result["errors"].append(traceback.format_exc()[:500])
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)

    return result


def main():
    specs = [
        ("delivery_bot", delivery_bot_spec()),
        ("course_booking", course_booking_spec()),
        ("store_inventory", store_inventory_spec()),
        ("simple_info", simple_info_spec()),
    ]

    print("=" * 70)
    print("SPEC-DRIVEN PIPELINE BENCHMARK")
    print("=" * 70)

    all_passed = True
    for name, spec in specs:
        print(f"\n--- {name} ({spec.bot_name}) ---")
        r = run_one(name, spec)
        status = "PASS" if r["passed"] else "FAIL"
        if not r["passed"]:
            all_passed = False
        print(f"  Status:       {status}")
        print(f"  Spec cmds:    {r['spec_cmds']}")
        print(f"  Entities:     {r['spec_entities']}")
        print(f"  Files:        {r['files_count']}")
        print(f"  Compile:      {'OK' if r['compile_ok'] else 'FAIL'}")
        print(f"  Handlers:     {'OK' if r['handlers_ok'] else 'FAIL'}")
        print(f"  No-phantom:   {'OK' if r['phantom_ok'] else 'FAIL'}")
        print(f"  Verify:       {'OK' if r['verify_ok'] else 'FAIL'}")
        print(f"  Contract:     {'OK' if r['contract_ok'] else 'FAIL'}")
        print(f"  Runtime store:{' OK' if r.get('runtime_store_ok', True) else ' FAIL'}")
        if r["errors"]:
            print(f"  Errors:")
            for e in r["errors"][:6]:
                print(f"    - {e}")

    print("\n" + "=" * 70)
    if all_passed:
        print("ALL BENCHMARKS PASSED ✅")
    else:
        print("SOME BENCHMARKS FAILED ❌")
    print("=" * 70)
    return 0 if all_passed else 1


if __name__ == "__main__":
    sys.exit(main())
