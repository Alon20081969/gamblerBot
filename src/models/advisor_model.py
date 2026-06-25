"""Transparent Elo estimates and persistent Advisor prediction evaluation."""

import math
import sqlite3
from contextlib import closing
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
PREDICTIONS_DB = PROJECT_ROOT / "data" / "advisor_predictions.sqlite3"


@dataclass(frozen=True)
class EloEstimate:
    home_rating: float
    away_rating: float
    home_probability: float
    draw_probability: float
    away_probability: float
    games_used: int

    def probability_for(self, odds_column):
        return {
            "home_odds": self.home_probability,
            "draw_odds": self.draw_probability,
            "away_odds": self.away_probability,
        }.get(str(odds_column))


class EloAdvisorModel:
    """Build a provisional fixture estimate from recent scored match histories."""

    BASE_RATING = 1500.0
    HOME_ADVANTAGE = 65.0
    K_FACTOR = 24.0
    MARKET_WEIGHT = 0.80
    ELO_WEIGHT = 0.20

    @classmethod
    def estimate(cls, home_team_id, away_team_id, recent_games):
        home_id, away_id = str(home_team_id), str(away_team_id)
        unique_games = {}
        for game in recent_games or ():
            if not isinstance(game, dict) or game.get("id") is None:
                continue
            unique_games[str(game["id"])] = game
        ordered = sorted(
            unique_games.values(),
            key=lambda game: str(game.get("startTime") or ""),
        )
        ratings = {}
        games_used = 0
        for game in ordered:
            home = game.get("homeCompetitor") or {}
            away = game.get("awayCompetitor") or {}
            if home.get("id") is None or away.get("id") is None:
                continue
            try:
                home_score = float(home.get("score"))
                away_score = float(away.get("score"))
            except (TypeError, ValueError):
                continue
            game_home_id, game_away_id = str(home["id"]), str(away["id"])
            home_rating = ratings.get(game_home_id, cls.BASE_RATING)
            away_rating = ratings.get(game_away_id, cls.BASE_RATING)
            expected_home = cls.expected_score(
                home_rating + cls.HOME_ADVANTAGE,
                away_rating,
            )
            if home_score > away_score:
                actual_home = 1.0
            elif home_score < away_score:
                actual_home = 0.0
            else:
                actual_home = 0.5
            goal_multiplier = 1.0 + 0.25 * math.log1p(
                abs(home_score - away_score)
            )
            change = (
                cls.K_FACTOR
                * goal_multiplier
                * (actual_home - expected_home)
            )
            ratings[game_home_id] = home_rating + change
            ratings[game_away_id] = away_rating - change
            games_used += 1

        home_rating = ratings.get(home_id, cls.BASE_RATING)
        away_rating = ratings.get(away_id, cls.BASE_RATING)
        decisive_home = cls.expected_score(
            home_rating + cls.HOME_ADVANTAGE,
            away_rating,
        )
        rating_gap = abs(
            (home_rating + cls.HOME_ADVANTAGE) - away_rating
        )
        draw_probability = max(0.16, min(0.28, 0.28 - rating_gap / 2000))
        home_probability = (1 - draw_probability) * decisive_home
        away_probability = (1 - draw_probability) * (1 - decisive_home)
        return EloEstimate(
            home_rating=round(home_rating, 1),
            away_rating=round(away_rating, 1),
            home_probability=home_probability,
            draw_probability=draw_probability,
            away_probability=away_probability,
            games_used=games_used,
        )

    @staticmethod
    def expected_score(rating_a, rating_b):
        return 1 / (1 + 10 ** ((float(rating_b) - float(rating_a)) / 400))

    @classmethod
    def blended_probability(cls, market_probability, elo_probability):
        market = float(market_probability)
        if market > 1:
            market /= 100
        elo = float(elo_probability)
        return (
            cls.MARKET_WEIGHT * market
            + cls.ELO_WEIGHT * elo
        )


class PredictionLedger:
    """Store pre-match Advisor estimates and settle them by 365Scores game ID."""

    def __init__(self, path=PREDICTIONS_DB):
        self.path = Path(path)
        self.ensure_schema()

    def connect(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        return sqlite3.connect(self.path, timeout=10)

    def ensure_schema(self):
        with closing(self.connect()) as connection:
            connection.execute("""
                CREATE TABLE IF NOT EXISTS advisor_predictions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    recorded_at TEXT NOT NULL,
                    scores365_game_id TEXT NOT NULL,
                    event_id TEXT,
                    home_team TEXT NOT NULL,
                    away_team TEXT NOT NULL,
                    kickoff TEXT,
                    odds_column TEXT NOT NULL,
                    selection TEXT NOT NULL,
                    market_probability REAL NOT NULL,
                    elo_probability REAL,
                    model_probability REAL NOT NULL,
                    winner_odds REAL,
                    expected_value REAL,
                    risk_label TEXT,
                    settled_at TEXT,
                    actual_outcome TEXT,
                    correct INTEGER,
                    profit_units REAL,
                    UNIQUE(scores365_game_id, odds_column)
                )
            """)
            connection.commit()

    def record(self, prediction):
        now = datetime.now(timezone.utc).isoformat()
        fields = (
            "scores365_game_id", "event_id", "home_team", "away_team",
            "kickoff", "odds_column", "selection", "market_probability",
            "elo_probability", "model_probability", "winner_odds",
            "expected_value", "risk_label",
        )
        values = [prediction.get(field) for field in fields]
        with closing(self.connect()) as connection:
            connection.execute(
                f"""
                INSERT INTO advisor_predictions (
                    recorded_at, {", ".join(fields)}
                ) VALUES (?, {", ".join("?" for _ in fields)})
                ON CONFLICT(scores365_game_id, odds_column) DO UPDATE SET
                    winner_odds = COALESCE(
                        excluded.winner_odds,
                        advisor_predictions.winner_odds
                    ),
                    expected_value = COALESCE(
                        excluded.expected_value,
                        advisor_predictions.expected_value
                    )
                """,
                [now, *values],
            )
            connection.commit()

    def pending_game_ids(self, limit=30):
        with closing(self.connect()) as connection:
            rows = connection.execute(
                """
                SELECT DISTINCT scores365_game_id
                FROM advisor_predictions
                WHERE settled_at IS NULL
                ORDER BY id ASC LIMIT ?
                """,
                (max(1, int(limit)),),
            ).fetchall()
        return [str(row[0]) for row in rows]

    def settle_game(self, game_id, home_score, away_score):
        try:
            home_score = float(home_score)
            away_score = float(away_score)
        except (TypeError, ValueError):
            return 0
        if home_score > away_score:
            actual = "home_odds"
        elif away_score > home_score:
            actual = "away_odds"
        else:
            actual = "draw_odds"
        now = datetime.now(timezone.utc).isoformat()
        with closing(self.connect()) as connection:
            rows = connection.execute(
                """
                SELECT id, odds_column, winner_odds
                FROM advisor_predictions
                WHERE scores365_game_id = ? AND settled_at IS NULL
                """,
                (str(game_id),),
            ).fetchall()
            for prediction_id, odds_column, winner_odds in rows:
                correct = int(str(odds_column) == actual)
                profit = None
                if winner_odds is not None:
                    profit = (
                        float(winner_odds) - 1
                        if correct
                        else -1.0
                    )
                connection.execute(
                    """
                    UPDATE advisor_predictions
                    SET settled_at = ?, actual_outcome = ?, correct = ?,
                        profit_units = ?
                    WHERE id = ?
                    """,
                    (now, actual, correct, profit, prediction_id),
                )
            connection.commit()
        return len(rows)

    def summary(self):
        with closing(self.connect()) as connection:
            row = connection.execute(
                """
                SELECT
                    COUNT(*) AS total,
                    SUM(CASE WHEN settled_at IS NOT NULL THEN 1 ELSE 0 END),
                    SUM(CASE WHEN correct = 1 THEN 1 ELSE 0 END),
                    AVG(
                        CASE WHEN settled_at IS NOT NULL THEN
                            (model_probability - correct)
                            * (model_probability - correct)
                        END
                    ),
                    SUM(profit_units),
                    SUM(CASE WHEN profit_units IS NOT NULL THEN 1 ELSE 0 END)
                FROM advisor_predictions
                """
            ).fetchone()
        total = int(row[0] or 0)
        settled = int(row[1] or 0)
        correct = int(row[2] or 0)
        priced = int(row[5] or 0)
        return {
            "total": total,
            "settled": settled,
            "pending": total - settled,
            "correct": correct,
            "accuracy_pct": (
                round(correct / settled * 100, 1) if settled else None
            ),
            "brier_score": (
                round(float(row[3]), 4) if row[3] is not None else None
            ),
            "profit_units": (
                round(float(row[4]), 2) if row[4] is not None else None
            ),
            "priced_predictions": priced,
        }
