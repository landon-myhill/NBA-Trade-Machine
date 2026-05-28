"""Build picks.json using:

  1. Real 2026 picks (post-lottery + traded picks) hand-coded from Wikipedia,
     loaded from picks_2026_real.json.
  2. Standings-based picks for 2027-2029 (best-effort; teams projected to keep
     their own picks at their current pace).
  3. Optional overrides in pick_overrides.json (add/remove/edit operations).

Re-run after editing pick_overrides.json or picks_2026_real.json.
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import requests
from bs4 import BeautifulSoup

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

SEED_DIR = Path(__file__).resolve().parent.parent / "app" / "data" / "seed"
REAL_2026_PATH = SEED_DIR / "picks_2026_real.json"
OVERRIDES_PATH = SEED_DIR / "pick_overrides.json"
BBREF = "https://www.basketball-reference.com"
UA = "Mozilla/5.0 Chrome/120.0.0.0 Safari/537.36"
SEASON_END_YEAR = 2026

BBREF_TO_CANONICAL = {"BRK": "BKN", "CHO": "CHA", "PHO": "PHX"}
DEFAULT_FAR_PICK = 15
SECOND_ROUND_OFFSET = 30


def fetch_standings() -> list[tuple[str, int, int]]:
    r = requests.get(
        f"{BBREF}/leagues/NBA_{SEASON_END_YEAR}_standings.html",
        headers={"User-Agent": UA},
        timeout=20,
    )
    r.encoding = "utf-8"
    r.raise_for_status()
    soup = BeautifulSoup(r.text, "lxml")
    teams: list[tuple[str, int, int]] = []
    for table_id in ("confs_standings_E", "confs_standings_W"):
        t = soup.find("table", id=table_id)
        for tr in t.find("tbody").find_all("tr"):
            name_cell = tr.find(["th", "td"], {"data-stat": "team_name"})
            wins = tr.find("td", {"data-stat": "wins"})
            losses = tr.find("td", {"data-stat": "losses"})
            if not (name_cell and wins and losses):
                continue
            link = name_cell.find("a")
            href = link.get("href", "") if link else ""
            bbref_abbr = href.split("/")[2] if href else ""
            canonical = BBREF_TO_CANONICAL.get(bbref_abbr, bbref_abbr)
            teams.append((canonical, int(wins.text), int(losses.text)))
    return teams


def draft_order(standings: list[tuple[str, int, int]]) -> dict[str, int]:
    sorted_teams = sorted(standings, key=lambda x: (x[1], -x[2]))
    return {abbr: rank + 1 for rank, (abbr, _, _) in enumerate(sorted_teams)}


def load_real_2026() -> list[dict]:
    """Convert picks_2026_real.json into picks.json schema."""
    data = json.loads(REAL_2026_PATH.read_text())
    out: list[dict] = []
    for entry in data["first_round"]:
        owner = entry["owner"]
        origin = entry["origin"]
        pick_num = entry["pick"]
        # ID encodes traded picks distinctively
        if owner == origin:
            pick_id = f"{owner}-2026-1"
        else:
            pick_id = f"{owner}-2026-1-from-{origin}"
        out.append(
            {
                "id": pick_id,
                "owner_team_id": owner,
                "origin_team_id": origin,
                "year": 2026,
                "round": 1,
                "protections": entry.get("protections"),
                "expected_pick": pick_num,
            }
        )
    return out


def generate_future_picks(
    standings_order: dict[str, int], existing_team_ids: set[str]
) -> list[dict]:
    """Picks for 2027-2031. Each team keeps own pick; expected pick = their record-based slot."""
    out: list[dict] = []
    for team_id in existing_team_ids:
        slot = standings_order.get(team_id, DEFAULT_FAR_PICK)
        for year in (2027, 2028, 2029, 2030, 2031):
            # Year 0-1 use current standings; later years revert to league average
            exp_pick = slot if year == 2027 else DEFAULT_FAR_PICK
            out.append(
                {
                    "id": f"{team_id}-{year}-1",
                    "owner_team_id": team_id,
                    "origin_team_id": team_id,
                    "year": year,
                    "round": 1,
                    "protections": None,
                    "expected_pick": exp_pick,
                }
            )
            out.append(
                {
                    "id": f"{team_id}-{year}-2",
                    "owner_team_id": team_id,
                    "origin_team_id": team_id,
                    "year": year,
                    "round": 2,
                    "protections": None,
                    "expected_pick": exp_pick + SECOND_ROUND_OFFSET,
                }
            )
    return out


def generate_2026_second_round(
    standings_order: dict[str, int], existing_team_ids: set[str]
) -> list[dict]:
    """Approximate 2nd-round 2026 picks: each team owns their own slot + 30."""
    out: list[dict] = []
    for team_id in existing_team_ids:
        slot = standings_order.get(team_id, DEFAULT_FAR_PICK)
        out.append(
            {
                "id": f"{team_id}-2026-2",
                "owner_team_id": team_id,
                "origin_team_id": team_id,
                "year": 2026,
                "round": 2,
                "protections": None,
                "expected_pick": slot + SECOND_ROUND_OFFSET,
            }
        )
    return out


def apply_overrides(picks: list[dict]) -> list[dict]:
    if not OVERRIDES_PATH.exists():
        return picks
    overrides = json.loads(OVERRIDES_PATH.read_text())
    add = overrides.get("add", [])
    remove_ids = set(overrides.get("remove", []))
    edit = {e["id"]: e for e in overrides.get("edit", [])}

    out: list[dict] = []
    for p in picks:
        if p["id"] in remove_ids:
            continue
        if p["id"] in edit:
            p = {**p, **edit[p["id"]]}
        out.append(p)
    out.extend(add)
    return out


def main() -> None:
    teams_data = json.loads((SEED_DIR / "teams.json").read_text())
    valid_team_ids = {t["id"] for t in teams_data}

    print(f"Loading real 2026 picks from {REAL_2026_PATH.name}…")
    real_2026 = load_real_2026()
    print(f"  {len(real_2026)} first-round picks loaded")

    print(f"\nFetching 2025-26 standings for future-year projection…")
    standings = fetch_standings()
    order = draft_order(standings)
    time.sleep(3.5)

    # Combine: real 2026 R1 + generated 2026 R2 + future years
    picks: list[dict] = []
    picks.extend(real_2026)
    picks.extend(generate_2026_second_round(order, valid_team_ids))
    picks.extend(generate_future_picks(order, valid_team_ids))

    picks = apply_overrides(picks)
    picks.sort(key=lambda p: (p["year"], p["round"], p["expected_pick"]))

    (SEED_DIR / "picks.json").write_text(json.dumps(picks, indent=2))

    # Diagnostic
    by_team_2026 = {}
    for p in picks:
        if p["year"] == 2026 and p["round"] == 1:
            by_team_2026.setdefault(p["owner_team_id"], []).append(p["expected_pick"])
    print(f"\n2026 first-round ownership:")
    for team in sorted(by_team_2026):
        picks_str = ", ".join(f"#{p}" for p in by_team_2026[team])
        marker = " ⭐" if len(by_team_2026[team]) > 1 else ""
        print(f"  {team}: {picks_str}{marker}")
    print(f"\nWrote {len(picks)} picks across {len(valid_team_ids)} teams")


if __name__ == "__main__":
    main()
