"""
Telegram Bot Generation Engine

Active path (zero-AI, deterministic only):
  user text
    → spec_core presets + deterministic coding engines
    → anti-hallucination gate
    → project files on disk (inside per-user sandbox)

No LLM / AI provider path.
No formal/DSL/transpiler codegen path.
"""

from __future__ import annotations


from typing import TYPE_CHECKING

if TYPE_CHECKING:  # explicit for mypy/pylint/IDEs — no runtime cycle
    from .pipeline import PipelineOrchestrator as PipelineOrchestrator
    from .registry import EngineRegistry as EngineRegistry
    from .core import bootstrap as bootstrap, build_configuration as build_configuration


import os

__all__ = [
    "bootstrap", "build_configuration", "generate_bot",
    "PipelineOrchestrator", "EngineRegistry",
]




def _maybe_run_git_stage(
    *,
    original_request: str,
    project_path: str,
    stages: list,
) -> dict | None:
    """
    Optionally run GitOperationsEngine after successful generation.

    Triggered only when the user text explicitly mentions git-related actions
    (push / pull / commit / clone / git / بوش / اسحب / اعمل كوميت ...).

    STRICT RULE (non-negotiable):
      - No saved templates or ready-made bot packs.
      - Every operation is derived dynamically from the user's text
        and the just-generated project path. Nothing is pre-baked.
    """
    from pathlib import Path as _Path
    from .core.context import GenerationContext
    from .core.result import StageResult
    from .configuration import Configuration
    from .configuration.defaults import build_default_schema

    text = (original_request or "").lower()
    git_keywords = (
        "git ", "git\n", "push", "pull", "commit", "clone", "fetch",
        "بوش", "اسحب", "اسحبوا", "كوميت", "اعمل كوميت", "ادفع", "جيب من الجيت",
        "repository", "repo ", "github",
    )
    if not any(k in text for k in git_keywords):
        return None

    try:
        from .engines.generators.git_operations import GitOperationsEngine

        # Detect intended operation from user text (purely dynamic)
        op = "commit"
        if any(k in text for k in ("push", "بوش", "ادفع")):
            op = "push"
        elif any(k in text for k in ("pull", "اسحب", "اسحبوا", "جيب")):
            op = "pull"
        elif any(k in text for k in ("clone", "كلون")):
            op = "clone"
        elif any(k in text for k in ("commit", "كوميت", "اعمل كوميت")):
            op = "commit"

        cfg = Configuration(schema=build_default_schema(), sources=[])
        ctx = GenerationContext(
            request=original_request,
            config=cfg,
            work_dir=_Path(project_path),
        )
        # Pass real-execution hints so GitExecutor can act on the generated project
        ctx.artefacts["repo_path"] = project_path
        ctx.artefacts["git_operation"] = op
        ctx.artefacts["operation"] = op
        ctx.artefacts["execute_real"] = True
        ctx.artefacts["add_all"] = True
        ctx.artefacts["message"] = "chore: generated bot from user request"
        # Shape expected by UserRequestReader / GitExecutor
        ctx.artefacts["user_request"] = {
            "operation": op,
            "git_operation": op,
            "repo_path": project_path,
            "path": project_path,
            "work_dir": project_path,
            "execute_real": True,
            "add_all": True,
            "message": "chore: generated bot from user request",
            "operations": [op],
        }

        engine = GitOperationsEngine()
        result = engine.execute(ctx)

        ok = bool(getattr(result, "success", None) or getattr(result, "ok", False))
        stage_payload = {
            "ok": ok,
            "operation": op,
            "project_path": project_path,
            "outputs": getattr(result, "outputs", None) or {},
            "errors": list(getattr(result, "errors", None) or [])[:8],
        }

        if ok:
            stages.append(StageResult.ok("git_operations", outputs=stage_payload))
        else:
            stages.append(
                StageResult.failed(
                    "git_operations",
                    errors=stage_payload["errors"] or ["git_operations_failed"],
                )
            )
        return stage_payload
    except Exception as exc:
        stages.append(
            StageResult.failed("git_operations", errors=[f"{type(exc).__name__}:{exc}"])
        )
        return {"ok": False, "error": str(exc)[:200]}




def _run_intelligence_layers(
    request: str,
    *,
    user_id: int = 0,
):
    """Execute L1→L6 and return a dict used by the generation path.

    L1 understand → L2 intent → L3 question plan → L4 memory →
    L5 suggestions → L6 personalization.
    """
    from .spec_core.language_understanding import (
        understand,
        analyze_intent,
        build_question_plan,
        suggest,
        personalize,
        get_memory_engine,
    )

    out: dict = {
        "lu": None,
        "intent": None,
        "question_plan": None,
        "style": None,
        "suggestion_report": None,
        "memory_engine": None,
        "meta": {},
    }
    lu = understand(request or "")
    intent = analyze_intent(request or "", lu=lu)
    # Stage-1 harden: ensure brief features land on entities (inline menus)
    try:
        from .spec_core.language_understanding.bot_spec_extract import extract_bot_brief
        _brief = extract_bot_brief(request or "")
        _ent = getattr(lu, "entities", None)
        if _ent is not None and _brief is not None:
            if _brief.features_requested:
                # merge brief features (prefer union, brief first for order)
                merged = list(dict.fromkeys(
                    list(_brief.features_requested)
                    + list(getattr(_ent, "features_requested", None) or [])
                ))
                _ent.features_requested = merged
            if _brief.bot_name:
                _ent.bot_name = _brief.bot_name
            if _brief.purpose:
                _ent.bot_purpose = _brief.purpose
            if _brief.menu_items:
                _ent.menu_ids = [c.id for c in _brief.menu_items]
            if _brief.strict:
                _ent.strict_spec = True
            if _brief.flows:
                _ent.flows = list(_brief.flows)
            raw = dict(getattr(_ent, "raw", None) or {})
            raw["bot_brief"] = _brief.to_dict()
            _ent.raw = raw
            # Strict: REPLACE intent plan (never merge fat preset plan)
            if intent is not None and _brief.features_requested:
                try:
                    if _brief.strict:
                        intent.feature_plan = list(dict.fromkeys(list(_brief.features_requested)))
                    else:
                        plan = list(getattr(intent, "feature_plan", None) or [])
                        intent.feature_plan = list(
                            dict.fromkeys(list(_brief.features_requested) + plan)
                        )
                except Exception:
                    pass
    except Exception:
        pass
    memory_engine = None
    if user_id:
        try:
            memory_engine = get_memory_engine()
            memory_engine.remember_turn(
                int(user_id),
                request or "",
                intent=intent,
                lu=lu,
                features=list(getattr(intent, "feature_plan", None) or []),
            )
        except Exception:
            try:
                memory_engine = get_memory_engine()
            except Exception:
                memory_engine = None

    # L3 — adaptive questions (report in meta; generation continues)
    question_plan = None
    try:
        question_plan = build_question_plan(
            request or "",
            intent=intent,
            lu=lu,
            user_id=int(user_id) if user_id else None,
            remember=bool(user_id),
        )
    except Exception:
        question_plan = None

    style = personalize(
        request or "", intent=intent, lu=lu, user_id=user_id or None, memory=memory_engine
    )
    suggestion_report = suggest(
        request or "",
        intent=intent,
        lu=lu,
        user_id=user_id or None,
        memory=memory_engine,
    )

    # Stage-2 memory: store brief, corrections, recall collective knowledge
    memory_snap = None
    try:
        from .spec_core.language_understanding.learning_layer import (
            recall,
            record_turn_learning,
            apply_full_memory,
        )
        ent = getattr(lu, "entities", None)
        brief = None
        if ent is not None:
            brief = (getattr(ent, "raw", None) or {}).get("bot_brief")
            if not brief and getattr(ent, "strict_spec", False):
                brief = {
                    "bot_name": getattr(ent, "bot_name", None),
                    "purpose": getattr(ent, "bot_purpose", None),
                    "features_requested": list(getattr(ent, "features_requested", None) or []),
                    "action_ids": list(getattr(ent, "menu_ids", None) or []),
                    "strict": True,
                }
        intent_name = intent.primary.intent if intent and intent.primary else None
        record_turn_learning(
            int(user_id) if user_id else 0,
            request or "",
            brief=brief,
            intent_name=intent_name,
            features=list(getattr(ent, "features_requested", None) or []) if ent else None,
            memory=memory_engine,
        )
        if user_id:
            memory_snap = recall(
                int(user_id),
                request or "",
                memory=memory_engine,
                intent_name=intent_name,
            )
            try:
                from .spec_core.language_understanding.learning_layer import apply_full_memory
                from .spec_core.language_understanding.continuous_learning import apply_success_learning
                _new_req, _notes = apply_full_memory(
                    ent, memory_snap, request=request or ""
                )
                # Stage-3: merge success recipes when not strict
                if ent is not None:
                    strict3 = bool(getattr(ent, "strict_spec", False))
                    merged3 = apply_success_learning(
                        list(getattr(ent, "features_requested", None) or []),
                        intent_name,
                        strict=strict3,
                        memory=memory_engine,
                        user_id=int(user_id) if user_id else None,
                    )
                    try:
                        ent.features_requested = merged3
                    except Exception:
                        pass
                    # Stage-5 closed-loop: global + per-user prefer/avoid
                    try:
                        from .spec_core.language_understanding.evaluation_layer import (
                            apply_eval_to_features,
                        )
                        if ent is not None:
                            feats = list(getattr(ent, "features_requested", None) or [])
                            strict5 = bool(getattr(ent, "strict_spec", False))
                            new_feats, ev_meta = apply_eval_to_features(
                                feats,
                                int(user_id) if user_id else None,
                                strict=strict5,
                                memory=memory_engine,
                            )
                            ent.features_requested = new_feats
                            raw = dict(getattr(ent, "raw", None) or {})
                            raw["l5_tweaks"] = ev_meta
                            try:
                                ent.raw = raw
                            except Exception:
                                pass
                    except Exception:
                        pass
                    try:
                        from .spec_core.language_understanding.continuous_learning import learning_summary
                        # stash on intel via meta later
                        if not hasattr(ent, "raw") or ent.raw is None:
                            ent.raw = {}
                        ent.raw["l3_learning"] = learning_summary(
                            int(user_id) if user_id else None,
                            intent_name,
                            memory=memory_engine,
                        )
                    except Exception:
                        pass
            except Exception:
                pass
    except Exception:
        memory_snap = None

    meta = {
        "l1_domains": [
            {"domain": d.domain, "score": round(d.score, 2)}
            for d in (lu.domains or [])[:6]
        ] if lu else [],
        "l1_primary": getattr(lu, "primary_domain", None),
        "l1_preset": getattr(lu, "primary_preset", None),
        "l2_intent": intent.primary.intent if intent and intent.primary else None,
        "l2_skill": getattr(intent, "skill_level", None),
        "l2_language": getattr(intent, "language", None),
        "l2_complexity": getattr(intent, "complexity", None),
        "l2_feature_plan": list(getattr(intent, "feature_plan", None) or [])[:30],
        "l1_bot_name": getattr(getattr(lu, "entities", None), "bot_name", None) if lu else None,
        "l1_strict": bool(getattr(getattr(lu, "entities", None), "strict_spec", False)) if lu else False,
        "l1_menu": list(getattr(getattr(lu, "entities", None), "menu_ids", None) or [])[:12] if lu else [],
        "l1_flows": list(getattr(getattr(lu, "entities", None), "flows", None) or [])[:12] if lu else [],
        "l1_features": list(getattr(getattr(lu, "entities", None), "features_requested", None) or [])[:20] if lu else [],
        "l1_brief_confidence": getattr(getattr(lu, "entities", None), "brief_confidence", 0) if lu else 0,
        "l3_questions": [
            {"id": q.id, "slot": q.slot, "text": q.text[:120]}
            for q in (question_plan.questions if question_plan else [])[:6]
        ],
        "l3_should_ask": bool(
            getattr(question_plan, "should_block_generation", False) if question_plan else False
        ),
        "l4_user_id": int(user_id) if user_id else None,
        "l5_build": [s.feature for s in (suggestion_report.build if suggestion_report else [])],
        "l5_improve": [s.feature for s in (suggestion_report.improve if suggestion_report else [])],
        "l5_preventive": [
            s.feature for s in (suggestion_report.preventive if suggestion_report else [])
        ],
        "l6_style": style.to_dict() if style else None,
        "l2_memory": memory_snap.to_dict() if memory_snap else None,
    }
    out.update(
        lu=lu,
        intent=intent,
        question_plan=question_plan,
        style=style,
        suggestion_report=suggestion_report,
        memory_engine=memory_engine,
        memory_snap=memory_snap,
        meta=meta,
    )
    return out


def _apply_layers_to_session(session, intel: dict) -> None:
    """Mutate BuilderSession.selected using L2 plan + L5 suggestions + L6 filter.

    Stage-1 strict mode: if the user listed an explicit menu/commands, REPLACE
    the selection with only extracted features (no invented extras).
    """
    if session is None or not hasattr(session, "selected"):
        return
    from .spec_core.language_understanding import feature_filter_for_skill
    from .spec_core.registry import CAPABILITIES

    lu = intel.get("lu")
    ent = getattr(lu, "entities", None) if lu is not None else None
    strict = bool(getattr(ent, "strict_spec", False)) if ent is not None else False
    explicit_feats = list(getattr(ent, "features_requested", None) or []) if ent is not None else []

    if strict and explicit_feats:
        # Only what the user asked for (+ always start/help)
        chosen: set[str] = set()
        for feat in explicit_feats + ["start", "help", "lang"]:
            if feat in CAPABILITIES:
                chosen.add(feat)
            # soft aliases if exact key missing
            elif feat.replace("-", "_") in CAPABILITIES:
                chosen.add(feat.replace("-", "_"))
        if chosen:
            session.selected = chosen
            # bot name stamp
            name = getattr(ent, "bot_name", None)
            if name and hasattr(session, "set_name"):
                try:
                    session.set_name(str(name)[:40])
                except Exception:
                    pass
            elif name and hasattr(session, "name"):
                try:
                    session.name = str(name)[:40]
                except Exception:
                    pass
            return

    # L2 feature_plan first
    intent = intel.get("intent")
    plan = list(getattr(intent, "feature_plan", None) or [])
    if explicit_feats:
        plan = list(dict.fromkeys(explicit_feats + plan))
    for feat in plan:
        if feat in CAPABILITIES:
            try:
                session.selected.add(feat)
            except Exception:
                pass

    # L5 high-confidence build suggestions (skipped under strict)
    report = intel.get("suggestion_report")
    if report is not None and not strict:
        for s in list(report.build)[:10]:
            if getattr(s, "confidence", 0) >= 0.50 and getattr(s, "feature", None):
                if s.feature in CAPABILITIES:
                    try:
                        session.selected.add(s.feature)
                    except Exception:
                        pass

    # L6 skill/domain density filter
    style = intel.get("style")
    if style is not None and not strict:
        try:
            filtered = feature_filter_for_skill(list(session.selected), style)
            session.selected = set(filtered)
        except Exception:
            pass


def _stamp_style_on_spec(spec, style) -> None:
    """Apply L6 + Stage-4 adaptive description onto BotSpec (drives /start tone)."""
    if style is None or spec is None:
        return
    try:
        from .spec_core.language_understanding import style_prompt_ar, phrase

        stamp = style_prompt_ar(style)
        welcome = phrase("welcome", style, with_emoji=True)
        skill = getattr(style, "skill_level", "beginner") or "beginner"
        domain = getattr(style, "domain", "") or ""
        if hasattr(spec, "bot") and hasattr(spec.bot, "description"):
            base = (spec.bot.description or "").strip()
            if skill == "beginner":
                tip = "اكتب /help لو احتجت قائمة الأوامر."
            elif skill == "expert":
                tip = f"domain={domain} · skill=expert · /help for full map."
            else:
                tip = "استخدم الأزرار أو /help."
            parts = [welcome, base, tip, stamp]
            spec.bot.description = chr(10).join(p for p in parts if p).strip()[:700]
        if hasattr(spec, "bot") and hasattr(spec.bot, "language"):
            if getattr(style, "prefer_arabic", True) or str(
                getattr(style, "language_variant", "")
            ).startswith("ar"):
                spec.bot.language = "ar"
            elif str(getattr(style, "language_variant", "")).startswith("en"):
                spec.bot.language = "en"
    except Exception:
        pass



def _generate_bot_zero_ai(request: str, work_dir, t0: float, user_id: int = 0, *, force: bool = False, preferred_keys=None):
    """Deterministic Spec → code only. No LLM providers.

    Pipeline: L1→L6 intelligence → compose session → build_from_spec → anti-hallucination.
    preferred_keys: optional list of capability keys from Phase-2 detection.
    """
    from pathlib import Path as _Path
    import tempfile as _tempfile
    import time as _time

    from .core.result import GenerationResult, StageResult
    from .spec_core.presets import (
        detect_preset,
        detect_preset_stack,
        compose_session,
        session_for_preset,
        is_bot_request,
        default_spec_from_request,
    )
    from .spec_core.pipeline import build_from_spec

    # Phase 4: ensure capability packs overlay is loaded before detection/codegen
    try:
        from .services.capability_detection.packs import ensure_packs_loaded
        ensure_packs_loaded()
    except Exception:
        pass

    # ── Layers 1–6 ─────────────────────────────────────────────────────────
    intel: dict = {
        "lu": None,
        "intent": None,
        "style": None,
        "suggestion_report": None,
        "memory_engine": None,
        "meta": {},
    }
    try:
        intel = _run_intelligence_layers(request or "", user_id=int(user_id or 0))
        layers_meta = dict(intel.get("meta") or {})
    except Exception as _lu_exc:
        layers_meta = {"layers_error": f"{type(_lu_exc).__name__}:{str(_lu_exc)[:200]}"}

    lu = intel.get("lu")
    style = intel.get("style")
    memory_engine = intel.get("memory_engine")

    preset = detect_preset(request)
    if preset is None and not force and not is_bot_request(request):
        if not (request or "").strip():
            return None
        force = True

    if work_dir is None:
        work_dir = _Path(_tempfile.mkdtemp(prefix="spec_bot_"))
    work_dir = _Path(work_dir)
    work_dir.mkdir(parents=True, exist_ok=True)
    project_dir = work_dir / "generated_bot"
    project_dir.mkdir(parents=True, exist_ok=True)

    # Stage-1 strict: user listed exact menu → NEVER inflate with fat multi-presets
    ent = getattr(lu, "entities", None) if lu is not None else None
    strict = bool(getattr(ent, "strict_spec", False)) if ent is not None else False
    explicit_feats = list(getattr(ent, "features_requested", None) or []) if ent is not None else []

    if strict and explicit_feats:
        from .spec_core.registry import CAPABILITIES as _CAPS

        session = compose_session(["echo_basic"], user_id=user_id, request=request)
        locked = {"start", "help", "lang"}
        for feat in explicit_feats:
            if feat in _CAPS:
                locked.add(feat)
        session.selected = set(locked)
        bot_name = getattr(ent, "bot_name", None)
        if bot_name:
            try:
                if hasattr(session, "set_name"):
                    session.set_name(str(bot_name)[:40])
                elif hasattr(session, "name"):
                    session.name = str(bot_name)[:40]
            except Exception:
                pass
        spec = session.to_spec()
        if bot_name and hasattr(spec, "bot") and hasattr(spec.bot, "name"):
            try:
                spec.bot.name = str(bot_name)[:40]
            except Exception:
                pass
        if hasattr(spec, "bot") and hasattr(spec.bot, "description"):
            menu = list(getattr(ent, "menu_ids", None) or [])
            flows = list(getattr(ent, "flows", None) or [])
            spec.bot.description = (
                f"Strict user brief: {bot_name or 'bot'} | "
                f"menu={','.join(menu[:8])} | flows={','.join(flows[:6])}"
            )[:500]
        _stamp_style_on_spec(spec, style)
        tag = f"strict:{(bot_name or 'bot')}"
        layers_meta["strict_locked_features"] = sorted(locked)
    else:
        # Multi-intent composition for open-ended requests only
        stack = detect_preset_stack(request, limit=8)
        if lu and getattr(lu, "primary_preset", None):
            lead = lu.primary_preset
            if lead and lead not in (stack or []):
                stack = [lead] + list(stack or [])
        if stack:
            session = compose_session(stack, user_id=user_id, request=request)
            _apply_layers_to_session(session, intel)
            spec = session.to_spec()
            _stamp_style_on_spec(spec, style)
            tag = "+".join(stack)
        elif preset:
            session = session_for_preset(preset, user_id=user_id)
            if hasattr(session, "selected"):
                _apply_layers_to_session(session, intel)
                spec = session.to_spec()
            else:
                spec = (
                    session.to_spec()
                    if hasattr(session, "to_spec")
                    else session_for_preset(preset, user_id=user_id).to_spec()
                )
            _stamp_style_on_spec(spec, style)
            tag = preset
        else:
            spec = default_spec_from_request(request, user_id=user_id)
            _stamp_style_on_spec(spec, style)
            tag = detect_preset(request) or "market_default"

    # ── Phase 2: Capability Detection keys → session / spec ─────────────
    detection_meta: dict = {}
    try:
        from .services.capability_detection.integration import (
            feature_keys,
            metadata_from_report,
            run_detection,
        )
        from .spec_core.registry import CAPABILITIES as _CAPS_DET

        keys = [k for k in (preferred_keys or []) if isinstance(k, str) and k in _CAPS_DET]
        if not keys:
            _det_report = run_detection(request)
            keys = feature_keys(_det_report, include_core=True)
            detection_meta = metadata_from_report(_det_report)
        else:
            detection_meta = {
                "capability_detection": {
                    "matched_keys": [k for k in keys if k not in {"start", "help"}],
                    "source": "caller",
                    "status": "provided",
                }
            }

        # Apply detection keys to the session/spec that will be built.
        # - preferred_keys from caller (Telegram/API Phase-2): always merge (authoritative)
        # - auto-detected only: merge unless strict user menu already locked features
        apply_keys = bool(keys) and (
            bool(preferred_keys) or not (strict and explicit_feats)
        )
        if apply_keys:
            sess = locals().get("session")
            if sess is None or not hasattr(sess, "selected"):
                try:
                    sess = compose_session(
                        ["echo_basic"], user_id=user_id, request=request
                    )
                except Exception:
                    sess = None
            if sess is not None and hasattr(sess, "selected"):
                # When preferred_keys provided under strict, rebuild selection from
                # strict locked set UNION detection keys (never drop user menu)
                if preferred_keys and strict and explicit_feats:
                    base = set(sess.selected) if sess.selected else {"start", "help"}
                    for k in list(explicit_feats) + list(keys) + ["start", "help", "lang"]:
                        if isinstance(k, str) and k in _CAPS_DET:
                            base.add(k)
                    sess.selected = base
                else:
                    for k in keys:
                        if k in _CAPS_DET:
                            try:
                                sess.selected.add(k)
                            except Exception:
                                pass
                    if preferred_keys:
                        for k in preferred_keys:
                            if isinstance(k, str) and k in _CAPS_DET:
                                try:
                                    sess.selected.add(k)
                                except Exception:
                                    pass
                if hasattr(sess, "to_spec"):
                    spec = sess.to_spec()
                    _stamp_style_on_spec(spec, style)
                    tag = (
                        f"detect:{'+'.join(k for k in keys if k not in {'start','help'})[:5] or 'core'}"
                    )
            layers_meta["detection_preferred_keys"] = [
                k for k in keys if k not in {"start", "help"}
            ]
            if detection_meta:
                layers_meta.update(detection_meta)
        elif keys:
            # Record what detection wanted even if not applied (strict path)
            layers_meta["detection_preferred_keys_skipped_strict"] = [
                k for k in keys if k not in {"start", "help"}
            ]
            if detection_meta:
                layers_meta.update(detection_meta)
    except Exception as _det_exc:
        layers_meta["detection_error"] = f"{type(_det_exc).__name__}:{str(_det_exc)[:160]}"
        detection_meta = {}
    if detection_meta:
        try:
            layers_meta.update(detection_meta)
        except Exception:
            pass

    result = build_from_spec(spec, project_dir)
    elapsed = _time.perf_counter() - t0
    # Stage-4: bake narrative into metadata for delivery
    try:
        from .spec_core.language_understanding.smart_generation import build_narrative
        _ent = getattr(lu, "entities", None) if lu is not None else None
        _feats = list(layers_meta.get("l1_features") or layers_meta.get("l2_feature_plan") or [])
        if hasattr(spec, "features") and spec.features:
            _feats = list(dict.fromkeys(
                _feats + [getattr(f, "feature", None) or getattr(f, "id", None) for f in spec.features]
            ))
            _feats = [str(x) for x in _feats if x]
        _nav = build_narrative(
            request or "",
            style=style,
            entities=_ent,
            intent_name=layers_meta.get("l2_intent"),
            features=_feats,
            learning=layers_meta.get("l3_learning") if isinstance(layers_meta.get("l3_learning"), dict) else None,
            memory_snap=layers_meta.get("l2_memory") if isinstance(layers_meta.get("l2_memory"), dict) else None,
            strict=bool(layers_meta.get("l1_strict")),
            bot_name=str(
                layers_meta.get("l1_bot_name")
                or getattr(getattr(spec, "bot", None), "name", None)
                or tag
            )[:40],
            success=True,
            feature_count=len(_feats),
        )
        _nav_d = _nav.to_dict()
        try:
            from .spec_core.language_understanding.evaluation_layer import (
                apply_ab_to_narrative,
                assign_ab_variant,
                record_ab_exposure,
            )
            if user_id:
                _nav_d = apply_ab_to_narrative(_nav_d, int(user_id))
                _ab = assign_ab_variant(int(user_id))
                layers_meta["ab_variant"] = _ab.variant
                record_ab_exposure(int(user_id), _ab.variant, surface="narrative")
        except Exception:
            pass
        layers_meta["l4_narrative"] = _nav_d
    except Exception:
        pass

    meta = {
        "engine": "spec_core",
        "preset": tag,
        "elapsed_ms": round(elapsed * 1000, 1),
        "zero_ai": True,
        "ai_disabled": True,
        "quality": "market_pack_v2",
        "layers": layers_meta,
        "user_id": int(user_id) if user_id else None,
        "narrative": layers_meta.get("l4_narrative"),
    }
    # Stage-5: record outcome for analytics / A/B
    try:
        from .spec_core.language_understanding.evaluation_layer import record_generation_outcome
        from .spec_core.language_understanding.memory_engine import get_memory_engine as _gme5
        record_generation_outcome(
            int(user_id) if user_id else 0,
            success=bool(getattr(result, "ok", False)),
            intent=str(layers_meta.get("l2_intent") or ""),
            strict=bool(layers_meta.get("l1_strict")),
            feature_count=len(list(layers_meta.get("l1_features") or layers_meta.get("l2_feature_plan") or [])),
            preset=str(tag),
            ab_variant=str(layers_meta.get("ab_variant") or ""),
            elapsed_ms=meta.get("elapsed_ms"),
            memory=memory_engine or _gme5(),
        )
    except Exception:
        pass

    # L4: persist successful build
    if memory_engine is not None and user_id and result.ok:
        try:
            feats = list(layers_meta.get("l2_feature_plan") or [])
            # include what actually got selected if available
            try:
                feats = list(dict.fromkeys(
                    feats + [getattr(f, "feature", None) or getattr(f, "id", None)
                             for f in (spec.features or [])]
                ))
                feats = [str(x) for x in feats if x][:40]
            except Exception:
                pass
            memory_engine.register_bot(
                int(user_id),
                name=getattr(getattr(spec, "bot", None), "name", None) or tag,
                intent=str(layers_meta.get("l2_intent") or tag),
                features=feats,
                request_text=request or "",
                preset=tag,
                output_path=str(project_dir),
                success=True,
            )
            primary = layers_meta.get("l2_intent")
            if primary and feats:
                memory_engine.record_patterns(intent=str(primary), features=feats)
            try:
                from .spec_core.language_understanding.continuous_learning import learn_from_success
                learn_from_success(
                    int(user_id),
                    intent=str(primary or "general"),
                    features=list(feats or []),
                    purpose=str(getattr(getattr(lu, "entities", None), "bot_purpose", None) or primary or ""),
                    bot_name=str(getattr(getattr(lu, "entities", None), "bot_name", None) or ""),
                    request_text=request or "",
                    memory=memory_engine,
                )
            except Exception:
                pass
        except Exception:
            pass

    # ── Anti-hallucination gate (mandatory before any "ready" claim) ──
    ah_report = None
    ah_dict = {}
    try:
        from .services.anti_hallucination import run_anti_hallucination_gate
        claimed = []
        try:
            claimed = [getattr(f, "feature", None) or getattr(f, "id", None) for f in (spec.features or [])]
            claimed = [str(c) for c in claimed if c]
        except Exception:
            claimed = []
        ah_report = run_anti_hallucination_gate(
            project_dir,
            claimed_features=claimed,
            user_request=request or "",
        )
        ah_dict = ah_report.to_dict()
        meta["anti_hallucination"] = ah_dict
        meta["verified_commands"] = list(ah_report.verified_commands)
        meta["stub_handlers"] = list(ah_report.stub_handlers)
        meta["ready_for_token"] = bool(ah_report.ready_for_token)
    except Exception as exc:
        meta["anti_hallucination_error"] = str(exc)[:300]
        meta["ready_for_token"] = False
        # Fail closed: never mark project ready if the gate itself crashed
        if result.ok:
            meta["blocked_by"] = "anti_hallucination_exception"
            return GenerationResult(
                success=False,
                project_path=str(project_dir),
                stages=[
                    StageResult.ok("spec_preset", outputs={"preset": tag}),
                    StageResult.ok("spec_codegen", outputs={"files": result.files}),
                    StageResult.failed(
                        "anti_hallucination",
                        errors=[f"gate_exception:{type(exc).__name__}"],
                    ),
                ],
                validation_reports=[],
                errors=[f"anti_hallucination_gate_failed:{type(exc).__name__}: {str(exc)[:200]}"],
                metadata=meta,
            )

    if result.ok and ah_report is not None and not ah_report.ok:
        # Structural generation succeeded but verification failed → not success for user
        meta.update(
            {
                "files_created": result.files,
                "services": result.plan_services,
                "ready_for_token": False,
                "blocked_by": "anti_hallucination",
            }
        )
        errs = list(result.errors) + [f.message_ar for f in ah_report.errors]
        return GenerationResult(
            success=False,
            project_path=str(project_dir),
            stages=[
                StageResult.ok("spec_preset", outputs={"preset": tag}),
                StageResult.ok("spec_codegen", outputs={"files": result.files}),
                StageResult.failed(
                    "anti_hallucination",
                    errors=[f.code for f in ah_report.errors],
                ),
            ],
            validation_reports=[],
            errors=errs,
            metadata=meta,
        )

    if result.ok:
        meta.update(
            {
                "files_created": result.files,
                "services": result.plan_services,
                # ready_for_token already set from gate (or False on gate error)
                "ready_for_token": bool(meta.get("ready_for_token", False)),
            }
        )
        stages = [
            StageResult.ok("spec_preset", outputs={"preset": tag}),
            StageResult.ok("spec_codegen", outputs={"files": result.files}),
        ]
        if ah_report is not None:
            stages.append(
                StageResult.ok(
                    "anti_hallucination",
                    outputs={
                        "verified_commands": ah_report.verified_commands,
                        "ready_for_token": ah_report.ready_for_token,
                    },
                )
            )
        return GenerationResult(
            success=True,
            project_path=str(project_dir),
            stages=stages,
            validation_reports=[],
            errors=[],
            metadata=meta,
        )
    return GenerationResult(
        success=False,
        project_path=str(project_dir),
        stages=[StageResult.failed("spec_codegen", errors=list(result.errors))],
        validation_reports=[],
        errors=list(result.errors),
        metadata=meta,
    )


def generate_bot(request: str, work_dir=None, user_id: int = 0, preferred_keys=None):
    """Generate a runnable Telegram bot using zero-AI engines only.

    Runs L1→L6 intelligence (per user_id when provided) then deterministic codegen.
    preferred_keys: optional capability keys from Capability Detection (Phase 2).
    """
    import time
    from .core.result import GenerationResult

    t0 = time.perf_counter()
    original_request = (request or "").strip()
    if not original_request:
        return GenerationResult(
            success=False,
            project_path=None,
            stages=[],
            validation_reports=[],
            errors=["Empty request"],
            metadata={"ai_disabled": True},
        )

    result = _generate_bot_zero_ai(
        original_request,
        work_dir,
        t0,
        user_id=int(user_id or 0),
        force=True,
        preferred_keys=preferred_keys,
    )
    if result is not None:
        return result
    return GenerationResult(
        success=False,
        project_path=None,
        stages=[],
        validation_reports=[],
        errors=["zero_ai_generation_failed"],
        metadata={"engine": "spec_core", "ai_disabled": True},
    )



__all__ = [
    "bootstrap",
    "build_configuration",
    "generate_bot",
    "PipelineOrchestrator",
    "EngineRegistry",
]


def bootstrap(*args, **kwargs):
    from .core import bootstrap as _bootstrap
    return _bootstrap(*args, **kwargs)


def build_configuration(*args, **kwargs):
    from .core import build_configuration as _bc
    return _bc(*args, **kwargs)


def PipelineOrchestrator(*args, **kwargs):
    from .pipeline import PipelineOrchestrator as _PO
    return _PO(*args, **kwargs)


def EngineRegistry(*args, **kwargs):
    from .registry import EngineRegistry as _ER
    return _ER(*args, **kwargs)
