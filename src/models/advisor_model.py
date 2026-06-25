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

    @classmethod
    def probabilities_from_ratings(
        cls,
        home_rating,
        away_rating,
        games_used=0,
    ):
        decisive_home = cls.expected_score(
            float(home_rating) + cls.HOME_ADVANTAGE,
            float(away_rating),
        )
        rating_gap = abs(
            (float(home_rating) + cls.HOME_ADVANTAGE)
            - float(away_rating)
        )
        draw_probability = max(0.16, min(0.28, 0.28 - rating_gap / 2000))
        return EloEstimate(
            home_rating=round(float(home_rating), 1),
            away_rating=round(float(away_rating), 1),
            home_probability=(1 - draw_probability) * decisive_home,
            draw_probability=draw_probability,
            away_probability=(1 - draw_probability) * (1 - decisive_home),
            games_used=int(games_used),
        )


class PersistentEloStore:
    """Persist unique completed matches and rebuild global ratings chronologically."""

    def __init__(self, path=PREDICTIONS_DB):
        self.path = Path(path)
        self.ensure_schema()

    def connect(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        return sqlite3.connect(self.path, timeout=10)

    def ensure_schema(self):
        with closing(self.connect()) as connection:
            connection.execute("""
                CREATE TABLE IF NOT EXISTS elo_matches (
                    game_id TEXT PRIMARY KEY,
                    start_time TEXT NOT NULL,
                    competition TEXT,
                    home_team_id TEXT NOT NULL,
                    home_team_name TEXT NOT NULL,
                    away_team_id TEXT NOT NULL,
                    away_team_name TEXT NOT NULL,
                    home_score REAL NOT NULL,
                    away_score REAL NOT NULL,
                    importance_weight REAL NOT NULL
                )
            """)
            connection.execute("""
                CREATE TABLE IF NOT EXISTS elo_ratings (
                    team_id TEXT PRIMARY KEY,
                    team_name TEXT NOT NULL,
                    rating REAL NOT NULL,
                    games_played INTEGER NOT NULL,
                    last_match_time TEXT
                )
            """)
            connection.commit()

    def ingest_games(self, games):
        rows = []
        for game in games or ():
            row = self.game_row(game)
            if row:
                rows.append(row)
        if not rows:
            return 0
        with closing(self.connect()) as connection:
            before = connection.total_changes
            connection.executemany(
                """
                INSERT OR IGNORE INTO elo_matches (
                    game_id, start_time, competition,
                    home_team_id, home_team_name,
                    away_team_id, away_team_name,
                    home_score, away_score, importance_weight
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                rows,
            )
            added = connection.total_changes - before
            connection.commit()
        if added:
            self.rebuild_ratings()
        return int(added)

    @classmethod
    def game_row(cls, game):
        if not isinstance(game, dict) or game.get("id") is None:
            return None
        try:
            if int(game.get("statusGroup", 4)) != 4:
                return None
        except (TypeError, ValueError):
            return None
        home = game.get("homeCompetitor") or {}
        away = game.get("awayCompetitor") or {}
        if (
            home.get("id") is None
            or away.get("id") is None
            or not game.get("startTime")
        ):
            return None
        try:
            home_score = float(home.get("score"))
            away_score = float(away.get("score"))
        except (TypeError, ValueError):
            return None
        competition = str(game.get("competitionDisplayName") or "")
        return (
            str(game["id"]),
            str(game["startTime"]),
            competition,
            str(home["id"]),
            str(home.get("name") or home["id"]),
            str(away["id"]),
            str(away.get("name") or away["id"]),
            home_score,
            away_score,
            cls.importance_weight(competition),
        )

    @staticmethod
    def importance_weight(competition):
        name = str(competition or "").casefold()
        if "friendly" in name:
            return 0.55
        if "world cup" in name and "qualif" not in name:
            return 1.15
        if "qualif" in name:
            return 0.90
        return 1.0

    def rebuild_ratings(self):
        with closing(self.connect()) as connection:
            rows = connection.execute(
                """
                SELECT start_time, home_team_id, home_team_name,
                       away_team_id, away_team_name,
                       home_score, away_score, importance_weight
                FROM elo_matches
                ORDER BY start_time ASC, game_id ASC
                """
            ).fetchall()
            ratings = {}
            games_played = {}
            names = {}
            last_played = {}
            for (
                start_time,
                home_id,
                home_name,
                away_id,
                away_name,
                home_score,
                away_score,
                importance,
            ) in rows:
                home_rating = self.regress_for_inactivity(
                    ratings.get(home_id, EloAdvisorModel.BASE_RATING),
                    last_played.get(home_id),
                    start_time,
                )
                away_rating = self.regress_for_inactivity(
                    ratings.get(away_id, EloAdvisorModel.BASE_RATING),
                    last_played.get(away_id),
                    start_time,
                )
                expected_home = EloAdvisorModel.expected_score(
                    home_rating + EloAdvisorModel.HOME_ADVANTAGE,
                    away_rating,
                )
                actual_home = (
                    1.0 if home_score > away_score
                    else 0.0 if home_score < away_score
                    else 0.5
                )
                goal_multiplier = 1.0 + 0.25 * math.log1p(
                    abs(home_score - away_score)
                )
                change = (
                    EloAdvisorModel.K_FACTOR
                    * float(importance)
                    * goal_multiplier
                    * (actual_home - expected_home)
                )
                ratings[home_id] = home_rating + change
                ratings[away_id] = away_rating - change
                games_played[home_id] = games_played.get(home_id, 0) + 1
                games_played[away_id] = games_played.get(away_id, 0) + 1
                names[home_id], names[away_id] = home_name, away_name
                last_played[home_id] = last_played[away_id] = start_time

            connection.execute("DELETE FROM elo_ratings")
            connection.executemany(
                """
                INSERT INTO elo_ratings (
                    team_id, team_name, rating, games_played, last_match_time
                ) VALUES (?, ?, ?, ?, ?)
                """,
                [
                    (
                        team_id,
                        names[team_id],
                        rating,
                        games_played[team_id],
                        last_played[team_id],
                    )
                    for team_id, rating in ratings.items()
                ],
            )
            connection.commit()

    @staticmethod
    def regress_for_inactivity(rating, previous_time, current_time):
        if not previous_time:
            return float(rating)
        try:
            previous = datetime.fromisoformat(
                str(previous_time).replace("Z", "+00:00")
            )
            current = datetime.fromisoformat(
                str(current_time).replace("Z", "+00:00")
            )
            days = max(0.0, (current - previous).total_seconds() / 86400)
        except (TypeError, ValueError):
            return float(rating)
        retention = 0.5 ** (days / 730)
        return (
            EloAdvisorModel.BASE_RATING
            + (float(rating) - EloAdvisorModel.BASE_RATING) * retention
        )

    def estimate(self, home_team_id, away_team_id):
        with closing(self.connect()) as connection:
            rows = connection.execute(
                """
                SELECT team_id, rating, games_played
                FROM elo_ratings
                WHERE team_id IN (?, ?)
                """,
                (str(home_team_id), str(away_team_id)),
            ).fetchall()
            match_count = connection.execute(
                "SELECT COUNT(*) FROM elo_matches"
            ).fetchone()[0]
        ratings = {
            str(team_id): (float(rating), int(games_played))
            for team_id, rating, games_played in rows
        }
        home = ratings.get(
            str(home_team_id),
            (EloAdvisorModel.BASE_RATING, 0),
        )
        away = ratings.get(
            str(away_team_id),
            (EloAdvisorModel.BASE_RATING, 0),
        )
        estimate = EloAdvisorModel.probabilities_from_ratings(
            home[0],
            away[0],
            games_used=match_count,
        )
        return estimate, home[1], away[1]


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
            existing_columns = {
                row[1]
                for row in connection.execute(
                    "PRAGMA table_info(advisor_predictions)"
                ).fetchall()
            }
            for column, definition in (
                ("raw_model_probability", "REAL"),
                ("calibration_sample", "INTEGER"),
            ):
                if column not in existing_columns:
                    connection.execute(
                        f"ALTER TABLE advisor_predictions "
                        f"ADD COLUMN {column} {definition}"
                    )
            connection.commit()

    def record(self, prediction):
        now = datetime.now(timezone.utc).isoformat()
        fields = (
            "scores365_game_id", "event_id", "home_team", "away_team",
            "kickoff", "odds_column", "selection", "market_probability",
            "elo_probability", "raw_model_probability",
            "model_probability", "calibration_sample", "winner_odds",
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

    def calibrate_probability(self, raw_probability, minimum_sample=8):
        raw = min(0.99, max(0.01, float(raw_probability)))
        lower = math.floor(raw * 10) / 10
        upper = min(1.000001, lower + 0.1)
        with closing(self.connect()) as connection:
            row = connection.execute(
                """
                SELECT COUNT(*), SUM(correct)
                FROM advisor_predictions
                WHERE settled_at IS NOT NULL
                  AND raw_model_probability >= ?
                  AND raw_model_probability < ?
                """,
                (lower, upper),
            ).fetchone()
        sample = int(row[0] or 0)
        correct = int(row[1] or 0)
        if sample < int(minimum_sample):
            return raw, sample
        prior_strength = 10
        calibrated = (
            correct + raw * prior_strength
        ) / (sample + prior_strength)
        return min(0.99, max(0.01, calibrated)), sample

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
            settled_rows = connection.execute(
                """
                SELECT model_probability, correct
                FROM advisor_predictions
                WHERE settled_at IS NOT NULL
                """
            ).fetchall()
        total = int(row[0] or 0)
        settled = int(row[1] or 0)
        correct = int(row[2] or 0)
        priced = int(row[5] or 0)
        log_loss = None
        if settled_rows:
            losses = []
            for probability, actual in settled_rows:
                probability = min(0.999999, max(0.000001, float(probability)))
                losses.append(
                    -(
                        int(actual) * math.log(probability)
                        + (1 - int(actual)) * math.log(1 - probability)
                    )
                )
            log_loss = sum(losses) / len(losses)
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
            "log_loss": (
                round(log_loss, 4) if log_loss is not None else None
            ),
        }
