"""Refresh everything in order: history → seed → salaries → archetypes → picks.

    cd backend && python scripts/refresh_all.py
    cd backend && python scripts/refresh_all.py --refresh-history  # also re-fetch 11 seasons

Takes ~3-4 minutes (longer the first time, when 11-season history is fetched).
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import fetch_history  # noqa: E402
import fetch_seed  # noqa: E402
import fetch_salaries  # noqa: E402
import patch_salaries  # noqa: E402
import annotate_archetypes  # noqa: E402
import generate_picks  # noqa: E402
import derive_team_context  # noqa: E402


def main() -> None:
    refresh_history = "--refresh-history" in sys.argv
    print("\n=== 1/7 Multi-year history (uses cache unless --refresh-history) ===")
    fetch_history.fetch_history(refresh=refresh_history)
    print("\n=== 2/7 Building rosters with effective stats ===")
    fetch_seed.main()
    print("\n=== 3/7 Fetching salaries ===")
    fetch_salaries.main()
    print("\n=== 4/7 Applying salary overrides ===")
    patch_salaries.main()
    print("\n=== 5/7 Classifying archetypes ===")
    annotate_archetypes.main()
    print("\n=== 6/7 Generating picks from real standings ===")
    generate_picks.main()
    print("\n=== 7/7 Deriving team needs + timeline ===")
    derive_team_context.main()
    print("\nDone.")


if __name__ == "__main__":
    main()
