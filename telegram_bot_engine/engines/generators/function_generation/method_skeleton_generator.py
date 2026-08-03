"""
MethodSkeletonGenerator — Specification 032

Discovers and emits method/function signatures for every class.
No business logic, no method bodies.
"""

from __future__ import annotations

import logging
import re
from collections import defaultdict
from typing import Dict, List, Tuple

from .report_data import (
    MethodSkeleton, ParamSpec, MethodDocSkeleton, MethodConflict,
    VIS_PUBLIC, VIS_PRIVATE,
    CONFLICT_DUPLICATE_METHOD, CONFLICT_SIGNATURE_CLASH, CONFLICT_NAMING,
    SEVERITY_CRITICAL, SEVERITY_HIGH, SEVERITY_MEDIUM,
)
from .data_readers import GenericData

_log = logging.getLogger("engine.function_generation.method_skeleton_generator")


def _sig(m: MethodSkeleton) -> str:
    decorators = "".join(f"@{d}\n    " for d in m.decorators)
    async_kw = "async " if m.is_async else ""
    params = ["self"] if not m.is_staticmethod else []
    if m.is_classmethod and "cls" not in params:
        params = ["cls"]
    for p in m.params:
        part = f"{p.name}: {p.type_hint}"
        if p.default:
            part += f" = {p.default}"
        params.append(part)
    return f"{decorators}{async_kw}def {m.name}({', '.join(params)}) -> {m.return_type}:"


class MethodSkeletonGenerator:
    def generate(
        self,
        class_data: GenericData,
        iface_data: GenericData,
        comp_data: GenericData,
    ) -> Tuple[List[MethodSkeleton], Dict[str, List[str]], List[MethodConflict]]:
        methods: List[MethodSkeleton] = []
        registry: Dict[str, List[str]] = defaultdict(list)
        conflicts: List[MethodConflict] = []

        classes = class_data.items if class_data.available else []
        if not classes and class_data.raw:
            classes = class_data.raw.get("classes") or []

        for cls in classes:
            if not isinstance(cls, dict):
                continue
            class_id = cls.get("class_id") or ""
            class_name = cls.get("name") or class_id
            kind = (cls.get("kind") or "").lower()

            # Constructor from injected properties
            injected = [p for p in (cls.get("properties") or []) if isinstance(p, dict) and p.get("injected")]
            ctor_params = [
                ParamSpec(name=p.get("name") or "dep", type_hint=p.get("type_hint") or "Any",
                          description="Injected dependency")
                for p in injected
            ]
            ctor = MethodSkeleton(
                method_id=f"{class_id}.__init__",
                name="__init__",
                class_id=class_id,
                class_name=class_name,
                is_constructor=True,
                params=ctor_params,
                return_type="None",
                purpose="Constructor with dependency injection",
                docstring=MethodDocSkeleton(
                    description=f"Initialize {class_name}",
                    inputs=[p.name for p in ctor_params],
                    outputs=["None"],
                    notes="Skeleton only — no business logic",
                ),
            )
            ctor.source_signature = _sig(ctor)
            methods.append(ctor)
            registry[class_id].append(ctor.method_id)

            # Methods already declared on the class skeleton
            seen_names = {"__init__"}
            for m in cls.get("methods") or []:
                if not isinstance(m, dict):
                    continue
                mname = m.get("name") or "method"
                if mname in seen_names:
                    conflicts.append(MethodConflict(
                        conflict_id=f"dup_{class_id}_{mname}",
                        conflict_type=CONFLICT_DUPLICATE_METHOD,
                        severity=SEVERITY_CRITICAL,
                        message=f"Duplicate method '{mname}' on {class_name}.",
                        affected_ids=[class_id],
                        resolution_hint="Rename or remove the duplicate.",
                    ))
                    continue
                seen_names.add(mname)

                params_raw = m.get("params") or m.get("inputs") or []
                params: List[ParamSpec] = []
                for pr in params_raw:
                    if isinstance(pr, str):
                        # "name: Type" or just "name"
                        if ":" in pr:
                            n, t = pr.split(":", 1)
                            params.append(ParamSpec(name=n.strip(), type_hint=t.strip()))
                        else:
                            params.append(ParamSpec(name=pr.strip()))
                    elif isinstance(pr, dict):
                        params.append(ParamSpec(
                            name=pr.get("name") or "arg",
                            type_hint=pr.get("type_hint") or pr.get("type") or "Any",
                            default=pr.get("default") or "",
                            description=pr.get("description") or "",
                        ))

                ret = m.get("return_type") or "None"
                if isinstance(ret, list):
                    ret = ret[0] if ret else "None"

                is_async = bool(m.get("is_async"))
                # default async for service/controller/repository/adapter
                if not is_async and kind in ("service", "controller", "repository", "adapter"):
                    is_async = True

                exceptions = list(m.get("exceptions") or m.get("errors") or [])
                ms = MethodSkeleton(
                    method_id=f"{class_id}.{mname}",
                    name=mname,
                    class_id=class_id,
                    class_name=class_name,
                    is_async=is_async,
                    params=params,
                    return_type=str(ret),
                    exceptions=exceptions,
                    purpose=m.get("docstring") or m.get("description") or f"{mname} on {class_name}",
                    docstring=MethodDocSkeleton(
                        description=m.get("docstring") or m.get("description") or f"{mname}",
                        inputs=[p.name for p in params],
                        outputs=[str(ret)],
                        exceptions=exceptions,
                        notes="Skeleton only — no business logic (Spec 032)",
                    ),
                )
                ms.source_signature = _sig(ms)
                methods.append(ms)
                registry[class_id].append(ms.method_id)

            # Ensure kind-specific essential methods if missing
            for extra in self._ensure_essentials(kind, class_id, class_name, seen_names):
                methods.append(extra)
                registry[class_id].append(extra.method_id)
                seen_names.add(extra.name)

        # Fallback if no classes
        if not methods:
            for cname, mname, async_, params, ret in [
                ("OrderService", "execute", True, [ParamSpec("command", "Any")], "Any"),
                ("OrderController", "handle", True, [ParamSpec("update", "Any")], "None"),
                ("OrderRepository", "save", True, [ParamSpec("entity", "Any")], "Any"),
                ("OrderRepository", "get", True, [ParamSpec("id", "str")], "Optional[Any]"),
            ]:
                cid = f"class.{cname}"
                if mname == "execute" or mname == "handle" or mname == "save":
                    # also add init once per class
                    if f"{cid}.__init__" not in {m.method_id for m in methods}:
                        init = MethodSkeleton(
                            method_id=f"{cid}.__init__", name="__init__",
                            class_id=cid, class_name=cname, is_constructor=True,
                            return_type="None", purpose="Constructor",
                            docstring=MethodDocSkeleton(description=f"Init {cname}", notes="skeleton"),
                        )
                        init.source_signature = _sig(init)
                        methods.append(init)
                        registry[cid].append(init.method_id)
                ms = MethodSkeleton(
                    method_id=f"{cid}.{mname}", name=mname,
                    class_id=cid, class_name=cname, is_async=async_,
                    params=params, return_type=ret, purpose=f"{mname} skeleton",
                    docstring=MethodDocSkeleton(description=mname, notes="skeleton only"),
                )
                ms.source_signature = _sig(ms)
                methods.append(ms)
                registry[cid].append(ms.method_id)

        # Naming validation
        for m in methods:
            if m.name != "__init__" and not re.match(r"^[a-z_][a-z0-9_]*$", m.name):
                conflicts.append(MethodConflict(
                    conflict_id=f"naming_{m.method_id}",
                    conflict_type=CONFLICT_NAMING,
                    severity=SEVERITY_HIGH,
                    message=f"Method '{m.name}' is not snake_case.",
                    affected_ids=[m.method_id],
                    resolution_hint="Rename to snake_case.",
                ))

        # Signature clash: same name+param count on same class
        by_cls_sig: Dict[str, List[str]] = defaultdict(list)
        for m in methods:
            key = f"{m.class_id}::{m.name}::{len(m.params)}"
            by_cls_sig[key].append(m.method_id)
        for key, ids in by_cls_sig.items():
            if len(ids) > 1:
                conflicts.append(MethodConflict(
                    conflict_id=f"clash_{key}",
                    conflict_type=CONFLICT_SIGNATURE_CLASH,
                    severity=SEVERITY_CRITICAL,
                    message=f"Signature clash for {key}.",
                    affected_ids=ids,
                    resolution_hint="Differentiate parameter lists or names.",
                ))

        _log.info("MethodSkeletonGenerator: %d methods, %d conflicts", len(methods), len(conflicts))
        return methods, dict(registry), conflicts

    def _ensure_essentials(self, kind, class_id, class_name, seen) -> List[MethodSkeleton]:
        extras = []
        needed = {
            "repository": [("save", True, [ParamSpec("entity", "Any")], "Any"),
                           ("get", True, [ParamSpec("id", "str")], "Optional[Any]")],
            "service": [("execute", True, [ParamSpec("command", "Any")], "Any")],
            "controller": [("handle", True, [ParamSpec("update", "Any")], "None")],
            "adapter": [("send", True, [ParamSpec("payload", "Any")], "Any")],
            "validator": [("validate", False, [ParamSpec("data", "Any")], "bool")],
        }.get(kind, [])
        for name, async_, params, ret in needed:
            if name in seen:
                continue
            ms = MethodSkeleton(
                method_id=f"{class_id}.{name}", name=name,
                class_id=class_id, class_name=class_name, is_async=async_,
                params=params, return_type=ret,
                purpose=f"Essential {name} for {kind}",
                docstring=MethodDocSkeleton(
                    description=f"{name} for {class_name}",
                    notes="Skeleton only — no business logic",
                ),
            )
            ms.source_signature = _sig(ms)
            extras.append(ms)
        return extras


__all__ = ["MethodSkeletonGenerator"]
