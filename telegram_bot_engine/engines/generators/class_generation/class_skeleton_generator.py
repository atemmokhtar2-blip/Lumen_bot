"""
ClassSkeletonGenerator — Specification 031

Discovers classes from components and emits skeletons only
(declaration, properties, method signatures, docs — NO bodies).
"""

from __future__ import annotations

import logging
import re
from typing import Dict, List, Tuple

from .report_data import (
    ClassSkeleton, MethodSignature, PropertySpec, ClassDocSkeleton,
    ClassConflict,
    CLASS_CONTROLLER, CLASS_SERVICE, CLASS_MANAGER, CLASS_REPOSITORY,
    CLASS_ADAPTER, CLASS_FACTORY, CLASS_BUILDER, CLASS_VALIDATOR,
    CLASS_STRATEGY, CLASS_PROVIDER, CLASS_MODEL, CLASS_ENTITY,
    CLASS_UTILITY, CLASS_OTHER,
    CONFLICT_DUPLICATE_NAME, CONFLICT_NAMING, CONFLICT_CIRCULAR_REF,
    SEVERITY_CRITICAL, SEVERITY_HIGH, SEVERITY_MEDIUM,
)
from .data_readers import GenericData

_log = logging.getLogger("engine.class_generation.class_skeleton_generator")

_KIND_MAP = {
    "controller": CLASS_CONTROLLER,
    "service": CLASS_SERVICE,
    "manager": CLASS_MANAGER,
    "repository": CLASS_REPOSITORY,
    "adapter": CLASS_ADAPTER,
    "factory": CLASS_FACTORY,
    "builder": CLASS_BUILDER,
    "validator": CLASS_VALIDATOR,
    "strategy": CLASS_STRATEGY,
    "provider": CLASS_PROVIDER,
    "entity": CLASS_ENTITY,
    "model": CLASS_MODEL,
    "helper": CLASS_UTILITY,
    "utility": CLASS_UTILITY,
}


def _pascal(name: str) -> str:
    parts = re.split(r"[^a-zA-Z0-9]+", name)
    return "".join(p[:1].upper() + p[1:] for p in parts if p)


def _render_skeleton(skel: ClassSkeleton) -> str:
    """Render Python class skeleton source — methods raise NotImplementedError only."""
    lines: List[str] = []
    doc = skel.docstring
    lines.append(f'"""{doc.description or skel.name}')
    if doc.purpose:
        lines.append("")
        lines.append(f"Purpose: {doc.purpose}")
    if doc.responsibilities:
        lines.append("")
        lines.append("Responsibilities:")
        for r in doc.responsibilities:
            lines.append(f"  - {r}")
    lines.append('"""')
    lines.append("")

    bases = list(skel.bases) + list(skel.interfaces)
    base_str = f"({', '.join(bases)})" if bases else ""
    lines.append(f"class {skel.name}{base_str}:")
    lines.append(f'    """{doc.description or skel.name} skeleton."""')
    lines.append("")

    # Injected deps as annotated attributes
    injected = [p for p in skel.properties if p.injected]
    plain = [p for p in skel.properties if not p.injected]

    if injected:
        params = ", ".join(f"{p.name}: {p.type_hint}" for p in injected)
        lines.append(f"    def __init__(self, {params}) -> None:")
        for p in injected:
            lines.append(f"        self._{p.name} = {p.name}")
        lines.append("")
    else:
        lines.append("    def __init__(self) -> None:")
        lines.append("        pass")
        lines.append("")

    for p in plain:
        default = f" = {p.default}" if p.default else ""
        lines.append(f"    {p.name}: {p.type_hint}{default}")
    if plain:
        lines.append("")

    for m in skel.methods:
        async_kw = "async " if m.is_async else ""
        params = ", ".join(["self"] + m.params)
        lines.append(f"    {async_kw}def {m.name}({params}) -> {m.return_type}:")
        if m.docstring:
            lines.append(f'        """{m.docstring}"""')
        lines.append("        raise NotImplementedError  # skeleton only — no business logic")
        lines.append("")

    if not skel.methods and not injected and not plain:
        lines.append("    pass")
        lines.append("")

    return "\n".join(lines)


class ClassSkeletonGenerator:
    def generate(
        self,
        comp_data: GenericData,
        iface_data: GenericData,
        project_data: GenericData,
        plan_data: GenericData,
    ) -> Tuple[List[ClassSkeleton], List[ClassConflict]]:
        classes: List[ClassSkeleton] = []
        conflicts: List[ClassConflict] = []

        components = comp_data.items if comp_data.available else []
        if not components and comp_data.raw:
            components = comp_data.raw.get("components") or []

        iface_by_id: Dict[str, str] = {}
        if iface_data.available:
            for i in iface_data.items:
                if isinstance(i, dict):
                    iid = i.get("interface_id") or ""
                    iname = i.get("name") or iid
                    if iid:
                        iface_by_id[iid] = iname

        # ---- From components ----
        for c in components:
            if not isinstance(c, dict):
                continue
            cid = c.get("component_id") or ""
            cname = c.get("name") or cid
            kind_raw = (c.get("kind") or "other").lower()
            kind = _KIND_MAP.get(kind_raw, CLASS_OTHER)
            mid = c.get("module_id") or ""
            class_name = _pascal(cname.replace(" ", ""))
            if not class_name.endswith(("Service", "Controller", "Repository", "Adapter",
                                        "Factory", "Manager", "Validator", "Provider",
                                        "Strategy", "Builder", "Entity", "Model")):
                # ensure kind suffix for clarity
                suffix = {
                    CLASS_SERVICE: "Service", CLASS_CONTROLLER: "Controller",
                    CLASS_REPOSITORY: "Repository", CLASS_ADAPTER: "Adapter",
                    CLASS_FACTORY: "Factory", CLASS_MANAGER: "Manager",
                    CLASS_VALIDATOR: "Validator", CLASS_PROVIDER: "Provider",
                    CLASS_STRATEGY: "Strategy", CLASS_BUILDER: "Builder",
                    CLASS_ENTITY: "Entity", CLASS_MODEL: "Model",
                }.get(kind, "")
                if suffix and not class_name.endswith(suffix):
                    class_name = class_name + suffix

            package = mid.replace(".", "/") if mid else "telegram_bot"
            module_path = f"{package}/{class_name.lower()}.py" if package else f"{class_name.lower()}.py"

            # Interfaces
            interfaces = []
            for iface in c.get("interfaces") or []:
                if isinstance(iface, dict):
                    interfaces.append(iface.get("name") or "")
                elif isinstance(iface, str):
                    interfaces.append(iface)
            interfaces = [i for i in interfaces if i]

            # Methods from interface methods or defaults by kind
            methods: List[MethodSignature] = []
            for iface in c.get("interfaces") or []:
                if isinstance(iface, dict):
                    for m in iface.get("methods") or []:
                        if isinstance(m, str):
                            methods.append(MethodSignature(name=m, docstring=f"{m} — not implemented"))
                        elif isinstance(m, dict):
                            methods.append(MethodSignature(
                                name=m.get("name") or "method",
                                params=m.get("inputs") or [],
                                return_type=(m.get("outputs") or ["None"])[0] if m.get("outputs") else "None",
                                docstring=m.get("description") or "",
                            ))
            if not methods:
                methods = self._default_methods(kind)

            # DI properties from depends_on
            props: List[PropertySpec] = []
            deps = list(c.get("depends_on") or [])
            for dep in deps:
                dep_name = dep.split(".")[-1] if dep else "dep"
                props.append(PropertySpec(
                    name=dep_name.replace("-", "_"),
                    type_hint=_pascal(dep_name),
                    injected=True,
                ))

            doc = ClassDocSkeleton(
                description=c.get("purpose") or f"{class_name} component",
                purpose=c.get("purpose") or "",
                responsibilities=[c.get("responsibility") or ""] if c.get("responsibility") else [],
                dependencies_note=", ".join(deps) if deps else "none",
                notes="Skeleton only — no business logic (Spec 031)",
            )

            skel = ClassSkeleton(
                class_id=f"class.{cid}" if cid else f"class.{class_name}",
                name=class_name,
                kind=kind,
                module_path=module_path,
                package=package,
                bases=[],
                interfaces=interfaces,
                properties=props,
                methods=methods,
                dependencies=deps,
                component_ref=cid,
                docstring=doc,
            )
            skel.source_code = _render_skeleton(skel)
            classes.append(skel)

        # ---- Fallback canonical classes if none discovered ----
        if not classes:
            defaults = [
                ("OrderService", CLASS_SERVICE, "telegram_bot/services/order_service.py",
                 [MethodSignature("execute", ["command"], "Result", True, "Execute use-case")]),
                ("OrderController", CLASS_CONTROLLER, "telegram_bot/handlers/order_controller.py",
                 [MethodSignature("handle", ["update"], "None", True, "Handle Telegram update")]),
                ("OrderRepository", CLASS_REPOSITORY, "telegram_bot/database/order_repository.py",
                 [MethodSignature("save", ["entity"], "Entity"),
                  MethodSignature("get", ["id"], "Optional[Entity]")]),
                ("TelegramAdapter", CLASS_ADAPTER, "telegram_bot/integrations/telegram_adapter.py",
                 [MethodSignature("send", ["payload"], "Response", True),
                  MethodSignature("receive", [], "Update", True)]),
                ("OrderEntity", CLASS_ENTITY, "telegram_bot/core/models/order.py",
                 [MethodSignature("validate", [], "bool")]),
                ("Settings", CLASS_OTHER, "telegram_bot/configs/settings.py",
                 [MethodSignature("load", [], "Settings")]),
            ]
            for name, kind, path, methods in defaults:
                skel = ClassSkeleton(
                    class_id=f"class.{name}",
                    name=name,
                    kind=kind,
                    module_path=path,
                    package="/".join(path.split("/")[:-1]),
                    methods=methods,
                    docstring=ClassDocSkeleton(
                        description=f"{name} skeleton",
                        purpose=f"Provide {kind} structure",
                        notes="Skeleton only — no business logic",
                    ),
                )
                skel.source_code = _render_skeleton(skel)
                classes.append(skel)

        # ---- Validation: duplicates, naming, circulars ----
        seen_names: Dict[str, str] = {}
        for c in classes:
            key = c.name.lower()
            if key in seen_names:
                conflicts.append(ClassConflict(
                    conflict_id=f"dup_{c.class_id}",
                    conflict_type=CONFLICT_DUPLICATE_NAME,
                    severity=SEVERITY_CRITICAL,
                    message=f"Duplicate class name '{c.name}'.",
                    affected_ids=[c.class_id, seen_names[key]],
                    resolution_hint="Rename one of the classes.",
                ))
            else:
                seen_names[key] = c.class_id

            if not re.match(r"^[A-Z][a-zA-Z0-9]*$", c.name):
                conflicts.append(ClassConflict(
                    conflict_id=f"naming_{c.class_id}",
                    conflict_type=CONFLICT_NAMING,
                    severity=SEVERITY_HIGH,
                    message=f"Class '{c.name}' does not follow PascalCase.",
                    affected_ids=[c.class_id],
                    resolution_hint="Rename to PascalCase.",
                ))

        # Circular dependency among class deps
        id_set = {c.class_id for c in classes}
        name_to_id = {c.name: c.class_id for c in classes}
        graph: Dict[str, List[str]] = {}
        for c in classes:
            targets = []
            for d in c.dependencies:
                # map dep string to class_id if possible
                if d in id_set:
                    targets.append(d)
                elif d in name_to_id:
                    targets.append(name_to_id[d])
            graph[c.class_id] = targets

        for cycle in self._cycles(graph):
            conflicts.append(ClassConflict(
                conflict_id=f"cycle_{'_'.join(cycle[:2])}",
                conflict_type=CONFLICT_CIRCULAR_REF,
                severity=SEVERITY_CRITICAL,
                message=f"Circular class dependency: {' → '.join(cycle + [cycle[0]])}",
                affected_ids=list(cycle),
                resolution_hint="Break cycle with an interface.",
            ))

        _log.info("ClassSkeletonGenerator: %d classes, %d conflicts", len(classes), len(conflicts))
        return classes, conflicts

    def _default_methods(self, kind: str) -> List[MethodSignature]:
        if kind == CLASS_REPOSITORY:
            return [
                MethodSignature("save", ["entity: Any"], "Any", True, "Persist entity"),
                MethodSignature("get", ["id: str"], "Optional[Any]", True, "Load by id"),
                MethodSignature("delete", ["id: str"], "bool", True, "Delete by id"),
                MethodSignature("list", ["filter: Any = None"], "List[Any]", True, "List entities"),
            ]
        if kind == CLASS_CONTROLLER:
            return [MethodSignature("handle", ["update: Any"], "None", True, "Handle update")]
        if kind == CLASS_ADAPTER:
            return [
                MethodSignature("send", ["payload: Any"], "Any", True, "Send outbound"),
                MethodSignature("receive", [], "Any", True, "Receive inbound"),
            ]
        if kind == CLASS_VALIDATOR:
            return [MethodSignature("validate", ["data: Any"], "bool", False, "Validate input")]
        if kind == CLASS_FACTORY:
            return [MethodSignature("create", ["**kwargs: Any"], "Any", False, "Create instance")]
        if kind == CLASS_SERVICE:
            return [MethodSignature("execute", ["command: Any"], "Any", True, "Execute use-case")]
        return [MethodSignature("run", [], "None", False, "Entry point")]

    def _cycles(self, graph: Dict[str, List[str]]) -> List[List[str]]:
        cycles: List[List[str]] = []
        visited, stack, path = set(), set(), []

        def dfs(n: str) -> None:
            if n in stack:
                try:
                    cycles.append(path[path.index(n):])
                except ValueError:
                    cycles.append([n])
                return
            if n in visited:
                return
            visited.add(n)
            stack.add(n)
            path.append(n)
            for nb in graph.get(n, []):
                dfs(nb)
            path.pop()
            stack.discard(n)

        for node in list(graph):
            if node not in visited:
                dfs(node)
        return cycles


__all__ = ["ClassSkeletonGenerator"]
