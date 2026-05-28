"""Compute archetype for every player and write back into players.json.

Idempotent — re-run any time after a stats refresh.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.fairness.archetypes import classify  # noqa: E402
from app.models import Player  # noqa: E402

SEED_DIR = Path(__file__).resolve().parent.parent / "app" / "data" / "seed"


def main() -> None:
    path = SEED_DIR / "players.json"
    raw = json.loads(path.read_text())
    for p in raw:
        player = Player(**p)
        p["archetype"] = classify(player)
    path.write_text(json.dumps(raw, indent=2))

    # Distribution print
    from collections import Counter
    counts = Counter(p["archetype"] for p in raw)
    print(f"Annotated {len(raw)} players with archetypes:")
    for label, n in sorted(counts.items(), key=lambda kv: -kv[1]):
        print(f"  {label:<24} {n}")


if __name__ == "__main__":
    main()
