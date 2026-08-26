# Extending Lumen (Developer Guide)

This guide is based on the live code after `spec_core` removal. Generation is **Cline-only**.

## Add a Skill (local)

```python
# my_skills.py
from lumen.engine.services.skills import Skill, register_skill

def hello(name: str = "world"):
    return {"ok": True, "message": f"hello {name}"}

def register(registry):
    registry.register(Skill(
        name="demo.hello",
        description="Example skill",
        input_schema={
            "type": "object",
            "properties": {"name": {"type": "string"}},
        },
        handler=hello,
        tags=["demo"],
    ))
```

```bash
export LUMEN_SKILLS_MODULES=my_skills
```

## Add MCP remote tools

```bash
export MCP_SERVER_URL=https://your-mcp-gateway.example/mcp
# optional:
export MCP_AUTH_TOKEN=...
```

On startup, `SkillRegistry` calls MCP `tools/list` and registers each tool as `mcp.<name>`.

## Browser / computer-use (Playwright)

```bash
pip install playwright
playwright install chromium
export BROWSER_USE_ENABLED=1
```

Agent tools: `browser_navigate`, `browser_content`, `browser_click`, `browser_fill`, `browser_screenshot`.

## GitHub integration

```bash
export GITHUB_TOKEN=ghp_...
```

```python
from lumen.engine.services.integrations.github import list_repo_issues, create_issue
list_repo_issues("owner", "repo")
```

## Events (Redis optional)

```python
from lumen.engine.services.events import emit, subscribe

def on_fail(ev):
    print("failed", ev)

subscribe("generation.failed", on_fail)
emit("generation.started", {"user_id": 1})
```

With `REDIS_URL`, events cross process boundaries via pub/sub channel `lumen:events`.

## Model router (Planner vs Worker)

| Env | Role |
|-----|------|
| `CLINE_MODEL_PLAN` | Architect / hard tasks |
| `CLINE_MODEL_BUILD` | Worker / build |
| `CLINE_MODEL_CRITIQUE` | Critic |
| `CLINE_LLM_PROVIDER` | Force provider |

`select_model_for_goal(task=..., goal=...)` uses difficulty bands.

## Evaluation (every multi-agent generate)

`orchestrate_generate` → `_phase_d_e_finalize` → `persist_state_evaluation`.

Records land via `evaluation.eval_store`.

## Swarm

```python
from lumen.engine.services.multi_agent.swarm import run_swarm
run_swarm(work_dir="...", tasks=[{"id": 1}, ...], worker_fn=my_worker)
```

`MULTI_AGENT_SWARM_SIZE` controls parallelism (1–32).
