"""Recent-team-form retrieval and scoring for Advisor safety labels."""

import threading
import time
from dataclasses import dataclass

import requests


SCORES365_H2H_URL = "https://webws.365scores.com/web/games/h2h/"


@dataclass(frozen=True)
class TeamForm:
    team_id: str
    team_name: str
    score: int
    results: tuple[str, ...]
    matches_count: int
    recent_games: tuple[dict, ...] = ()


@dataclass(frozen=True)
class MatchFormResult:
    home: TeamForm | None
    away: TeamForm | None
    error: str | None = None
    source: str = "365Scores"
    from_cache: bool = False
    game_id: str | None = None
    status_group: int | None = None
    home_score: float | None = None
    away_score: float | None = None


class FormAnalyzer:
    """Fetch and score each fixture's five most recent completed team matches."""

    CACHE_SECONDS = 15 * 60
    REQUEST_COOLDOWN_SECONDS = 0.35
    _cache = {}
    _lock = threading.Lock()
    _last_request_at = 0.0

    def __init__(self, timeout=12):
        self.timeout = timeout

    def fetch_match(self, game_id):
        key = str(game_id or "")
        if not key:
            return MatchFormResult(None, None, "Missing 365Scores game ID.")

        with self._lock:
            cached = self._cache.get(key)
            now = time.monotonic()
            if cached and now - cached[0] < self.CACHE_SECONDS:
                result = cached[1]
                return MatchFormResult(
                    result.home,
                    result.away,
                    result.error,
                    result.source,
                    True,
                    result.game_id,
                    result.status_group,
                    result.home_score,
                    result.away_score,
                )
            wait_for = self.REQUEST_COOLDOWN_SECONDS - (
                now - self.__class__._last_request_at
            )
            if wait_for > 0:
                time.sleep(wait_for)
            result = self._request_match(key)
            self.__class__._last_request_at = time.monotonic()
            self.__class__._cache[key] = (
                self.__class__._last_request_at,
                result,
            )
            return result

    def _request_match(self, game_id):
        try:
            response = requests.get(
                SCORES365_H2H_URL,
                params={
                    "gameId": game_id,
                    "appTypeId": 5,
                    "langId": 1,
                    "timezoneName": "Asia/Jerusalem",
                    "userCountryId": 6,
                },
                headers={
                    "User-Agent": "Mozilla/5.0",
                    "Accept": "application/json",
                    "Origin": "https://www.365scores.com",
                    "Referer": "https://www.365scores.com/",
                },
                timeout=self.timeout,
            )
            response.raise_for_status()
            return self.parse_payload(response.json())
        except requests.RequestException as exc:
            return MatchFormResult(
                None,
                None,
                f"Recent-form request failed: {exc}",
            )
        except (KeyError, TypeError, ValueError) as exc:
            return MatchFormResult(
                None,
                None,
                f"Recent-form response changed: {exc}",
            )

    @classmethod
    def parse_payload(cls, payload):
        game = payload.get("game") or {}
        home_data = game.get("homeCompetitor") or {}
        away_data = game.get("awayCompetitor") or {}
        home = cls.score_team(home_data)
        away = cls.score_team(away_data)
        if home is None or away is None:
            return MatchFormResult(
                home,
                away,
                "365Scores did not provide enough recent team results.",
            )
        return MatchFormResult(
            home,
            away,
            game_id=(
                str(game.get("id"))
                if game.get("id") is not None
                else None
            ),
            status_group=cls.safe_int(game.get("statusGroup")),
            home_score=cls.safe_float(
                (game.get("homeCompetitor") or {}).get("score")
            ),
            away_score=cls.safe_float(
                (game.get("awayCompetitor") or {}).get("score")
            ),
        )

    @classmethod
    def score_team(cls, team_data):
        team_id = team_data.get("id")
        team_name = team_data.get("name")
        if team_id is None or not team_name:
            return None
        recent_games = []
        for game in team_data.get("recentGames", []):
            if not isinstance(game, dict):
                continue
            try:
                is_finished = int(game.get("statusGroup", -1)) == 4
            except (TypeError, ValueError):
                is_finished = False
            if is_finished:
                recent_games.append(game)
        recent_games.sort(
            key=lambda game: str(game.get("startTime") or ""),
            reverse=True,
        )
        results = []
        for game in recent_games:
            result = cls.result_for_team(game, team_id)
            if result:
                results.append(result)
            if len(results) == 5:
                break
        if not results:
            return None
        score = sum({"W": 3, "D": 1, "L": 0}[result] for result in results)
        return TeamForm(
            team_id=str(team_id),
            team_name=str(team_name),
            score=score,
            results=tuple(results),
            matches_count=len(results),
            recent_games=tuple(recent_games),
        )

    @staticmethod
    def safe_int(value):
        try:
            return int(value)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def safe_float(value):
        try:
            parsed = float(value)
            return parsed if parsed >= 0 else None
        except (TypeError, ValueError):
            return None

    @staticmethod
    def result_for_team(game, team_id):
        home = game.get("homeCompetitor") or {}
        away = game.get("awayCompetitor") or {}
        home_id = str(home.get("id"))
        away_id = str(away.get("id"))
        target = str(team_id)
        if target not in {home_id, away_id}:
            return None
        try:
            home_score = float(home.get("score"))
            away_score = float(away.get("score"))
        except (TypeError, ValueError):
            return None
        if home_score == away_score:
            if bool(home.get("isWinner")):
                winning_id = home_id
            elif bool(away.get("isWinner")):
                winning_id = away_id
            else:
                return "D"
        else:
            winning_id = home_id if home_score > away_score else away_id
        return "W" if target == winning_id else "L"

    @staticmethod
    def adjusted_safety(consensus_chance, suggested_form, opponent_form):
        """Return adjusted safety chance, differential, penalty, and alert state."""
        baseline = float(consensus_chance)
        if (
            suggested_form is None
            or opponent_form is None
            or suggested_form.matches_count < 5
            or opponent_form.matches_count < 5
        ):
            return baseline, None, 0.0, False
        differential = suggested_form.score - opponent_form.score
        penalty = 5.0 if differential < -5 else 0.0
        adjusted = max(0.0, baseline - penalty)
        return adjusted, differential, penalty, penalty > 0
