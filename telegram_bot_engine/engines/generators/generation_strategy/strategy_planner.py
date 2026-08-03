"""
StrategyPlanner — Specification 026

Builds generation stages, ordered items, rules, rollback points and optimisations.
"""

from __future__ import annotations

import logging
from typing import List, Tuple

from .report_data import (
    GenerationStage, GenerationItem, GenerationRule, RollbackPoint, OptimizationStep,
    STAGE_FOUNDATION, STAGE_CORE, STAGE_FEATURES, STAGE_INTEGRATION,
    STAGE_CONFIGURATION, STAGE_TESTING, STAGE_DOCUMENTATION, ALL_STAGES,
    ITEM_FOLDER, ITEM_FILE, ITEM_MODULE, ITEM_COMPONENT, ITEM_CONFIG, ITEM_TEST, ITEM_DOC,
)
from .data_readers import GenericData

_log = logging.getLogger("engine.generation_strategy.strategy_planner")


class StrategyPlanner:
    def plan(
        self,
        struct_data: GenericData,
        mod_data: GenericData,
        comp_data: GenericData,
        res_data: GenericData,
    ) -> Tuple[
        List[GenerationStage],
        List[GenerationItem],
        List[str],
        List[GenerationRule],
        List[RollbackPoint],
        List[OptimizationStep],
    ]:
        stages: List[GenerationStage] = []
        items: List[GenerationItem] = []
        order = 0

        stage_defs = [
            (STAGE_FOUNDATION, "Foundation Generation",
             "Create root layout, package markers, requirements, gitignore"),
            (STAGE_CORE, "Core Generation",
             "Domain models, handlers, services, core modules"),
            (STAGE_FEATURES, "Feature Generation",
             "Business feature modules derived from requirements"),
            (STAGE_INTEGRATION, "Integration Generation",
             "Telegram adapter, external APIs, database layer"),
            (STAGE_CONFIGURATION, "Configuration Generation",
             "Settings, env templates, secrets placeholders"),
            (STAGE_TESTING, "Testing Preparation",
             "Unit/integration/e2e test scaffolds"),
            (STAGE_DOCUMENTATION, "Documentation Preparation",
             "README, architecture notes, usage docs"),
        ]

        for idx, (sid, name, desc) in enumerate(stage_defs):
            prereq = [stage_defs[idx - 1][0]] if idx > 0 else []
            stages.append(GenerationStage(
                stage_id=sid, name=name, order=(idx + 1) * 10,
                description=desc, prerequisites=prereq,
            ))

        # Foundation items
        foundation_items = [
            ("item.root", "Project root", ITEM_FOLDER, "telegram_bot/", "Root package directory"),
            ("item.init_root", "__init__.py", ITEM_FILE, "telegram_bot/__init__.py", "Package marker"),
            ("item.requirements", "requirements.txt", ITEM_FILE, "requirements.txt", "Dependency list"),
            ("item.gitignore", ".gitignore", ITEM_FILE, ".gitignore", "Git ignore rules"),
            ("item.main", "main.py", ITEM_FILE, "main.py", "Application entry point"),
        ]
        for iid, name, itype, path, desc in foundation_items:
            order += 1
            items.append(GenerationItem(
                item_id=iid, name=name, item_type=itype, stage=STAGE_FOUNDATION,
                order=order, path=path, description=desc,
            ))
            stages[0].item_ids.append(iid)

        # Core
        core_items = [
            ("item.core_pkg", "core/", ITEM_FOLDER, "telegram_bot/core/", "Core package"),
            ("item.models", "models/", ITEM_MODULE, "telegram_bot/core/models/", "Domain models"),
            ("item.handlers", "handlers/", ITEM_MODULE, "telegram_bot/handlers/", "Update handlers"),
            ("item.services", "services/", ITEM_MODULE, "telegram_bot/services/", "Application services"),
        ]
        for iid, name, itype, path, desc in core_items:
            order += 1
            items.append(GenerationItem(
                item_id=iid, name=name, item_type=itype, stage=STAGE_CORE,
                depends_on=["item.root"], order=order, path=path, description=desc,
            ))
            stages[1].item_ids.append(iid)

        # Features from modules if available
        if mod_data.available:
            for m in mod_data.items[:8]:
                if not isinstance(m, dict):
                    continue
                mid = m.get("module_id") or ""
                if "business" not in mid and m.get("category") != "business":
                    continue
                mname = m.get("name") or mid
                safe = "".join(c if c.isalnum() or c in "_-" else "_" for c in str(mname).lower())[:30]
                iid = f"item.feature.{safe}"
                order += 1
                items.append(GenerationItem(
                    item_id=iid, name=mname, item_type=ITEM_MODULE, stage=STAGE_FEATURES,
                    depends_on=["item.services"], order=order,
                    path=f"telegram_bot/modules/{safe}/",
                    description=f"Feature module: {mname}",
                ))
                stages[2].item_ids.append(iid)

        if not stages[2].item_ids:
            order += 1
            items.append(GenerationItem(
                item_id="item.feature.placeholder", name="features/",
                item_type=ITEM_FOLDER, stage=STAGE_FEATURES,
                depends_on=["item.services"], order=order,
                path="telegram_bot/modules/", description="Feature modules directory",
            ))
            stages[2].item_ids.append("item.feature.placeholder")

        # Integration
        integ_items = [
            ("item.db", "database/", ITEM_MODULE, "telegram_bot/database/", "Persistence layer"),
            ("item.telegram", "telegram adapter", ITEM_COMPONENT,
             "telegram_bot/integrations/telegram/", "Telegram Bot API adapter"),
        ]
        for iid, name, itype, path, desc in integ_items:
            order += 1
            items.append(GenerationItem(
                item_id=iid, name=name, item_type=itype, stage=STAGE_INTEGRATION,
                depends_on=["item.core_pkg"], order=order, path=path, description=desc,
            ))
            stages[3].item_ids.append(iid)

        # Configuration
        conf_items = [
            ("item.config_pkg", "configs/", ITEM_FOLDER, "telegram_bot/configs/", "Config package"),
            ("item.settings", "settings.py", ITEM_CONFIG, "telegram_bot/configs/settings.py", "Settings module"),
            ("item.env_example", ".env.example", ITEM_CONFIG, ".env.example", "Env template"),
        ]
        for iid, name, itype, path, desc in conf_items:
            order += 1
            items.append(GenerationItem(
                item_id=iid, name=name, item_type=itype, stage=STAGE_CONFIGURATION,
                depends_on=["item.root"], order=order, path=path, description=desc,
            ))
            stages[4].item_ids.append(iid)

        # Testing
        order += 1
        items.append(GenerationItem(
            item_id="item.tests", name="tests/", item_type=ITEM_TEST,
            stage=STAGE_TESTING, depends_on=["item.services", "item.handlers"],
            order=order, path="tests/", description="Test suite package",
        ))
        stages[5].item_ids.append("item.tests")

        # Documentation
        order += 1
        items.append(GenerationItem(
            item_id="item.readme", name="README.md", item_type=ITEM_DOC,
            stage=STAGE_DOCUMENTATION, depends_on=["item.root"],
            order=order, path="README.md", description="Project overview",
        ))
        stages[6].item_ids.append("item.readme")

        generation_order = [i.item_id for i in sorted(items, key=lambda x: x.order)]

        rules = [
            GenerationRule("rule.no_empty", "Never create empty files without a purpose"),
            GenerationRule("rule.no_unused", "Do not generate components that nothing references"),
            GenerationRule("rule.no_dup", "Never emit the same path twice"),
            GenerationRule("rule.respect_arch", "Honour module/component/interface blueprints"),
            GenerationRule("rule.deps_first", "Create a dependency only after its prerequisites exist"),
            GenerationRule("rule.tests_after_impl", "Test scaffolds only after the code they cover"),
        ]

        rollbacks = [
            RollbackPoint("rb.foundation", STAGE_FOUNDATION,
                          "After foundation: delete generated root package and restart",
                          ["remove project root", "clear partial requirements"]),
            RollbackPoint("rb.core", STAGE_CORE,
                          "After core: keep foundation, wipe core/handlers/services",
                          ["remove core package", "remove handlers", "remove services"]),
            RollbackPoint("rb.features", STAGE_FEATURES,
                          "After features: keep core, remove feature modules only",
                          ["remove modules/*"]),
        ]

        optimisations = [
            OptimizationStep("opt.batch_folders",
                             "Create all folders of a stage in one pass",
                             "Fewer filesystem syscalls"),
            OptimizationStep("opt.parallel_features",
                             "Feature modules with no mutual deps can be generated in parallel",
                             "Lower wall-clock time on multi-core hosts"),
            OptimizationStep("opt.skip_optional",
                             "Skip optional resources marked optional in the resource blueprint",
                             "Less work when the user did not request them"),
        ]

        _log.info("StrategyPlanner: %d stages, %d items", len(stages), len(items))
        return stages, items, generation_order, rules, rollbacks, optimisations


__all__ = ["StrategyPlanner"]
