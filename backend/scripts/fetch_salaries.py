"""Fetch per-player salary data from basketball-reference team contract pages.

Loads existing players.json, augments each player with a `contract` block, writes
back. Idempotent — re-running just refreshes the salary values.

    cd backend && python scripts/fetch_salaries.py
    cd backend && python scripts/fetch_salaries.py --target-season 2026-27

bbref's contracts pages show a multi-year grid (y1..y6). By default the script
uses y1 (whatever season bbref currently displays as "current"). Pass
--target-season YYYY-YY to detect the matching column from the table header and
use that year as current_salary instead. Useful in the offseason when bbref
hasn't rolled forward yet but you want to plan for the upcoming league year.
"""
from __future__ import annotations

import argparse
import json
import time
from pathlib import Path
from typing import Any

import requests
from bs4 import BeautifulSoup

BBREF = "https://www.basketball-reference.com"
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
CRAWL_DELAY = 3.5
SEED_DIR = Path(__file__).resolve().parent.parent / "app" / "data" / "seed"

# bbref uses BRK/CHO/PHO for some teams; map back to canonical NBA abbrevs
BBREF_TO_CANONICAL = {
    "BRK": "BKN",
    "CHO": "CHA",
    "PHO": "PHX",
}
BBREF_TEAM_CODES = [
    "ATL", "BOS", "BRK", "CHO", "CHI", "CLE", "DAL", "DEN", "DET", "GSW",
    "HOU", "IND", "LAC", "LAL", "MEM", "MIA", "MIL", "MIN", "NOP", "NYK",
    "OKC", "ORL", "PHI", "PHO", "POR", "SAC", "SAS", "TOR", "UTA", "WAS",
]


def fetch(url: str) -> str:
    r = requests.get(url, headers={"User-Agent": UA}, timeout=20)
    r.encoding = "utf-8"
    r.raise_for_status()
    return r.text


def _parse_dollars(s: str) -> int:
    s = s.strip().replace("$", "").replace(",", "")
    if not s:
        return 0
    try:
        return int(s)
    except ValueError:
        return 0


Y_STATS = ("y1", "y2", "y3", "y4", "y5", "y6")


def _season_to_stat(table) -> dict[str, str]:
    """Map season label (e.g. '2025-26') → data-stat name ('y1' / 'y2' / ...).

    Built from the <thead> row that labels each year column.
    """
    out: dict[str, str] = {}
    head = table.find("thead")
    if not head:
        return out
    rows = head.find_all("tr")
    if not rows:
        return out
    for cell in rows[-1].find_all(["th", "td"]):
        ds = cell.get("data-stat", "")
        if ds in Y_STATS:
            label = cell.get_text(strip=True)
            if label:
                out[label] = ds
    return out


def parse_contracts(
    html: str, target_season: str | None = None
) -> dict[str, dict[str, Any]]:
    """Returns dict of player_id -> {current_salary, total_guaranteed, years_remaining}.

    If target_season is set, the script picks that season's column as the
    "current" salary and counts years_remaining from that column forward.
    """
    soup = BeautifulSoup(html, "lxml")
    table = soup.find("table", id="contracts")
    if not table:
        return {}

    if target_season:
        season_map = _season_to_stat(table)
        start_stat = season_map.get(target_season)
        if not start_stat:
            # Target season is not on this team's page (every player on it has
            # already departed or contract data hasn't rolled forward). Skip.
            return {}
    else:
        start_stat = "y1"
    start_idx = Y_STATS.index(start_stat)
    active_stats = Y_STATS[start_idx:]

    out: dict[str, dict[str, Any]] = {}
    for tr in table.find("tbody").find_all("tr"):
        link = tr.find("a", href=lambda h: h and h.startswith("/players/"))
        if not link:
            continue
        pid = link.get("href", "").split("/")[-1].replace(".html", "")

        # Per-year salaries from the target year forward, in order.
        salaries: list[int] = []
        for stat in active_stats:
            cell = tr.find("td", {"data-stat": stat})
            if cell:
                v = _parse_dollars(cell.text)
                if v > 0:
                    salaries.append(v)

        current = salaries[0] if salaries else 0
        years = len(salaries)
        # When targeting a future season we can't reuse bbref's remain_gtd field
        # (it's from y1). Sum the per-year cells directly — most contracts are
        # fully guaranteed so this is accurate; partial guarantees would need
        # an override entry.
        total_guar = sum(salaries) if target_season else (
            _parse_dollars(tr.find("td", {"data-stat": "remain_gtd"}).text)
            if tr.find("td", {"data-stat": "remain_gtd"})
            else sum(salaries)
        )

        if current == 0:
            # Player has no salary in or after the target season — skip.
            continue

        out[pid] = {
            "current_salary": current,
            "total_guaranteed": total_guar,
            "years_remaining": years,
        }
    return out


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--target-season",
        default=None,
        help="Season label exactly as bbref shows it (e.g. '2026-27'). "
        "When set, salaries are read from that year's column instead of y1.",
    )
    args = parser.parse_args()

    players_path = SEED_DIR / "players.json"
    players = json.loads(players_path.read_text())
    by_id: dict[str, dict[str, Any]] = {p["id"]: p for p in players}

    target = args.target_season
    if target:
        print(f"Targeting {target} cap hits (using bbref column for that season).")

    all_contracts: dict[str, dict[str, Any]] = {}
    for code in BBREF_TEAM_CODES:
        canonical = BBREF_TO_CANONICAL.get(code, code)
        print(f"Fetching contracts for {canonical}…")
        try:
            html = fetch(f"{BBREF}/contracts/{code}.html")
        except requests.HTTPError as e:
            print(f"  ERROR {e}; skipping")
            time.sleep(CRAWL_DELAY)
            continue
        team_contracts = parse_contracts(html, target_season=target)
        all_contracts.update(team_contracts)
        print(f"  {len(team_contracts)} contracts")
        time.sleep(CRAWL_DELAY)

    # Apply to players
    matched = 0
    for pid, contract in all_contracts.items():
        if pid in by_id:
            by_id[pid]["contract"] = contract
            matched += 1

    # Ensure every player has a contract field (empty default if no data)
    for p in players:
        p.setdefault("contract", {"current_salary": 0, "total_guaranteed": 0, "years_remaining": 0})

    players_path.write_text(json.dumps(players, indent=2))
    print()
    print(f"Matched contracts for {matched}/{len(players)} players")
    print(f"Wrote {players_path}")


if __name__ == "__main__":
    main()
