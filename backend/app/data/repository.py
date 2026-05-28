from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Protocol

from app.models import DraftPick, Player, Team, TierRubric

SEED_DIR = Path(__file__).parent / "seed"


class Repository(Protocol):
    """Data access boundary. A live API can swap in by implementing this protocol."""

    def list_teams(self) -> list[Team]: ...
    def get_team(self, team_id: str) -> Team | None: ...
    def list_players(self) -> list[Player]: ...
    def get_player(self, player_id: str) -> Player | None: ...
    def list_picks(self) -> list[DraftPick]: ...
    def get_pick(self, pick_id: str) -> DraftPick | None: ...
    def get_rubric(self) -> TierRubric: ...


class JsonRepository:
    """Loads seed data from JSON files in app/data/seed/."""

    def __init__(self, seed_dir: Path = SEED_DIR) -> None:
        self.seed_dir = seed_dir

    def _load(self, filename: str) -> list[dict] | dict:
        return json.loads((self.seed_dir / filename).read_text())

    @lru_cache(maxsize=1)
    def _teams(self) -> dict[str, Team]:
        return {t["id"]: Team(**t) for t in self._load("teams.json")}

    @lru_cache(maxsize=1)
    def _players(self) -> dict[str, Player]:
        return {p["id"]: Player(**p) for p in self._load("players.json")}

    @lru_cache(maxsize=1)
    def _picks(self) -> dict[str, DraftPick]:
        return {pk["id"]: DraftPick(**pk) for pk in self._load("picks.json")}

    @lru_cache(maxsize=1)
    def _rubric(self) -> TierRubric:
        return TierRubric(**self._load("rubric.json"))

    def list_teams(self) -> list[Team]:
        return list(self._teams().values())

    def get_team(self, team_id: str) -> Team | None:
        return self._teams().get(team_id)

    def list_players(self) -> list[Player]:
        return list(self._players().values())

    def get_player(self, player_id: str) -> Player | None:
        return self._players().get(player_id)

    def list_picks(self) -> list[DraftPick]:
        return list(self._picks().values())

    def get_pick(self, pick_id: str) -> DraftPick | None:
        return self._picks().get(pick_id)

    def get_rubric(self) -> TierRubric:
        return self._rubric()


_repo: Repository = JsonRepository()


def get_repo() -> Repository:
    return _repo
