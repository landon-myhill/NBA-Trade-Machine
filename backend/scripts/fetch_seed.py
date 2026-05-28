"""Build players.json + teams.json from real bbref data with multi-year context.

Pipeline:
  1. Load 11-season cached history (or fetch via fetch_history if missing)
  2. For each of 30 teams, fetch the current roster page
  3. For each rostered player, build season_logs from history (last 3 valid)
  4. Compute effective (blended) stats — represents typical healthy production
  5. Compute injury_discount from most-recent-season games
  6. Include hurt players (don't skip 0-game seasons if they have prior history)

Usage:
    cd backend && python scripts/fetch_seed.py
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path
from typing import Any

import requests
from bs4 import BeautifulSoup

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.fairness.multi_year import (  # noqa: E402
    effective_stats,
    injury_discount,
    latest_played_season,
    season_log_for_player,
)
from fetch_history import fetch_history  # noqa: E402

SEASON_END_YEAR = 2026
SEASON_LABEL = "2025-26"
SEED_DIR = Path(__file__).resolve().parent.parent / "app" / "data" / "seed"
BBREF = "https://www.basketball-reference.com"
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
CRAWL_DELAY = 3.5

# (bbref_abbr, full_name, canonical_abbr). bbref uses BRK/CHO/PHO for some teams.
TEAMS: list[tuple[str, str, str]] = [
    ("ATL", "Atlanta Hawks", "ATL"),
    ("BOS", "Boston Celtics", "BOS"),
    ("BRK", "Brooklyn Nets", "BKN"),
    ("CHO", "Charlotte Hornets", "CHA"),
    ("CHI", "Chicago Bulls", "CHI"),
    ("CLE", "Cleveland Cavaliers", "CLE"),
    ("DAL", "Dallas Mavericks", "DAL"),
    ("DEN", "Denver Nuggets", "DEN"),
    ("DET", "Detroit Pistons", "DET"),
    ("GSW", "Golden State Warriors", "GSW"),
    ("HOU", "Houston Rockets", "HOU"),
    ("IND", "Indiana Pacers", "IND"),
    ("LAC", "Los Angeles Clippers", "LAC"),
    ("LAL", "Los Angeles Lakers", "LAL"),
    ("MEM", "Memphis Grizzlies", "MEM"),
    ("MIA", "Miami Heat", "MIA"),
    ("MIL", "Milwaukee Bucks", "MIL"),
    ("MIN", "Minnesota Timberwolves", "MIN"),
    ("NOP", "New Orleans Pelicans", "NOP"),
    ("NYK", "New York Knicks", "NYK"),
    ("OKC", "Oklahoma City Thunder", "OKC"),
    ("ORL", "Orlando Magic", "ORL"),
    ("PHI", "Philadelphia 76ers", "PHI"),
    ("PHO", "Phoenix Suns", "PHX"),
    ("POR", "Portland Trail Blazers", "POR"),
    ("SAC", "Sacramento Kings", "SAC"),
    ("SAS", "San Antonio Spurs", "SAS"),
    ("TOR", "Toronto Raptors", "TOR"),
    ("UTA", "Utah Jazz", "UTA"),
    ("WAS", "Washington Wizards", "WAS"),
]

VALID_POSITIONS = {"PG", "SG", "SF", "PF", "C"}


def fetch(url: str) -> str:
    r = requests.get(url, headers={"User-Agent": UA}, timeout=20)
    r.encoding = "utf-8"
    r.raise_for_status()
    return r.text


def parse_team_roster(html: str) -> list[tuple[str, str]]:
    """Returns list of (player_id, position_from_roster_page)."""
    soup = BeautifulSoup(html, "lxml")
    table = soup.find("table", id="roster")
    if not table:
        return []
    out: list[tuple[str, str]] = []
    for tr in table.find("tbody").find_all("tr"):
        link = tr.find("a", href=lambda h: h and h.startswith("/players/"))
        if not link:
            continue
        pid = link.get("href", "").split("/")[-1].replace(".html", "")
        pos_td = tr.find("td", {"data-stat": "pos"})
        pos = pos_td.text.strip() if pos_td else ""
        out.append((pid, pos))
    return out


def normalize_position(pos_raw: str) -> str:
    for chunk in pos_raw.split("-"):
        chunk = chunk.strip()
        if chunk in VALID_POSITIONS:
            return chunk
    return "SF"


def main() -> None:
    print("Loading multi-year history (uses cache if available)…")
    history = fetch_history(refresh=False)
    print(f"  {len(history)} players in history")

    teams_out: list[dict[str, Any]] = []
    players_out: list[dict[str, Any]] = []
    skipped: list[str] = []
    hurt_recovered: list[str] = []

    for bbref_abbr, full_name, canonical in TEAMS:
        print(f"Fetching roster: {full_name} ({bbref_abbr})…")
        try:
            roster_html = fetch(
                f"{BBREF}/teams/{bbref_abbr}/{SEASON_END_YEAR}.html"
            )
        except requests.HTTPError as e:
            print(f"  ERROR: {e}; skipping")
            time.sleep(CRAWL_DELAY)
            continue
        roster_entries = parse_team_roster(roster_html)
        team_count = 0
        for pid, roster_pos in roster_entries:
            logs = history.get(pid, [])
            if not logs:
                skipped.append(f"{pid} ({canonical})")
                continue

            # Build season_logs (newest first, last 5 for richer history)
            season_logs = [season_log_for_player(l) for l in logs[:5]]

            # Compute effective stats by multi-year blend
            blended = effective_stats(logs)

            # Determine player metadata
            latest = latest_played_season(logs) or logs[0]
            name = latest.get("name") or logs[0].get("name", pid)
            position = normalize_position(
                latest.get("position", "") or roster_pos
            )

            # Current age: latest log's age + years elapsed since
            latest_season = latest.get("season", SEASON_LABEL)
            latest_end_year = int(latest_season.split("-")[0]) + 1
            years_elapsed = SEASON_END_YEAR - latest_end_year
            age = int(latest.get("age", 0) or 0) + max(0, years_elapsed)

            # Injury discount: based on current-season games played
            discount = injury_discount(logs, SEASON_LABEL)
            if discount < 0.95:
                hurt_recovered.append(f"{name} ({canonical}) discount={discount:.2f}")

            players_out.append(
                {
                    "id": pid,
                    "name": name,
                    "team_id": canonical,
                    "position": position,
                    "age": age,
                    "stats": {
                        "season": SEASON_LABEL,
                        "games_played": int(blended.get("games_played", 0)),
                        "minutes_per_game": round(blended.get("minutes_per_game", 0), 1),
                        "points": round(blended.get("points", 0), 1),
                        "rebounds": round(blended.get("rebounds", 0), 1),
                        "assists": round(blended.get("assists", 0), 1),
                        "steals": round(blended.get("steals", 0), 2),
                        "blocks": round(blended.get("blocks", 0), 2),
                        "turnovers": round(blended.get("turnovers", 0), 2),
                        "fg_pct": round(blended.get("fg_pct", 0), 3),
                        "three_pct": round(blended.get("three_pct", 0), 3),
                        "ft_pct": round(blended.get("ft_pct", 0), 3),
                        "fta_per_game": round(blended.get("fta_per_game", 0), 1),
                        "three_attempts_per_game": round(
                            blended.get("three_attempts_per_game", 0), 1
                        ),
                        "epm": round(blended.get("bpm", 0), 2),  # substitute
                        "bpm": round(blended.get("bpm", 0), 2),
                        "obpm": round(blended.get("obpm", 0), 2),
                        "dbpm": round(blended.get("dbpm", 0), 2),
                        "vorp": round(blended.get("vorp", 0), 2),
                        "per": round(blended.get("per", 0), 1),
                        "usg_pct": round(blended.get("usg_pct", 0), 1),
                        "ts_pct": round(blended.get("ts_pct", 0), 3),
                        "ast_pct": round(blended.get("ast_pct", 0), 1),
                        "tov_pct": round(blended.get("tov_pct", 0), 1),
                        "all_nba": bool(blended.get("all_nba", False)),
                        "all_star": bool(blended.get("all_star", False)),
                    },
                    "season_logs": season_logs,
                    "injury_discount": round(discount, 2),
                }
            )
            team_count += 1
        teams_out.append(
            {
                "id": canonical,
                "name": full_name,
                "abbreviation": canonical,
                "needs": [],
                "timeline": "play_in",
            }
        )
        print(f"  {team_count} players added")
        time.sleep(CRAWL_DELAY)

    SEED_DIR.mkdir(parents=True, exist_ok=True)
    (SEED_DIR / "teams.json").write_text(json.dumps(teams_out, indent=2))
    (SEED_DIR / "players.json").write_text(json.dumps(players_out, indent=2))
    print()
    print(f"Wrote {len(teams_out)} teams, {len(players_out)} players")
    if skipped:
        print(f"Skipped {len(skipped)} players (no history at all): {skipped[:5]}…")
    if hurt_recovered:
        print(f"\nHurt players recovered ({len(hurt_recovered)}):")
        for entry in hurt_recovered[:15]:
            print(f"  {entry}")


if __name__ == "__main__":
    main()
