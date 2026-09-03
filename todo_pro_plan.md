# Lumen Pro Plan — Implementation Todo

## 1. Plan Config Module
- [x] Create `pro_plan.py` — single source of truth (price, duration, resources, includes)

## 2. State / Phase / Catalog
- [x] Add `PRO_PLAN` phase to `EngineUiPhase` enum (`models.py`)
- [x] Register actions in catalog: `show_more_plans`, `view_pro_plan`, `buy_pro_plan` (`catalog.py`)
- [x] Add short aliases `smp`, `vpp`, `bpp` to `_ACTION_SHORT` (`signed_callback.py`)
- [x] Fix pre-existing missing aliases `dash_backup`→`dbk`, `dash_versions`→`dv`

## 3. Controller / Buttons / Render
- [x] BILLING buttons: "عرض المزيد" (blue) → reveals "🚀 Lumen Pro" (green) via `billing_expanded` slot (`controller.py`)
- [x] PRO_PLAN buttons: "اشترك — 2000 ⭐" (green) + "رجوع للرصيد" (blue) (`controller.py`)
- [x] Action handlers: show_more_plans, view_pro_plan, buy_pro_plan (`controller.py`)
- [x] nav_back PRO_PLAN → BILLING; home clears billing_expanded + pro_buy_requested slots
- [x] Button styles: `buy_pro_plan` + `view_pro_plan` in success group, `show_more_plans` in primary (`keyboards.py`)
- [x] Render PRO_PLAN HTML card with price/stars/duration (`render.py`)

## 4. Payments & Rich Messages
- [x] Rich Messages native `<table>` for resources on PRO_PLAN phase (`callback_router.py`)
- [x] `buy_pro_plan` triggers `send_invoice` with XTR currency, 2000 stars, empty provider_token (`callback_router.py`)
- [x] Create `payment_handlers.py` — pre-checkout (ok=True) + successful payment (verify + persist 30-day sub)
- [x] Register handlers in `main.py` (`_wire()`)

## 5. Testing
- [x] All 10 files compile (`py_compile`)
- [x] 19 dedicated Pro Plan tests pass (`test_pro_plan.py`)
- [x] 7 wiring tests pass (`test_button_engine_wiring.py`)
- [x] 9 bottom-nav/batch6 tests pass
- [x] Stray duplicate `pro_plan.py` cleaned up

## 6. Deploy
- [ ] Commit all changes to git
- [ ] Push to Lumen branch
- [ ] Verify push reached remote
