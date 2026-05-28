"""Fetch multi-year per-player stats from basketball-reference.

Pulls 11 seasons (2015-16 through 2025-26) of per-game + advanced league pages.
Caches the raw result to /tmp/bbref_history.json so re-runs are instant.

Usage:
    python scripts/fetch_history.py            # uses cache if exists
    python scripts/fetch_history.py --refresh  # force re-fetch
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path
from typing import Any

import requests
from bs4 import BeautifulSoup

BBREF = "https://www.basketball-reference.com"
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
CRAWL_DELAY = 3.5

SEASON_END_YEARS = list(range(2016, 2027))  # 2015-16 through 2025-26
CACHE_PATH = Path("/tmp/bbref_history.json")


def _season_label(end_year: int) -> str:
    return f"{end_year - 1}-{str(end_year)[2:]}"


def fetch(url: str) -> str:
    r = requests.get(url, headers={"User-Agent": UA}, timeout=20)
    r.encoding = "utf-8"
    r.raise_for_status()
    return r.text


def _td(row, stat: str) -> str:
    td = row.find("td", {"data-stat": stat})
    return td.text.strip() if td else ""


def _td_float(row, stat: str, default: float = 0.0) -> float:
    v = _td(row, stat)
    try:
        return float(v) if v else default
    except ValueError:
        return default


def _td_int(row, stat: str, default: int = 0) -> int:
    v = _td(row, stat)
    try:
        return int(v) if v else default
    except ValueError:
        return default


def parse_per_game(html: str) -> dict[str, dict[str, Any]]:
    soup = BeautifulSoup(html, "lxml")
    table = soup.find("table", id="per_game_stats")
    if not table:
        return {}
    out: dict[str, dict[str, Any]] = {}
    for tr in table.find("tbody").find_all("tr"):
        name_td = tr.find("td", {"data-stat": "name_display"})
        if not name_td:
            continue
        pid = name_td.get("data-append-csv")
        if not pid:
            continue
        team = _td(tr, "team_name_abbr")
        is_tot = team in ("2TM", "3TM", "4TM", "5TM")
        row = {
            "name": name_td.text.strip(),
            "age": _td_int(tr, "age"),
            "position": _td(tr, "pos"),
            "games_played": _td_int(tr, "games"),
            "minutes_per_game": _td_float(tr, "mp_per_g"),
            "points": _td_float(tr, "pts_per_g"),
            "rebounds": _td_float(tr, "trb_per_g"),
            "assists": _td_float(tr, "ast_per_g"),
            "steals": _td_float(tr, "stl_per_g"),
            "blocks": _td_float(tr, "blk_per_g"),
            "turnovers": _td_float(tr, "tov_per_g"),
            "fg_pct": _td_float(tr, "fg_pct"),
            "three_pct": _td_float(tr, "fg3_pct"),
            "ft_pct": _td_float(tr, "ft_pct"),
            "fta_per_game": _td_float(tr, "fta_per_g"),
            "three_attempts_per_game": _td_float(tr, "fg3a_per_g"),
        }
        if pid not in out or is_tot:
            out[pid] = row
    return out


def parse_advanced(html: str) -> dict[str, dict[str, Any]]:
    soup = BeautifulSoup(html, "lxml")
    table = soup.find("table", id="advanced")
    if not table:
        return {}
    out: dict[str, dict[str, Any]] = {}
    for tr in table.find("tbody").find_all("tr"):
        name_td = tr.find("td", {"data-stat": "name_display"})
        if not name_td:
            continue
        pid = name_td.get("data-append-csv")
        if not pid:
            continue
        team = _td(tr, "team_name_abbr")
        is_tot = team in ("2TM", "3TM", "4TM", "5TM")
        awards = _td(tr, "awards")
        award_codes = [a.strip() for a in awards.split(",") if a.strip()]
        row = {
            "bpm": _td_float(tr, "bpm"),
            "obpm": _td_float(tr, "obpm"),
            "dbpm": _td_float(tr, "dbpm"),
            "vorp": _td_float(tr, "vorp"),
            "per": _td_float(tr, "per"),
            "usg_pct": _td_float(tr, "usg_pct"),
            "ts_pct": _td_float(tr, "ts_pct"),
            "ast_pct": _td_float(tr, "ast_pct"),
            "tov_pct": _td_float(tr, "tov_pct"),
            "all_star": "AS" in award_codes,
            "all_nba": any(c.startswith("NBA") for c in award_codes),
        }
        if pid not in out or is_tot:
            out[pid] = row
    return out


def fetch_history(refresh: bool = False) -> dict[str, list[dict[str, Any]]]:
    """Returns dict mapping player_id -> [season_dict, ...] newest first."""
    if not refresh and CACHE_PATH.exists():
        print(f"Loading cached history from {CACHE_PATH}")
        return json.loads(CACHE_PATH.read_text())

    history: dict[str, list[dict[str, Any]]] = {}
    for end_year in SEASON_END_YEARS:
        season = _season_label(end_year)
        print(f"Fetching {season}…")
        try:
            pg = parse_per_game(
                fetch(f"{BBREF}/leagues/NBA_{end_year}_per_game.html")
            )
            time.sleep(CRAWL_DELAY)
            adv = parse_advanced(
                fetch(f"{BBREF}/leagues/NBA_{end_year}_advanced.html")
            )
            time.sleep(CRAWL_DELAY)
        except requests.HTTPError as e:
            print(f"  ERROR {e}; skipping {season}")
            continue
        seen = set(pg) | set(adv)
        for pid in seen:
            p = pg.get(pid, {})
            a = adv.get(pid, {})
            row = {"season": season, **p, **a}
            history.setdefault(pid, []).insert(0, row)  # newest first
        print(f"  {len(seen)} players")

    # Sort each player's logs newest-first by season
    for pid in history:
        history[pid].sort(key=lambda r: r.get("season", ""), reverse=True)

    CACHE_PATH.write_text(json.dumps(history))
    print(f"\nCached to {CACHE_PATH} ({len(history)} unique players)")
    return history


if __name__ == "__main__":
    refresh = "--refresh" in sys.argv
    fetch_history(refresh=refresh)
