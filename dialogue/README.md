# Maestro Dialogue — Rasa only

**No rule-based chat in production.** Understanding comes from a trained Rasa model.

## Enable on hosting

```bash
DIALOGUE_ENABLED=1
# first deploy without model:
DIALOGUE_TRAIN_ON_START=1
```

Or SSH/one-off:

```bash
bash scripts/train_dialogue.sh
# restarts bot after models/maestro-dialogue.tar.gz exists
```

## Data

- `data/nlu.yml` + `data/nlu_platform.yml` — intents & examples  
- `data/stories.yml` + `data/rules.yml` — dialogue paths  
- `domain.yml` — responses (platform knowledge)  
- `models/*.tar.gz` — trained artifact

## Architecture

```
Telegram → dialogue_bridge → Rasa Agent (model required)
                          ↘ None → legacy messages.py
```
