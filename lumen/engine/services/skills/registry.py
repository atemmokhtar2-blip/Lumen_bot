"""Skill registry — developers register callables or MCP tools.

A Skill is a named capability with JSON schema + handler.
Handlers may be:
  - local Python callables
  - MCP remote tools (via MCPClient)
"""
from __future__ import annotations

import importlib
import logging
import os
import threading
from dataclasses import dataclass, field
from typing import Any, Callable

logger = logging.getLogger(__name__)


@dataclass
class Skill:
    name: str
    description: str
    input_schema: dict[str, Any] = field(default_factory=dict)
    handler: Callable[..., Any] | None = None
    mcp_server: str | None = None
    mcp_tool: str | None = None
    tags: list[str] = field(default_factory=list)
    enabled: bool = True
    source: str = "local"  # local | mcp | entrypoint

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "input_schema": dict(self.input_schema or {}),
            "tags": list(self.tags or []),
            "enabled": self.enabled,
            "source": self.source,
            "mcp_server": self.mcp_server,
            "mcp_tool": self.mcp_tool,
        }


class SkillRegistry:
    def __init__(self) -> None:
        self._skills: dict[str, Skill] = {}
        self._lock = threading.RLock()
        self._bootstrapped = False

    def register(self, skill: Skill) -> None:
        with self._lock:
            self._skills[skill.name] = skill

    def get(self, name: str) -> Skill | None:
        self.ensure_bootstrapped()
        return self._skills.get(name)

    def list(self, *, tag: str | None = None) -> list[Skill]:
        self.ensure_bootstrapped()
        out = list(self._skills.values())
        if tag:
            out = [s for s in out if tag in (s.tags or [])]
        return sorted(out, key=lambda s: s.name)

    def run(self, name: str, arguments: dict[str, Any] | None = None) -> dict[str, Any]:
        skill = self.get(name)
        if skill is None:
            return {"ok": False, "error": f"skill_not_found:{name}"}
        if not skill.enabled:
            return {"ok": False, "error": f"skill_disabled:{name}"}
        args = dict(arguments or {})
        try:
            if skill.source == "mcp" and skill.mcp_server and skill.mcp_tool:
                from .mcp_client import MCPClient
                client = MCPClient(skill.mcp_server)
                return client.call_tool(skill.mcp_tool, args)
            if skill.handler is None:
                return {"ok": False, "error": "skill_has_no_handler"}
            result = skill.handler(**args) if args else skill.handler()
            if isinstance(result, dict):
                return result if "ok" in result else {"ok": True, **result}
            return {"ok": True, "result": result}
        except TypeError:
            # handler may accept a single dict
            try:
                result = skill.handler(args)  # type: ignore[misc]
                if isinstance(result, dict):
                    return result if "ok" in result else {"ok": True, **result}
                return {"ok": True, "result": result}
            except Exception as exc:
                logger.exception("skill %s failed", name)
                return {"ok": False, "error": f"{type(exc).__name__}:{exc}"}
        except Exception as exc:
            logger.exception("skill %s failed", name)
            return {"ok": False, "error": f"{type(exc).__name__}:{exc}"}

    def ensure_bootstrapped(self) -> None:
        with self._lock:
            if self._bootstrapped:
                return
            self._bootstrapped = True
            self._register_builtins()
            self._load_entrypoints()
            self._sync_mcp_servers()

    def _register_builtins(self) -> None:
        def _echo(**kwargs: Any) -> dict[str, Any]:
            return {"ok": True, "echo": kwargs}

        self.register(
            Skill(
                name="echo",
                description="Debug skill — echoes arguments",
                input_schema={"type": "object"},
                handler=_echo,
                tags=["debug", "builtin"],
                source="local",
            )
        )
        # Browser skills (real Playwright)
        try:
            from lumen.engine.services.browser_use import (
                browse_url,
                click,
                fill,
                get_content,
                screenshot,
                close_session,
            )

            self.register(Skill(
                name="browser.navigate",
                description="Open URL with Playwright Chromium",
                input_schema={
                    "type": "object",
                    "properties": {
                        "url": {"type": "string"},
                        "session_id": {"type": "string"},
                    },
                    "required": ["url"],
                },
                handler=lambda **kw: browse_url(
                    str(kw.get("url") or ""),
                    session_id=kw.get("session_id"),
                    work_dir=str(kw.get("work_dir") or ""),
                ),
                tags=["browser", "computer_use"],
            ))
            self.register(Skill(
                name="browser.content",
                description="Read page text via Playwright",
                input_schema={
                    "type": "object",
                    "properties": {"session_id": {"type": "string"}},
                    "required": ["session_id"],
                },
                handler=lambda **kw: get_content(str(kw["session_id"])),
                tags=["browser", "computer_use"],
            ))
            self.register(Skill(
                name="browser.click",
                description="Click selector via Playwright",
                input_schema={
                    "type": "object",
                    "properties": {
                        "session_id": {"type": "string"},
                        "selector": {"type": "string"},
                    },
                    "required": ["session_id", "selector"],
                },
                handler=lambda **kw: click(str(kw["session_id"]), str(kw["selector"])),
                tags=["browser", "computer_use"],
            ))
            self.register(Skill(
                name="browser.fill",
                description="Fill input via Playwright",
                input_schema={
                    "type": "object",
                    "properties": {
                        "session_id": {"type": "string"},
                        "selector": {"type": "string"},
                        "value": {"type": "string"},
                    },
                    "required": ["session_id", "selector", "value"],
                },
                handler=lambda **kw: fill(
                    str(kw["session_id"]), str(kw["selector"]), str(kw.get("value") or "")
                ),
                tags=["browser", "computer_use"],
            ))
            self.register(Skill(
                name="browser.screenshot",
                description="Screenshot page via Playwright",
                input_schema={
                    "type": "object",
                    "properties": {
                        "session_id": {"type": "string"},
                        "path": {"type": "string"},
                    },
                    "required": ["session_id"],
                },
                handler=lambda **kw: screenshot(
                    str(kw["session_id"]), path=kw.get("path")
                ),
                tags=["browser", "computer_use"],
            ))
            self.register(Skill(
                name="browser.close",
                description="Close Playwright session",
                input_schema={
                    "type": "object",
                    "properties": {"session_id": {"type": "string"}},
                    "required": ["session_id"],
                },
                handler=lambda **kw: close_session(str(kw["session_id"])),
                tags=["browser", "computer_use"],
            ))
        except Exception:
            logger.exception("browser skills registration failed")

    def _load_entrypoints(self) -> None:
        """Load skills from LUMEN_SKILLS_MODULES=pkg.mod,pkg.mod2 exposing register(registry)."""
        raw = (os.getenv("LUMEN_SKILLS_MODULES") or "").strip()
        if not raw:
            return
        for mod_name in raw.split(","):
            mod_name = mod_name.strip()
            if not mod_name:
                continue
            try:
                mod = importlib.import_module(mod_name)
                fn = getattr(mod, "register", None)
                if callable(fn):
                    fn(self)
            except Exception:
                logger.exception("skill module load failed: %s", mod_name)

    def _sync_mcp_servers(self) -> None:
        # Prefer official MCP SDK stdio servers when MCP_SERVER_COMMAND is set
        try:
            from .mcp_official import list_tools_sync, mcp_sdk_available
            if mcp_sdk_available() and (os.getenv("MCP_SERVER_COMMAND") or "").strip():
                for tool in list_tools_sync():
                    name = str(tool.get("name") or "").strip()
                    if not name:
                        continue
                    self.register(
                        Skill(
                            name=f"mcp.{name}",
                            description=str(tool.get("description") or name),
                            input_schema=dict(tool.get("inputSchema") or {}),
                            tags=["mcp", "official_sdk"],
                            source="mcp",
                            mcp_server="stdio",
                            mcp_tool=name,
                        )
                    )
        except Exception:
            logger.exception("official MCP SDK sync failed")

        """Discover tools from MCP_SERVER_URLS=url1,url2 and register as skills."""
        raw = (
            os.getenv("MCP_SERVER_URLS")
            or os.getenv("MCP_SERVER_URL")
            or os.getenv("ACTIVEPIECES_MCP_URL")
            or ""
        ).strip()
        if not raw:
            return
        from .mcp_client import MCPClient

        for url in [u.strip() for u in raw.split(",") if u.strip()]:
            try:
                client = MCPClient(url)
                tools = client.list_tools()
                for tool in tools:
                    name = str(tool.get("name") or "").strip()
                    if not name:
                        continue
                    skill_name = f"mcp.{name}"
                    self.register(
                        Skill(
                            name=skill_name,
                            description=str(tool.get("description") or name),
                            input_schema=dict(tool.get("inputSchema") or tool.get("input_schema") or {}),
                            mcp_server=url,
                            mcp_tool=name,
                            tags=["mcp", "remote"],
                            source="mcp",
                        )
                    )
            except Exception:
                logger.exception("MCP sync failed for %s", url)


_REGISTRY: SkillRegistry | None = None
_REG_LOCK = threading.Lock()


def get_registry() -> SkillRegistry:
    global _REGISTRY
    with _REG_LOCK:
        if _REGISTRY is None:
            _REGISTRY = SkillRegistry()
        return _REGISTRY


def register_skill(skill: Skill) -> None:
    get_registry().register(skill)


def list_skills(*, tag: str | None = None) -> list[dict[str, Any]]:
    return [s.to_dict() for s in get_registry().list(tag=tag)]


def run_skill(name: str, arguments: dict[str, Any] | None = None) -> dict[str, Any]:
    return get_registry().run(name, arguments)


__all__ = [
    "Skill",
    "SkillRegistry",
    "get_registry",
    "list_skills",
    "register_skill",
    "run_skill",
]
