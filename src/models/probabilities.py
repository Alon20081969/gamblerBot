import math

import pandas as pd


class MarketAnalyzer:
    """Flatten bookmaker odds and add reusable market math helpers."""

    ODDS_COLUMNS = ("home_odds", "draw_odds", "away_odds")

    @staticmethod
    def safe_decimal(value):
        """Return a valid decimal odd as float, otherwise None."""
        try:
            odd = float(value)
        except (TypeError, ValueError):
            return None
        if not math.isfinite(odd) or odd <= 1.0:
            return None
        return odd

    @classmethod
    def implied_probability_pct(cls, odds):
        """Convert decimal odds to implied probability percentage."""
        odd = cls.safe_decimal(odds)
        return round((1 / odd) * 100, 2) if odd else None

    @classmethod
    def market_margin_pct(cls, odds_values):
        """Calculate bookmaker margin/vig from all available outcome odds."""
        valid_odds = [cls.safe_decimal(odd) for odd in odds_values]
        valid_odds = [odd for odd in valid_odds if odd]
        if len(valid_odds) < 2:
            return None
        return round((sum(1 / odd for odd in valid_odds) - 1) * 100, 2)

    @staticmethod
    def odds_spread_pct(highest, lowest):
        """Return percentage difference between highest and lowest odds."""
        try:
            highest = float(highest)
            lowest = float(lowest)
        except (TypeError, ValueError):
            return None
        if lowest <= 0:
            return None
        return round(((highest - lowest) / lowest) * 100, 2)

    @classmethod
    def opportunity_score(cls, highest, lowest, median):
        """
        Score how interesting an outcome is.

        Higher score means the best available price is far above the market's
        lower/median price. This is not a prediction; it is a price-difference
        signal for filtering and sorting.
        """
        try:
            highest = float(highest)
            lowest = float(lowest)
            median = float(median)
        except (TypeError, ValueError):
            return 0.0
        if highest <= 1.0 or lowest <= 1.0 or median <= 1.0:
            return 0.0
        spread = max(0.0, highest - lowest)
        median_lift = max(0.0, highest - median)
        return round((spread / lowest * 70) + (median_lift / median * 30), 2)

    @classmethod
    def consensus_probabilities(cls, game_df):
        """Return margin-free consensus probabilities and bookmaker count."""
        consensus, count, _ = cls.consensus_analysis(game_df)
        return consensus, count

    @classmethod
    def consensus_analysis(cls, game_df):
        """
        Estimate fair probabilities and how tightly bookmakers agree.

        Each bookmaker's implied probabilities are normalized first, removing
        its margin (vig). The median normalized probability is then taken for
        each outcome and normalized once more so the final market sums to 100%.
        The range records the gap between the highest and lowest bookmaker
        probability estimate for each outcome, in percentage points.
        """
        if game_df is None or game_df.empty:
            return {}, 0, {}

        active_columns = [
            column
            for column in cls.ODDS_COLUMNS
            if column in game_df and game_df[column].notna().any()
        ]
        if len(active_columns) < 2:
            return {}, 0, {}

        estimates = {column: [] for column in active_columns}
        complete_market_count = 0
        for _, bookmaker_row in game_df.iterrows():
            odds = {
                column: cls.safe_decimal(bookmaker_row.get(column))
                for column in active_columns
            }
            if any(odds[column] is None for column in active_columns):
                continue

            implied_total = sum(1 / odds[column] for column in active_columns)
            if implied_total <= 0:
                continue
            complete_market_count += 1
            for column in active_columns:
                estimates[column].append((1 / odds[column]) / implied_total)

        if not complete_market_count:
            return {}, 0, {}

        consensus = {
            column: float(pd.Series(values).median())
            for column, values in estimates.items()
            if values
        }
        consensus_total = sum(consensus.values())
        if consensus_total <= 0:
            return {}, 0, {}
        normalized_consensus = {
            column: probability / consensus_total
            for column, probability in consensus.items()
        }
        probability_ranges_pct = {
            column: round((max(values) - min(values)) * 100, 2)
            for column, values in estimates.items()
            if values
        }
        return (
            normalized_consensus,
            complete_market_count,
            probability_ranges_pct,
        )

    @staticmethod
    def consensus_confidence(bookmaker_count, probability_range_pct):
        """
        Rate the stability of a consensus as High, Medium, or Low.

        High requires at least 6 complete bookmakers with estimates no more
        than 5 percentage points apart. Medium requires at least 3 bookmakers
        with estimates no more than 10 points apart. Everything else is Low.
        """
        try:
            count = int(bookmaker_count)
            range_pct = float(probability_range_pct)
        except (TypeError, ValueError):
            return "Low"
        if count >= 6 and range_pct <= 5:
            return "High"
        if count >= 3 and range_pct <= 10:
            return "Medium"
        return "Low"

    @classmethod
    def protected_best_market(cls, valid, odds_column):
        """
        Return prices eligible for the advertised best odd.

        With at least three prices, an upper price is treated as an outlier when
        it is above the median by both a robust MAD threshold and a minimum 15%
        tolerance. Outliers remain visible in bookmaker details, but do not
        create an unrealistic value recommendation.
        """
        if valid is None or valid.empty or len(valid) < 3:
            return valid, pd.DataFrame(columns=valid.columns if valid is not None else [])

        prices = valid[odds_column].astype(float)
        median = float(prices.median())
        median_absolute_deviation = float((prices - median).abs().median())
        robust_distance = 3 * 1.4826 * median_absolute_deviation
        tolerance = max(robust_distance, median * 0.15)
        upper_limit = median + tolerance
        outlier_mask = prices > upper_limit

        protected = valid.loc[~outlier_mask]
        if protected.empty:
            return valid, valid.iloc[0:0]
        return protected, valid.loc[outlier_mask]

    @staticmethod
    def value_edge_pct(best_odds, consensus_probability):
        """
        Return expected value per 100 staked using the market consensus.

        For example, +12 means the offered odds pay 12% more than the
        margin-free consensus estimate. It is a pricing signal, not a forecast.
        """
        try:
            odds = float(best_odds)
            probability = float(consensus_probability)
        except (TypeError, ValueError):
            return None
        if odds <= 1.0 or probability <= 0 or probability >= 1:
            return None
        return round(((odds * probability) - 1) * 100, 2)

    @staticmethod
    def metadata_from_event(raw_event_data):
        """Extract safe display metadata from a raw Odds API event."""
        venue = raw_event_data.get("venue") or {}
        if not isinstance(venue, dict):
            venue = {"name": str(venue)}
        stadium = (
            raw_event_data.get("stadium", "")
            or raw_event_data.get("venue_name", "")
            or venue.get("name", "")
            or "Venue not supplied"
        )
        country = (
            raw_event_data.get("country", "")
            or raw_event_data.get("sport_country", "")
            or venue.get("country", "")
            or "Country not supplied"
        )
        return country, stadium

    @classmethod
    def flatten_odds_data(cls, raw_event_data):
        """Convert raw nested JSON into a bookmaker-level odds DataFrame."""
        flat_records = []

        home_team = raw_event_data.get("home_team")
        away_team = raw_event_data.get("away_team")
        event_id = raw_event_data.get("id")
        commence_time = raw_event_data.get("commence_time")
        country, stadium = cls.metadata_from_event(raw_event_data)

        for bookmaker in raw_event_data.get("bookmakers", []):
            bookie_name = bookmaker.get("title") or "Unknown bookmaker"

            for market in bookmaker.get("markets", []):
                if market.get("key") != "h2h":
                    continue

                home_odds = None
                away_odds = None
                draw_odds = None

                for outcome in market.get("outcomes", []):
                    name = outcome.get("name")
                    price = cls.safe_decimal(outcome.get("price"))
                    if not name or not price:
                        continue

                    if name == home_team:
                        home_odds = price
                    elif name == away_team:
                        away_odds = price
                    elif str(name).casefold() == "draw":
                        draw_odds = price

                if not home_odds or not away_odds:
                    continue

                margin_pct = cls.market_margin_pct(
                    [home_odds, draw_odds, away_odds]
                    if draw_odds
                    else [home_odds, away_odds]
                )

                flat_records.append({
                    "event_id": event_id,
                    "home_team": home_team,
                    "away_team": away_team,
                    "commence_time": commence_time,
                    "country": country,
                    "stadium": stadium,
                    "bookmaker": bookie_name,
                    "home_odds": home_odds,
                    "away_odds": away_odds,
                    "draw_odds": draw_odds,
                    "home_implied_pct": cls.implied_probability_pct(home_odds),
                    "away_implied_pct": cls.implied_probability_pct(away_odds),
                    "draw_implied_pct": cls.implied_probability_pct(draw_odds),
                    "margin_pct": margin_pct,
                })

        return pd.DataFrame(flat_records)

    @classmethod
    def outcome_label(cls, odds_column):
        return {
            "home_odds": "Home",
            "draw_odds": "Draw",
            "away_odds": "Away",
        }.get(odds_column, str(odds_column))

    @classmethod
    def best_worst_by_outcome(cls, df):
        """Return one row per game/outcome with best, worst, spread, and score."""
        if df is None or df.empty:
            return pd.DataFrame()

        records = []
        group_cols = ["event_id", "home_team", "away_team"]
        for (event_id, home, away), game_df in df.groupby(group_cols, dropna=False):
            (
                consensus,
                consensus_bookmakers,
                probability_ranges_pct,
            ) = cls.consensus_analysis(game_df)
            for odds_column in cls.ODDS_COLUMNS:
                if odds_column not in game_df:
                    continue
                valid = game_df.dropna(subset=[odds_column])
                if valid.empty:
                    continue

                protected, excluded = cls.protected_best_market(
                    valid, odds_column
                )
                raw_highest = valid.loc[valid[odds_column].idxmax()]
                highest = protected.loc[protected[odds_column].idxmax()]
                lowest = valid.loc[valid[odds_column].idxmin()]
                median = float(protected[odds_column].median())
                best_odds = float(highest[odds_column])
                raw_best_odds = float(raw_highest[odds_column])
                worst_odds = float(lowest[odds_column])
                consensus_probability = consensus.get(odds_column)
                fair_odds = (
                    round(1 / consensus_probability, 2)
                    if consensus_probability
                    else None
                )
                value_score = cls.value_edge_pct(
                    best_odds, consensus_probability
                )
                probability_range_pct = probability_ranges_pct.get(odds_column)
                confidence = cls.consensus_confidence(
                    consensus_bookmakers, probability_range_pct
                )

                if odds_column == "home_odds":
                    selection = home
                elif odds_column == "away_odds":
                    selection = away
                else:
                    selection = "Draw"

                records.append({
                    "event_id": event_id,
                    "match": f"{home} vs {away}",
                    "selection": selection,
                    "outcome": cls.outcome_label(odds_column),
                    "odds_column": odds_column,
                    "best_odds": best_odds,
                    "best_bookmaker": str(highest["bookmaker"]),
                    "raw_best_odds": raw_best_odds,
                    "raw_best_bookmaker": str(raw_highest["bookmaker"]),
                    "outliers_excluded": int(len(excluded)),
                    "worst_odds": worst_odds,
                    "worst_bookmaker": str(lowest["bookmaker"]),
                    "median_odds": round(median, 2),
                    "best_implied_pct": cls.implied_probability_pct(best_odds),
                    "consensus_probability_pct": (
                        round(consensus_probability * 100, 2)
                        if consensus_probability
                        else None
                    ),
                    "consensus_fair_odds": fair_odds,
                    "consensus_bookmakers": consensus_bookmakers,
                    "consensus_probability_range_pct": probability_range_pct,
                    "consensus_confidence": confidence,
                    "value_score": value_score,
                    "spread_pct": cls.odds_spread_pct(best_odds, worst_odds),
                    "opportunity_score": cls.opportunity_score(
                        best_odds, worst_odds, median
                    ),
                })

        return pd.DataFrame(records)

    @classmethod
    def enrich_market_dataframe(cls, df):
        """Attach outcome-level best price metrics to each bookmaker row."""
        if df is None or df.empty:
            return df

        enriched = df.copy()
        for odds_column in cls.ODDS_COLUMNS:
            if odds_column not in enriched:
                continue
            implied_column = odds_column.replace("_odds", "_implied_pct")
            if implied_column not in enriched:
                enriched[implied_column] = enriched[odds_column].apply(
                    cls.implied_probability_pct
                )

        summary = cls.best_worst_by_outcome(enriched)
        if summary.empty:
            return enriched

        for _, row in summary.iterrows():
            mask = (
                (enriched["event_id"] == row["event_id"])
                & (enriched["home_team"] + " vs " + enriched["away_team"] == row["match"])
            )
            odds_column = row["odds_column"]
            prefix = odds_column.replace("_odds", "")
            enriched.loc[mask, f"{prefix}_best_odds"] = row["best_odds"]
            enriched.loc[mask, f"{prefix}_best_bookmaker"] = row["best_bookmaker"]
            enriched.loc[mask, f"{prefix}_raw_best_odds"] = row["raw_best_odds"]
            enriched.loc[mask, f"{prefix}_raw_best_bookmaker"] = (
                row["raw_best_bookmaker"]
            )
            enriched.loc[mask, f"{prefix}_outliers_excluded"] = (
                row["outliers_excluded"]
            )
            enriched.loc[mask, f"{prefix}_worst_odds"] = row["worst_odds"]
            enriched.loc[mask, f"{prefix}_worst_bookmaker"] = row["worst_bookmaker"]
            enriched.loc[mask, f"{prefix}_spread_pct"] = row["spread_pct"]
            enriched.loc[mask, f"{prefix}_opportunity_score"] = row["opportunity_score"]
            enriched.loc[mask, f"{prefix}_consensus_probability_pct"] = (
                row["consensus_probability_pct"]
            )
            enriched.loc[mask, f"{prefix}_consensus_fair_odds"] = (
                row["consensus_fair_odds"]
            )
            enriched.loc[mask, f"{prefix}_consensus_bookmakers"] = (
                row["consensus_bookmakers"]
            )
            enriched.loc[mask, f"{prefix}_consensus_probability_range_pct"] = (
                row["consensus_probability_range_pct"]
            )
            enriched.loc[mask, f"{prefix}_consensus_confidence"] = (
                row["consensus_confidence"]
            )
            enriched.loc[mask, f"{prefix}_value_score"] = row["value_score"]

        return enriched

    @classmethod
    def find_discrepancies(cls, df, minimum_spread_pct=5.0):
        """
        Find outcomes where bookmakers disagree materially.

        Kept under the old method name for compatibility with earlier code.
        """
        summary = cls.best_worst_by_outcome(df)
        if summary.empty:
            return summary
        return summary[
            summary["spread_pct"].fillna(0) >= float(minimum_spread_pct)
        ].sort_values(
            ["value_score", "opportunity_score"],
            ascending=False,
            na_position="last",
        )
