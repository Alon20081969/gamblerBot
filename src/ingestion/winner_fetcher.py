"""Best-effort retrieval and matching for publicly listed Winner soccer odds."""

import json
import os
import re
import sqlite3
import threading
import time
import unicodedata
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from difflib import SequenceMatcher
from pathlib import Path
from contextlib import closing

import requests
from bs4 import BeautifulSoup


DEFAULT_WINNER_URL = "https://www.winner.co.il/"
WINNER_PUBLIC_LINE_URL = (
    "https://api.winner.co.il/v2/publicapi/GetCMobileLine"
)
SCORES365_WINNER_URL = (
    "https://webws.365scores.com/web/bets/lines/bestodds/"
)
PROJECT_ROOT = Path(__file__).resolve().parents[2]
WINNER_HISTORY_DB = PROJECT_ROOT / "data" / "winner_odds_history.sqlite3"

# Winner frequently uses Hebrew display names while the global feed uses English.
# Add aliases here as mismatches are discovered; matching remains fuzzy afterward.
TEAM_ALIASES = {
    "argentina": ("ארגנטינה",),
    "austria": ("אוסטריה",),
    "australia": ("אוסטרליה",),
    "belgium": ("בלגיה",),
    "brazil": ("ברזיל",),
    "canada": ("קנדה",),
    "colombia": ("קולומביה",),
    "costa rica": ("קוסטה ריקה",),
    "croatia": ("קרואטיה",),
    "curacao": ("קוראסאו",),
    "czech republic": ("צכיה", "צ׳כיה"),
    "denmark": ("דנמרק",),
    "ecuador": ("אקוודור",),
    "egypt": ("מצרים",),
    "england": ("אנגליה",),
    "france": ("צרפת",),
    "germany": ("גרמניה",),
    "greece": ("יוון",),
    "hungary": ("הונגריה",),
    "iceland": ("איסלנד",),
    "iran": ("איראן",),
    "iraq": ("עיראק",),
    "ivory coast": ("חוף השנהב",),
    "israel": ("ישראל",),
    "italy": ("איטליה",),
    "japan": ("יפן",),
    "mexico": ("מקסיקו",),
    "morocco": ("מרוקו",),
    "netherlands": ("הולנד",),
    "new zealand": ("ניו זילנד",),
    "nigeria": ("ניגריה",),
    "norway": ("נורבגיה",),
    "panama": ("פנמה",),
    "paraguay": ("פרגוואי",),
    "peru": ("פרו",),
    "poland": ("פולין",),
    "portugal": ("פורטוגל",),
    "qatar": ("קטאר",),
    "romania": ("רומניה",),
    "saudi arabia": ("ערב הסעודית",),
    "scotland": ("סקוטלנד",),
    "senegal": ("סנגל",),
    "serbia": ("סרביה",),
    "slovakia": ("סלובקיה",),
    "slovenia": ("סלובניה",),
    "south africa": ("דרום אפריקה",),
    "south korea": ("דרום קוריאה", "קוריאה הדרומית"),
    "spain": ("ספרד",),
    "sweden": ("שוודיה",),
    "switzerland": ("שוויץ",),
    "tunisia": ("תוניסיה",),
    "turkey": ("טורקיה",),
    "ukraine": ("אוקראינה",),
    "united arab emirates": ("איחוד האמירויות",),
    "united states": ("ארצות הברית", "ארהב"),
    "uruguay": ("אורוגוואי",),
    "uzbekistan": ("אוזבקיסטן",),
    "wales": ("וויילס",),
}

HOME_KEYS = ("home", "home_team", "homeTeam", "competitor1", "team1")
AWAY_KEYS = ("away", "away_team", "awayTeam", "competitor2", "team2")
HOME_ODDS_KEYS = ("home_odds", "homeOdds", "odd1", "price1", "odds1")
DRAW_ODDS_KEYS = ("draw_odds", "drawOdds", "oddX", "priceX", "oddsX")
AWAY_ODDS_KEYS = ("away_odds", "awayOdds", "odd2", "price2", "odds2")


@dataclass(frozen=True)
class WinnerMatch:
    home_team: str
    away_team: str
    match_id: str | None = None
    start_time: str | None = None
    home_odds: float | None = None
    draw_odds: float | None = None
    away_odds: float | None = None
    home_previous_odds: float | None = None
    draw_previous_odds: float | None = None
    away_previous_odds: float | None = None
    home_opening_odds: float | None = None
    draw_opening_odds: float | None = None
    away_opening_odds: float | None = None
    home_trend: int | None = None
    draw_trend: int | None = None
    away_trend: int | None = None
    source: str = "Winner"

    def odd_for(self, odds_column):
        return {
            "home_odds": self.home_odds,
            "draw_odds": self.draw_odds,
            "away_odds": self.away_odds,
        }.get(odds_column)

    def previous_for(self, odds_column):
        return {
            "home_odds": self.home_previous_odds,
            "draw_odds": self.draw_previous_odds,
            "away_odds": self.away_previous_odds,
        }.get(odds_column)

    def opening_for(self, odds_column):
        return {
            "home_odds": self.home_opening_odds,
            "draw_odds": self.draw_opening_odds,
            "away_odds": self.away_opening_odds,
        }.get(odds_column)

    def trend_for(self, odds_column):
        return {
            "home_odds": self.home_trend,
            "draw_odds": self.draw_trend,
            "away_odds": self.away_trend,
        }.get(odds_column)


@dataclass(frozen=True)
class WinnerFetchResult:
    matches: tuple[WinnerMatch, ...]
    source_url: str
    error: str | None = None
    warning: str | None = None
    from_cache: bool = False
    fetched_at: str | None = None


class WinnerHistoryStore:
    """Append only changed Winner prices to a local SQLite time series."""

    def __init__(self, path=WINNER_HISTORY_DB):
        self.path = Path(path)

    def record_matches(self, matches):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with closing(sqlite3.connect(self.path)) as connection:
            connection.execute("""
                CREATE TABLE IF NOT EXISTS winner_odds_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    recorded_at TEXT NOT NULL,
                    match_id TEXT NOT NULL,
                    home_team TEXT NOT NULL,
                    away_team TEXT NOT NULL,
                    start_time TEXT,
                    outcome TEXT NOT NULL,
                    current_odds REAL NOT NULL,
                    previous_odds REAL,
                    opening_odds REAL,
                    trend INTEGER,
                    source TEXT NOT NULL
                )
            """)
            connection.execute("""
                CREATE INDEX IF NOT EXISTS idx_winner_history_lookup
                ON winner_odds_history(match_id, outcome, id)
            """)
            now = datetime.now(timezone.utc).isoformat()
            for match in matches:
                match_id = match.match_id or (
                    f"{normalize_team(match.home_team)}|"
                    f"{normalize_team(match.away_team)}"
                )
                for outcome, column in (
                    ("home", "home_odds"),
                    ("draw", "draw_odds"),
                    ("away", "away_odds"),
                ):
                    current = match.odd_for(column)
                    if current is None:
                        continue
                    last = connection.execute(
                        """
                        SELECT current_odds
                        FROM winner_odds_history
                        WHERE match_id = ? AND outcome = ?
                        ORDER BY id DESC LIMIT 1
                        """,
                        (str(match_id), outcome),
                    ).fetchone()
                    if last and abs(float(last[0]) - float(current)) < 0.0001:
                        continue
                    connection.execute(
                        """
                        INSERT INTO winner_odds_history (
                            recorded_at, match_id, home_team, away_team,
                            start_time, outcome, current_odds, previous_odds,
                            opening_odds, trend, source
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            now,
                            str(match_id),
                            match.home_team,
                            match.away_team,
                            match.start_time,
                            outcome,
                            float(current),
                            match.previous_for(column),
                            match.opening_for(column),
                            match.trend_for(column),
                            match.source,
                        ),
                    )
            connection.commit()

    def get_history(self, match_id, outcome, limit=120):
        """Return the oldest-to-newest stored price changes for one outcome."""
        if not match_id or not self.path.exists():
            return []
        try:
            with closing(sqlite3.connect(self.path)) as connection:
                rows = connection.execute(
                    """
                    SELECT recorded_at, current_odds, previous_odds, opening_odds
                    FROM winner_odds_history
                    WHERE match_id = ? AND outcome = ?
                    ORDER BY id DESC
                    LIMIT ?
                    """,
                    (str(match_id), str(outcome), max(1, int(limit))),
                ).fetchall()
        except sqlite3.Error:
            return []
        return [
            {
                "recorded_at": row[0],
                "current_odds": float(row[1]),
                "previous_odds": row[2],
                "opening_odds": row[3],
            }
            for row in reversed(rows)
        ]


class WinnerOddsFetcher:
    """Retrieve public Winner listings without bypassing access controls."""

    COOLDOWN_SECONDS = 30
    _fetch_lock = threading.Lock()
    _last_fetch_at = 0.0
    _cached_result = None

    def __init__(self, url=None, timeout=12, history_store=None):
        configured_url = url or os.getenv("WINNER_ODDS_URL")
        self.url = configured_url or WINNER_PUBLIC_LINE_URL
        self.uses_public_line_api = configured_url is None
        self.timeout = timeout
        self.history_store = history_store or WinnerHistoryStore()

    def fetch(self):
        with self._fetch_lock:
            elapsed = time.monotonic() - self.__class__._last_fetch_at
            cached = self.__class__._cached_result
            if cached is not None and elapsed < self.COOLDOWN_SECONDS:
                return WinnerFetchResult(
                    cached.matches,
                    cached.source_url,
                    cached.error,
                    cached.warning,
                    True,
                    cached.fetched_at,
                )

            if self.uses_public_line_api:
                primary = self._fetch_365scores()
                if primary.error is None:
                    result = primary
                else:
                    fallback = self._fetch_public_line()
                    if fallback.error is None:
                        result = WinnerFetchResult(
                            fallback.matches,
                            fallback.source_url,
                            warning=(
                                f"365Scores sync failed ({primary.error}); "
                                "direct Winner fallback succeeded."
                            ),
                        )
                    else:
                        result = WinnerFetchResult(
                            (),
                            primary.source_url,
                            error=(
                                f"365Scores failed: {primary.error}; "
                                f"Winner fallback failed: {fallback.error}"
                            ),
                        )
            else:
                result = self._fetch_configured_source()

            if result.fetched_at is None:
                result = WinnerFetchResult(
                    result.matches,
                    result.source_url,
                    result.error,
                    result.warning,
                    result.from_cache,
                    datetime.now(timezone.utc).isoformat(),
                )
            if result.matches:
                try:
                    self.history_store.record_matches(result.matches)
                except (OSError, sqlite3.Error) as exc:
                    result = WinnerFetchResult(
                        result.matches,
                        result.source_url,
                        result.error,
                        (
                            f"{result.warning + ' ' if result.warning else ''}"
                            f"Winner history logging failed: {exc}"
                        ),
                        result.from_cache,
                        result.fetched_at,
                    )
            self.__class__._last_fetch_at = time.monotonic()
            self.__class__._cached_result = result
            return result

    def _fetch_configured_source(self):
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 Chrome/124 Safari/537.36"
            ),
            "Accept": "application/json,text/html,application/xhtml+xml",
            "Accept-Language": "he-IL,he;q=0.9,en;q=0.8",
        }
        try:
            response = requests.get(
                self.url,
                headers=headers,
                timeout=self.timeout,
            )
            response.raise_for_status()
            matches = self._parse_response(response)
            if not matches:
                return WinnerFetchResult(
                    (),
                    self.url,
                    "Winner responded, but no recognizable soccer match odds were found.",
                )
            return WinnerFetchResult(tuple(matches), self.url)
        except requests.RequestException as exc:
            return WinnerFetchResult(
                (),
                self.url,
                f"Winner auto-sync unavailable: {exc}",
            )
        except (TypeError, ValueError, json.JSONDecodeError) as exc:
            return WinnerFetchResult(
                (),
                self.url,
                f"Winner response could not be parsed: {exc}",
            )

    def _fetch_365scores(self):
        params = {
            "sport": 1,
            "lineType": 1,
            "minGames": 1,
            "maxGames": 500,
            "context": "dashboard",
            "withCompetitionFilter": "true",
            "appTypeId": 5,
            "langId": 10,
            "timezoneName": "Asia/Jerusalem",
            "userCountryId": 6,
        }
        try:
            response = requests.get(
                SCORES365_WINNER_URL,
                params=params,
                headers={
                    "User-Agent": "Mozilla/5.0",
                    "Accept": "application/json",
                    "Origin": "https://www.365scores.com",
                    "Referer": "https://www.365scores.com/",
                },
                timeout=self.timeout,
            )
            response.raise_for_status()
            matches = self.parse_365scores(response.json())
            if not matches:
                return WinnerFetchResult(
                    (),
                    SCORES365_WINNER_URL,
                    "unexpected schema or no Winner full-time odds",
                )
            return WinnerFetchResult(tuple(matches), SCORES365_WINNER_URL)
        except requests.RequestException as exc:
            return WinnerFetchResult(
                (), SCORES365_WINNER_URL, f"request failed: {exc}"
            )
        except (TypeError, ValueError, KeyError, json.JSONDecodeError) as exc:
            return WinnerFetchResult(
                (), SCORES365_WINNER_URL, f"schema parse failed: {exc}"
            )

    @classmethod
    def parse_365scores(cls, payload):
        games = {
            str(game.get("id")): game
            for game in payload.get("games", [])
            if isinstance(game, dict) and game.get("id") is not None
        }
        matches = []
        for line in payload.get("lines", []):
            if (
                not isinstance(line, dict)
                or int(line.get("bookmakerId", -1)) != 1
                or int(line.get("lineTypeId", -1)) != 1
            ):
                continue
            game = games.get(str(line.get("gameId")))
            if not game:
                continue
            home = (game.get("homeCompetitor") or {}).get("name")
            away = (game.get("awayCompetitor") or {}).get("name")
            if not home or not away:
                continue

            values = {}
            for option in line.get("options", []):
                if not isinstance(option, dict):
                    continue
                name = str(option.get("name", "")).casefold()
                column = {"1": "home", "x": "draw", "2": "away"}.get(name)
                if not column:
                    continue
                values[f"{column}_odds"] = cls._decimal_from_rate(
                    option.get("rate")
                )
                values[f"{column}_previous_odds"] = cls._decimal_from_rate(
                    option.get("oldRate")
                )
                values[f"{column}_opening_odds"] = cls._decimal_from_rate(
                    option.get("originalRate")
                )
                values[f"{column}_trend"] = cls._safe_int(option.get("trend"))

            if values.get("home_odds") and values.get("away_odds"):
                matches.append(
                    WinnerMatch(
                        home_team=str(home),
                        away_team=str(away),
                        match_id=str(game.get("id")),
                        start_time=game.get("startTime"),
                        source="365Scores",
                        **values,
                    )
                )
        return cls._deduplicate(matches)

    @classmethod
    def _decimal_from_rate(cls, rate):
        if isinstance(rate, dict):
            return cls._odd_from_value(rate.get("decimal"))
        return cls._odd_from_value(rate)

    @staticmethod
    def _safe_int(value):
        try:
            return int(value)
        except (TypeError, ValueError):
            return None

    def _fetch_public_line(self):
        user_agent = (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 Chrome/124 Safari/537.36"
        )
        session = requests.Session()
        try:
            session.get(
                DEFAULT_WINNER_URL,
                headers={"User-Agent": user_agent},
                timeout=self.timeout,
            ).raise_for_status()
            headers = {
                "User-Agent": user_agent,
                "Accept": "application/json",
                "Content-Type": "application/json",
                "Origin": DEFAULT_WINNER_URL.rstrip("/"),
                "Referer": DEFAULT_WINNER_URL,
                "RequestId": str(uuid.uuid4()),
                "DeviceId": str(uuid.uuid4()),
                "appVersion": "2.6.2",
                "HashesMessage": "{}",
                "UserAgentData": json.dumps({
                    "devicemodel": "Windows",
                    "deviceos": "windows",
                    "deviceosversion": "10",
                    "appversion": "2.6.2",
                    "apptype": "desktop",
                    "originId": 15,
                    "isAccessibility": False,
                }),
            }
            csrf_token = session.cookies.get("csrf_token")
            if csrf_token:
                headers["X-Csrf-Token"] = csrf_token
            response = session.get(
                WINNER_PUBLIC_LINE_URL,
                headers=headers,
                params={"lineChecksum": "fictive_hash"},
                timeout=max(self.timeout, 20),
            )
            response.raise_for_status()
            matches = self.parse_winner_line(response.json())
            if not matches:
                return WinnerFetchResult(
                    (),
                    WINNER_PUBLIC_LINE_URL,
                    "Winner returned no full-time 1/X/2 soccer markets.",
                )
            return WinnerFetchResult(
                tuple(matches),
                WINNER_PUBLIC_LINE_URL,
            )
        except requests.RequestException as exc:
            return WinnerFetchResult(
                (),
                WINNER_PUBLIC_LINE_URL,
                f"Winner public line sync unavailable: {exc}",
            )
        except (TypeError, ValueError, json.JSONDecodeError) as exc:
            return WinnerFetchResult(
                (),
                WINNER_PUBLIC_LINE_URL,
                f"Winner public line response could not be parsed: {exc}",
            )

    def _parse_response(self, response):
        content_type = response.headers.get("content-type", "").casefold()
        if "json" in content_type:
            return self.parse_json(response.json())

        text = response.text
        stripped = text.lstrip()
        if stripped.startswith(("{", "[")):
            try:
                return self.parse_json(json.loads(text))
            except json.JSONDecodeError:
                pass
        return self.parse_html(text)

    @classmethod
    def parse_json(cls, payload):
        matches = []

        def visit(node):
            if isinstance(node, dict):
                match = cls._match_from_mapping(node)
                if match:
                    matches.append(match)
                for value in node.values():
                    visit(value)
            elif isinstance(node, list):
                for value in node:
                    visit(value)

        visit(payload)
        return cls._deduplicate(matches)

    @classmethod
    def parse_winner_line(cls, payload):
        """Parse Winner's public full-time 1/X/2 market (mop 10002)."""
        matches = []
        for market in payload.get("markets", []):
            if not isinstance(market, dict) or market.get("mop") != 10002:
                continue
            title = cls._clean_bidi_text(market.get("desc"))
            if " - " not in title:
                continue
            home, away = (part.strip() for part in title.split(" - ", 1))
            outcomes = market.get("outcomes")
            if not home or not away or not isinstance(outcomes, list):
                continue

            home_odds = draw_odds = away_odds = None
            for outcome in outcomes:
                if not isinstance(outcome, dict):
                    continue
                description = cls._clean_bidi_text(outcome.get("desc"))
                odd = cls._odd_from_value(outcome.get("price"))
                if not odd:
                    continue
                normalized = normalize_team(description)
                if normalized in {"x", "draw", "תיקו"}:
                    draw_odds = odd
                elif team_similarity(home, description) >= 0.82:
                    home_odds = odd
                elif team_similarity(away, description) >= 0.82:
                    away_odds = odd

            if home_odds and away_odds:
                matches.append(
                    WinnerMatch(
                        home_team=home,
                        away_team=away,
                        match_id=str(market.get("eId")) if market.get("eId") else None,
                        home_odds=home_odds,
                        draw_odds=draw_odds,
                        away_odds=away_odds,
                        source="Winner direct",
                    )
                )
        return cls._deduplicate(matches)

    @classmethod
    def parse_html(cls, html):
        soup = BeautifulSoup(html, "html.parser")
        matches = []

        for script in soup.select(
            'script[type="application/json"], script[type="application/ld+json"]'
        ):
            try:
                matches.extend(cls.parse_json(json.loads(script.string or "")))
            except (json.JSONDecodeError, TypeError):
                continue

        selectors = (
            "[data-home-team][data-away-team]",
            ".match-card",
            ".event-card",
            ".game-card",
            "[class*='match']",
            "[class*='event']",
        )
        for card in soup.select(",".join(selectors)):
            match = cls._match_from_html_card(card)
            if match:
                matches.append(match)
        return cls._deduplicate(matches)

    @classmethod
    def _match_from_mapping(cls, data):
        home = cls._first_text(data, HOME_KEYS)
        away = cls._first_text(data, AWAY_KEYS)
        if not home or not away:
            participants = data.get("participants") or data.get("competitors")
            if isinstance(participants, list) and len(participants) >= 2:
                home = cls._participant_name(participants[0])
                away = cls._participant_name(participants[1])
        if not home or not away:
            return None

        home_odds = cls._first_odd(data, HOME_ODDS_KEYS)
        draw_odds = cls._first_odd(data, DRAW_ODDS_KEYS)
        away_odds = cls._first_odd(data, AWAY_ODDS_KEYS)

        markets = data.get("markets") or data.get("market")
        if isinstance(markets, (list, dict)):
            outcomes = cls._find_outcomes(markets)
            for outcome in outcomes:
                name = normalize_team(cls._participant_name(outcome))
                odd = cls._odd_from_value(
                    outcome.get("price")
                    or outcome.get("odds")
                    or outcome.get("value")
                )
                if not odd:
                    continue
                if name in {"draw", "x", "תיקו"}:
                    draw_odds = draw_odds or odd
                elif team_similarity(home, name) >= 0.72:
                    home_odds = home_odds or odd
                elif team_similarity(away, name) >= 0.72:
                    away_odds = away_odds or odd

        if not any((home_odds, draw_odds, away_odds)):
            return None
        return WinnerMatch(
            home_team=home,
            away_team=away,
            home_odds=home_odds,
            draw_odds=draw_odds,
            away_odds=away_odds,
        )

    @classmethod
    def _match_from_html_card(cls, card):
        home = card.get("data-home-team")
        away = card.get("data-away-team")
        if not home:
            node = card.select_one(
                "[data-role='home-team'], .home-team, [class*='homeTeam']"
            )
            home = node.get_text(" ", strip=True) if node else None
        if not away:
            node = card.select_one(
                "[data-role='away-team'], .away-team, [class*='awayTeam']"
            )
            away = node.get_text(" ", strip=True) if node else None
        if not home or not away:
            return None

        def odd(selector, attribute):
            node = card.select_one(selector)
            value = (
                card.get(attribute)
                or (node.get("data-odds") if node else None)
                or (node.get_text(" ", strip=True) if node else None)
            )
            return cls._odd_from_value(value)

        return WinnerMatch(
            home_team=home,
            away_team=away,
            home_odds=odd(
                "[data-outcome='1'], .home-odds, [class*='homeOdds']",
                "data-home-odds",
            ),
            draw_odds=odd(
                "[data-outcome='x'], .draw-odds, [class*='drawOdds']",
                "data-draw-odds",
            ),
            away_odds=odd(
                "[data-outcome='2'], .away-odds, [class*='awayOdds']",
                "data-away-odds",
            ),
        )

    @staticmethod
    def _first_text(data, keys):
        for key in keys:
            value = data.get(key)
            if isinstance(value, dict):
                value = value.get("name") or value.get("title")
            if value is not None and str(value).strip():
                return str(value).strip()
        return None

    @classmethod
    def _first_odd(cls, data, keys):
        for key in keys:
            odd = cls._odd_from_value(data.get(key))
            if odd:
                return odd
        return None

    @staticmethod
    def _participant_name(value):
        if isinstance(value, dict):
            return str(
                value.get("name")
                or value.get("title")
                or value.get("label")
                or ""
            )
        return str(value or "")

    @classmethod
    def _find_outcomes(cls, node):
        outcomes = []
        if isinstance(node, dict):
            direct = node.get("outcomes") or node.get("selections")
            if isinstance(direct, list):
                outcomes.extend(item for item in direct if isinstance(item, dict))
            for value in node.values():
                if isinstance(value, (list, dict)):
                    outcomes.extend(cls._find_outcomes(value))
        elif isinstance(node, list):
            for value in node:
                outcomes.extend(cls._find_outcomes(value))
        return outcomes

    @staticmethod
    def _odd_from_value(value):
        if isinstance(value, dict):
            value = value.get("decimal") or value.get("value") or value.get("price")
        if value is None:
            return None
        match = re.search(r"(?<!\d)(\d{1,3}(?:[.,]\d{1,3}))(?!\d)", str(value))
        if not match:
            return None
        odd = float(match.group(1).replace(",", "."))
        return odd if 1 < odd < 1000 else None

    @staticmethod
    def _clean_bidi_text(value):
        return re.sub(r"[\u200e\u200f\u202a-\u202e\u2066-\u2069]", "", str(value or "")).strip()

    @staticmethod
    def _deduplicate(matches):
        unique = {}
        for match in matches:
            key = (normalize_team(match.home_team), normalize_team(match.away_team))
            if all(key):
                unique[key] = match
        return list(unique.values())


def normalize_team(value):
    text = unicodedata.normalize("NFKD", str(value or "").casefold())
    text = "".join(char for char in text if not unicodedata.combining(char))
    text = re.sub(r"[^\w\u0590-\u05ff]+", " ", text, flags=re.UNICODE)
    return " ".join(text.split())


def team_variants(team):
    normalized = normalize_team(team)
    variants = {normalized}
    variants.update(normalize_team(alias) for alias in TEAM_ALIASES.get(normalized, ()))
    return {variant for variant in variants if variant}


def team_similarity(expected, actual):
    actual_normalized = normalize_team(actual)
    if not actual_normalized:
        return 0.0
    scores = []
    for variant in team_variants(expected):
        if variant == actual_normalized:
            return 1.0
        if variant in actual_normalized or actual_normalized in variant:
            scores.append(0.92)
        scores.append(SequenceMatcher(None, variant, actual_normalized).ratio())
    return max(scores, default=0.0)


def parse_match_time(value):
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def match_winner_game(
    home_team,
    away_team,
    winner_matches,
    threshold=0.72,
    expected_start_time=None,
    max_kickoff_difference_hours=18,
):
    """Match both team identity and, when available, the scheduled kickoff."""
    expected_kickoff = parse_match_time(expected_start_time)
    best = None
    best_score = 0.0
    best_time_difference = float("inf")
    for match in winner_matches:
        direct = (
            team_similarity(home_team, match.home_team)
            + team_similarity(away_team, match.away_team)
        ) / 2
        swapped = (
            team_similarity(home_team, match.away_team)
            + team_similarity(away_team, match.home_team)
        ) / 2
        score = max(direct, swapped)

        match_kickoff = parse_match_time(match.start_time)
        time_difference = float("inf")
        if expected_kickoff is not None and match_kickoff is not None:
            time_difference = abs(
                (match_kickoff - expected_kickoff).total_seconds()
            ) / 3600
            if time_difference > max_kickoff_difference_hours:
                continue

        if (
            score > best_score
            or (
                abs(score - best_score) < 0.0001
                and time_difference < best_time_difference
            )
        ):
            best = match
            best_score = score
            best_time_difference = time_difference
    return (best, best_score) if best is not None and best_score >= threshold else (None, best_score)
