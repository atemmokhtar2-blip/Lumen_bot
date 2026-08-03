"""
ScaffoldBuilder — Specification 030

Initializes project identity, creates folder/file scaffold entries,
manifest, registry and build logs — without writing business logic.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import List, Tuple

from .report_data import (
    ProjectIdentity, ScaffoldEntry, ProjectManifest, ProjectRegistry,
    BuildLogEntry, BuildConflict,
    ENTRY_FOLDER, ENTRY_FILE,
    CONFLICT_DUPLICATE_PATH, CONFLICT_EMPTY_PROJECT, CONFLICT_MISSING_PATH,
    SEVERITY_CRITICAL, SEVERITY_HIGH, SEVERITY_MEDIUM,
)
from .data_readers import GenericData

_log = logging.getLogger("engine.project_builder.scaffold_builder")


class ScaffoldBuilder:
    def build(
        self,
        plan_data: GenericData,
        structure_data: GenericData,
        mod_data: GenericData,
        comp_data: GenericData,
        strategy_data: GenericData,
        session_data: GenericData,
    ) -> Tuple[
        ProjectIdentity,
        List[ScaffoldEntry],
        ProjectManifest,
        ProjectRegistry,
        List[BuildLogEntry],
        List[BuildConflict],
    ]:
        now = datetime.now(timezone.utc).isoformat()
        conflicts: List[BuildConflict] = []
        logs: List[BuildLogEntry] = []
        entries: List[ScaffoldEntry] = []

        # ---- Identity ----
        project_name = "telegram_bot"
        project_id = str(uuid.uuid4())
        if session_data.available and session_data.raw:
            project_id = session_data.raw.get("project_id") or project_id
            project_name = session_data.raw.get("project_id") or project_name
        if structure_data.available and structure_data.raw:
            project_name = structure_data.raw.get("project_name") or project_name

        identity = ProjectIdentity(
            project_id=project_id,
            project_name=project_name,
            version="0.1.0",
            created_at=now,
            description="Scaffolded by Intelligent Project Builder Engine (Spec 030)",
        )
        logs.append(BuildLogEntry(
            entry_id=str(uuid.uuid4()), timestamp=now,
            action="project_initialized", path=project_name,
            result="ok", reason="Identity and metadata created",
        ))

        # ---- Collect paths from code plan units + structure + strategy ----
        paths: List[Tuple[str, str, str]] = []  # (path, type, purpose)

        def _add(path: str, etype: str, purpose: str, ref: str = "") -> None:
            if not path:
                return
            path = path.replace("\\", "/").strip("/")
            if not path:
                return
            paths.append((path, etype, purpose))

        # From code generation plan units
        units = plan_data.items if plan_data.available else []
        if not units and plan_data.raw:
            units = plan_data.raw.get("units") or []
        for u in units:
            if not isinstance(u, dict):
                continue
            p = u.get("path") or ""
            kind = (u.get("kind") or "file").lower()
            etype = ENTRY_FOLDER if kind == "folder" or p.endswith("/") else ENTRY_FILE
            _add(p, etype, u.get("purpose") or u.get("name") or "", u.get("unit_id") or "")

        # From structure blueprint
        if structure_data.available:
            for f in structure_data.items:
                if isinstance(f, dict):
                    _add(f.get("path") or f.get("name") or "", ENTRY_FILE,
                         f.get("purpose") or "", f.get("file_id") or "")
            folders = (structure_data.raw or {}).get("folders") or []
            for fo in folders:
                if isinstance(fo, dict):
                    _add(fo.get("path") or fo.get("name") or "", ENTRY_FOLDER,
                         fo.get("purpose") or "", "")
                elif isinstance(fo, str):
                    _add(fo, ENTRY_FOLDER, "", "")

        # From strategy items
        if strategy_data.available:
            for it in strategy_data.items:
                if isinstance(it, dict):
                    p = it.get("path") or ""
                    itype = (it.get("item_type") or "file").lower()
                    etype = ENTRY_FOLDER if itype == "folder" or p.endswith("/") else ENTRY_FILE
                    _add(p, etype, it.get("description") or it.get("name") or "",
                         it.get("item_id") or "")

        # Canonical fallback scaffold
        if not paths:
            for p, etype in [
                ("telegram_bot", ENTRY_FOLDER),
                ("telegram_bot/__init__.py", ENTRY_FILE),
                ("telegram_bot/core", ENTRY_FOLDER),
                ("telegram_bot/core/__init__.py", ENTRY_FILE),
                ("telegram_bot/core/models.py", ENTRY_FILE),
                ("telegram_bot/handlers", ENTRY_FOLDER),
                ("telegram_bot/handlers/__init__.py", ENTRY_FILE),
                ("telegram_bot/services", ENTRY_FOLDER),
                ("telegram_bot/services/__init__.py", ENTRY_FILE),
                ("telegram_bot/integrations", ENTRY_FOLDER),
                ("telegram_bot/integrations/telegram.py", ENTRY_FILE),
                ("telegram_bot/configs", ENTRY_FOLDER),
                ("telegram_bot/configs/settings.py", ENTRY_FILE),
                ("tests", ENTRY_FOLDER),
                ("tests/__init__.py", ENTRY_FILE),
                ("requirements.txt", ENTRY_FILE),
                (".gitignore", ENTRY_FILE),
                (".env.example", ENTRY_FILE),
                ("README.md", ENTRY_FILE),
                ("main.py", ENTRY_FILE),
            ]:
                _add(p, etype, f"Canonical scaffold: {p}", "")

        # Ensure parent folders exist for every file
        all_paths = set()
        expanded: List[Tuple[str, str, str]] = []
        for path, etype, purpose in paths:
            if etype == ENTRY_FILE:
                parts = path.split("/")
                for i in range(1, len(parts)):
                    parent = "/".join(parts[:i])
                    if parent and parent not in all_paths:
                        expanded.append((parent, ENTRY_FOLDER, f"Parent of {path}"))
                        all_paths.add(parent)
            if path not in all_paths:
                expanded.append((path, etype, purpose))
                all_paths.add(path)

        # Dedupe preserving order
        seen = set()
        unique: List[Tuple[str, str, str]] = []
        for path, etype, purpose in expanded:
            key = path.lower()
            if key in seen:
                conflicts.append(BuildConflict(
                    conflict_id=f"dup_{path.replace('/', '_')}",
                    conflict_type=CONFLICT_DUPLICATE_PATH,
                    severity=SEVERITY_MEDIUM,
                    message=f"Duplicate path '{path}' collapsed.",
                    affected_paths=[path],
                    resolution_hint="Path was deduplicated; only one entry kept.",
                ))
                continue
            seen.add(key)
            unique.append((path, etype, purpose))

        # Build entries + logs
        for idx, (path, etype, purpose) in enumerate(unique):
            eid = f"entry.{idx + 1}"
            entries.append(ScaffoldEntry(
                entry_id=eid,
                path=path,
                entry_type=etype,
                purpose=purpose,
                blueprint_ref="",
                created=True,
            ))
            logs.append(BuildLogEntry(
                entry_id=str(uuid.uuid4()), timestamp=now,
                action=f"create_{etype}", path=path,
                result="ok", reason=purpose or "scaffold",
            ))

        if not entries:
            conflicts.append(BuildConflict(
                conflict_id="empty_project",
                conflict_type=CONFLICT_EMPTY_PROJECT,
                severity=SEVERITY_CRITICAL,
                message="No folders or files were scaffolded.",
                affected_paths=[],
                resolution_hint="Ensure code generation plan or structure blueprint has paths.",
            ))

        # ---- Manifest ----
        folders = [e.path for e in entries if e.entry_type == ENTRY_FOLDER]
        files = [e.path for e in entries if e.entry_type == ENTRY_FILE]
        rels = []
        for e in entries:
            if e.entry_type == ENTRY_FILE and "/" in e.path:
                parent = "/".join(e.path.split("/")[:-1])
                if parent:
                    rels.append({"from": e.path, "to": parent, "type": "contained_in"})

        deps = []
        if plan_data.raw:
            ctx = plan_data.raw.get("context") or {}
            deps = list(ctx.get("dependencies") or [])

        manifest = ProjectManifest(
            folders=folders, files=files, relationships=rels, dependencies=deps,
        )

        # ---- Registry ----
        modules = []
        if mod_data.available:
            for m in mod_data.items:
                if isinstance(m, dict):
                    modules.append(m.get("module_id") or m.get("name") or "")
        components = []
        if comp_data.available:
            for c in comp_data.items:
                if isinstance(c, dict):
                    components.append(c.get("component_id") or c.get("name") or "")
        interfaces = []
        if plan_data.raw:
            ctx = plan_data.raw.get("context") or {}
            interfaces = list(ctx.get("interfaces") or [])

        registry = ProjectRegistry(
            modules=[m for m in modules if m],
            components=[c for c in components if c],
            interfaces=[i for i in interfaces if i],
            configurations=[f for f in files if "config" in f.lower() or "settings" in f.lower()],
            resources=[f for f in files if f.endswith((".env.example", ".gitignore", "requirements.txt"))],
            services=[c for c in components if "service" in c.lower()],
        )

        logs.append(BuildLogEntry(
            entry_id=str(uuid.uuid4()), timestamp=now,
            action="manifest_generated", path="",
            result="ok", reason=f"{len(folders)} folders, {len(files)} files",
        ))
        logs.append(BuildLogEntry(
            entry_id=str(uuid.uuid4()), timestamp=now,
            action="registry_built", path="",
            result="ok", reason=f"modules={len(registry.modules)} components={len(registry.components)}",
        ))

        _log.info(
            "ScaffoldBuilder: folders=%d files=%d conflicts=%d",
            len(folders), len(files), len(conflicts),
        )
        return identity, entries, manifest, registry, logs, conflicts


__all__ = ["ScaffoldBuilder"]
