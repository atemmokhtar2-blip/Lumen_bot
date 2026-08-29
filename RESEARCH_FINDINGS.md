# Research Findings — Strongest Real-World Solutions for Agent Reliability

## Sources Consulted
1. **Agent Reliability Engineering Design Guide** (hidekazu-konishi.com) — comprehensive guide on retries, loop detection, budgets
2. **LangGraph Fault Tolerance: Retries, Timeouts, and Error Handlers** (langchain.com official blog) — official LangGraph primitives
3. **"The Agent Wall-Clock Budget That Raced Your Tool's Own Timeout"** (tianpan.co) — deadline propagation deep dive
4. **YouTube: "Why Your Coding Agent Gets Stuck and How to Fix It"** (Parth Patil, Reid Hoffman's office) — death loops, context pollution
5. **YouTube: "Why Your AI Coding Agent Will Fail in Production"** (AIND Meetup, Qodo/Snyk/Tessl) — orchestration paradox, 80/20 model approach

## Key Patterns Identified (Root-Cause Solutions)

### 1. Wall-Clock Deadline Propagation (THE critical fix)
- **Problem**: Nested retry multiplication: steps × step_retries × call_retries × call_timeout
  - Lumen's worst case: 24 steps × 3 retries × 90s timeout = 36+ MINUTES with no budget
- **Solution**: Pass an ABSOLUTE deadline down, not per-layer durations
  - `Deadline` class with `remaining()`, `expired()`, `clamp()` methods
  - Every layer checks the deadline before retrying
  - "Every enforced ceiling should have a corresponding advertised budget set somewhat below it"
- **LangGraph native**: `TimeoutPolicy(run_timeout=X, idle_timeout=Y)` — wall-clock cap per node attempt

### 2. Three-Currency Budget (steps/tokens/wall-clock)
- Not just max_steps — also track wall-clock and tokens
- When ANY budget expires → stop, deliver partial result, inform user
- Lumen currently only has max_steps (24) — NO wall-clock budget

### 3. Death Loop / Stagnation Detection
- YouTube (Parth Patil): "death loops" = context window polluted with irrelevant info after 25+ interactions → agent loops
- Solution: Detect when agent repeats same tool calls / same errors → spawn fresh context OR auto-finish
- Lumen's agent_loop has auto-finish nudges but no stagnation detection

### 4. Orchestration Paradox → 80/20 with Counter/Timeout
- YouTube (Qodo): Agents try to find "best way" instead of solving → infinite research loop
- Solution: Give research/exploration agents a COUNTER and TIMEOUT → stop, hand results to execution model
- "giving the 80% models a counter or a timeout so it does not go on and on"

### 5. LangGraph Official Fault Tolerance Primitives
- `RetryPolicy(max_attempts=N, backoff_factor=2.0, retry_on=(ConnectionError, TimeoutError))`
- `TimeoutPolicy(run_timeout=30.0, idle_timeout=5.0)` — hard wall-clock cap
- `error_handler` — runs AFTER retries exhausted, can route to fallback/compensation
- These attach to nodes via `add_node()` — config lives next to logic it protects

### 6. Progressive Disclosure over Pre-Memorization
- YouTube (Parth Patil): MCP tools hurt by pre-loading all tool descriptions into context
- CLI tools better: agent runs `--help` on demand → progressive disclosure
- Lumen: capability_detection catalog is EMPTY (spec_core deleted) — this is actually fine, simplify

## Lumen-Specific Root Cause Mapping
| Weakness | Root Cause | Solution Pattern |
|----------|-----------|-----------------|
| 10-min hang | No wall-clock budget; 24×3×90s retry multiplication | Deadline propagation + TimeoutPolicy |
| Stuck feeling | run_with_heartbeat has NO timeout (only UX updates) | Wrap generation in hard deadline |
| Dead code | spec_core deleted but 61 refs in 26 files | Delete all dead refs |
| Message path complexity | 1701 lines, ~300 dead lines, redundant binds | Remove dead blocks, deduplicate |
| Multi-agent no budget | orchestrator runs with NO deadline | Propagate deadline to orchestrator |
| Cline fallback 30s too short | run_with_engine_timeout=30s but agent needs more | Increase to realistic budget with deadline |
