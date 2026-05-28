"""Fetch per-player salary data from basketball-reference team contract pages.

Loads existing players.json, augments each player with a `contract` block, writes
back. Idempotent — re-running just refreshes the salary values.

    cd backend && python scripts/fetch_salaries.py
"""
from __future__ import annotations

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


def parse_contracts(html: str) -> dict[str, dict[str, Any]]:
    """Returns dict of player_id -> {current_salary, total_guaranteed, years_remaining}."""
    soup = BeautifulSoup(html, "lxml")
    table = soup.find("table", id="contracts")
    if not table:
        return {}
    out: dict[str, dict[str, Any]] = {}
    for tr in table.find("tbody").find_all("tr"):
        # Player anchor in first cell
        link = tr.find("a", href=lambda h: h and h.startswith("/players/"))
        if not link:
            continue
        pid = link.get("href", "").split("/")[-1].replace(".html", "")

        # Find year cells (y1, y2, ..., y6) and remain_gtd
        salaries: list[int] = []
        for stat in ("y1", "y2", "y3", "y4", "y5", "y6"):
            cell = tr.find("td", {"data-stat": stat})
            if cell:
                v = _parse_dollars(cell.text)
                if v > 0:
                    salaries.append(v)
        current = salaries[0] if salaries else 0
        years = len(salaries)
        total_cell = tr.find("td", {"data-stat": "remain_gtd"})
        total_guar = _parse_dollars(total_cell.text) if total_cell else sum(salaries)

        out[pid] = {
            "current_salary": current,
            "total_guaranteed": total_guar,
            "years_remaining": years,
        }
    return out


def main() -> None:
    players_path = SEED_DIR / "players.json"
    players = json.loads(players_path.read_text())
    by_id: dict[str, dict[str, Any]] = {p["id"]: p for p in players}

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
        team_contracts = parse_contracts(html)
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
