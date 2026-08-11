# Maestro Dialogue (Rasa) — Phase 0

Smart guided chat for **Free and Pro**. Does **not** run the generation engine.

## Layout

| Path | Role |
|------|------|
| `config.yml` | NLU pipeline + Core policies |
| `domain.yml` | Intents, slots, responses, actions |
| `data/nlu.yml` | Training examples (AR/EN) |
| `data/stories.yml` | Dialogue paths |
| `data/rules.yml` | Deterministic rules |
| `actions/` | rasa-sdk (plan report, session, fallback) |
| `models/` | Trained `.tar.gz` shipped to hosting |

## Train (dev machine / CI)

```bash
./scripts/train_dialogue.sh
```

## Enable on hosting

```bash
DIALOGUE_ENABLED=1
# optional action server later:
# rasa run actions --actions actions -p 5055
```

`bot_interface/dialogue_bridge.py` loads the latest `models/*.tar.gz`.
If no model or flag off → Telegram keeps the legacy path (no breakage).

## Integration boundary

```
Telegram → bot_interface → dialogue_bridge → Rasa Agent
                              ↘ None → legacy messages.py paths
telegram_bot_engine  = generation only (unchanged in Phase 0)
b2b_platform         = plans / Mongo (actions read plan only)
```

## Next phases

1. Wire bridge early in `handle_message` behind the flag  
2. Expand NLU (augmentation)  
3. Pro-only actions for generation handoff  
4. Optional Mongo tracker store  
