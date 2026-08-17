# Runtime source parts

`market_runtime.py` and `generic_runtime.py` are **assembled** from `market_parts/` and `generic_parts/`.

Edit the part files, then run:
```bash
python -c "from pathlib import Path; ..."
```
Or: the monolith files are the source of truth after assembly for emission into generated bots.

`presets.py` is assembled from `../presets_parts/`.
