# Maestro Dialogue — Phase 0 (Solid Foundation)

Smart guided chat for **Free and Pro**. Generation stays in `telegram_bot_engine`.

## Architecture (stable)

```
Telegram
  → bot_interface/messages.py
  → dialogue_bridge
  → dialogue.runtime.handle_turn
       ├─ RasaEngine   (if DIALOGUE_ENABLED=1 AND models/*.tar.gz)
       └─ RuleEngine   (always available — production backbone)
```

| Component | Role |
|-----------|------|
| `runtime/contract.py` | Stable Request/Response/Engine protocol |
| `runtime/rule_engine.py` | Deterministic AR/EN guided chat (no deps) |
| `runtime/rasa_engine.py` | Optional ML layer on top of rules |
| `runtime/registry.py` | Engine selection + fallback |
| `data/*` | Rasa training corpus (expand continuously) |
| `actions/` | rasa-sdk hooks to plan/Mongo |

## Behaviour guarantees

1. **Never generates bots** from this layer.
2. **`describe_bot_idea` is handoff** (`handled=False`) → legacy generation path runs.
3. **Rasa failure → RuleEngine** automatically.
4. **`DIALOGUE_RUNTIME=0`** disables the whole layer (full legacy).
5. **Default `DIALOGUE_RUNTIME=1`** so chat is smart without training.

## Train Rasa (optional upgrade path)

```bash
./scripts/train_dialogue.sh
# deploy dialogue/models/*.tar.gz
export DIALOGUE_ENABLED=1
export DIALOGUE_RUNTIME=1
```

## Tests

```bash
python -m pytest tests/test_dialogue_phase0.py -q
```
