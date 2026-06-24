import tkinter as tk
from datetime import datetime, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import customtkinter as ctk
import pandas as pd

from src.models.probabilities import MarketAnalyzer


class ResultsMixin:
    """Searchable, incrementally rendered game cards and bookmaker details."""

    def build_results_tab(self):
        self.results_tab.grid_rowconfigure(2, weight=1)
        self.results_tab.grid_columnconfigure(0, weight=1)
        header = ctk.CTkFrame(self.results_tab, fg_color="transparent")
        header.grid(row=0, column=0, sticky="ew", padx=8, pady=(6, 8))
        self.results_title = ctk.CTkLabel(
            header,
            text="Market results",
            font=ctk.CTkFont(size=18, weight="bold"),
            text_color=self.COLORS["text"],
        )
        self.results_title.pack(side="left")
        self.result_search_entry = ctk.CTkEntry(
            header,
            placeholder_text="Search teams...",
            width=250,
            height=34,
            fg_color=self.COLORS["panel_alt"],
            border_color=self.COLORS["border_light"],
        )
        self.result_search_entry.pack(side="right")
        self.result_search_entry.bind("<KeyRelease>", self.filter_result_teams)
        ctk.CTkButton(
            header, text="Export scan CSV", command=self.export_results_csv,
            width=122, height=34,
            fg_color=self.COLORS["accent"],
            hover_color=self.COLORS["accent_hover"],
        ).pack(side="right", padx=(0, 8))
        ctk.CTkLabel(
            header,
            text="↑ odds rose   ↓ odds fell",
            text_color=("gray45", "gray65"),
            font=ctk.CTkFont(size=10),
        ).pack(side="right", padx=12)
        self.results_export_status = ctk.CTkLabel(
            self.results_tab,
            text=(
                "Export scan CSV saves every bookmaker/outcome from the current scan, "
                "including its movement since the previous scan."
            ),
            anchor="w",
            text_color=("gray45", "gray65"),
            font=ctk.CTkFont(size=10),
        )
        self.results_export_status.grid(row=1, column=0, sticky="ew", padx=8, pady=(0, 6))
        self.game_results = ctk.CTkScrollableFrame(
            self.results_tab,
            fg_color=self.COLORS["panel_soft"],
            corner_radius=12,
            border_width=1,
            border_color=self.COLORS["border"],
        )
        self.game_results.grid(row=2, column=0, sticky="nsew", padx=4, pady=(0, 4))
        self.game_results.grid_columnconfigure(0, weight=1)
        self.show_results_message("Scan a competition to see its games here.")
        self.build_best_opportunities_tab()

    def build_best_opportunities_tab(self):
        self.best_tab.grid_rowconfigure(2, weight=1)
        self.best_tab.grid_columnconfigure(0, weight=1)
        header = ctk.CTkFrame(self.best_tab, fg_color="transparent")
        header.grid(row=0, column=0, sticky="ew", padx=8, pady=(6, 8))
        self.best_title = ctk.CTkLabel(
            header,
            text="Best value opportunities",
            font=ctk.CTkFont(size=18, weight="bold"),
            text_color=self.COLORS["text"],
        )
        self.best_title.pack(side="left")
        ctk.CTkButton(
            header,
            text="Open Results",
            command=lambda: self.show_page("Results"),
            width=112,
            height=34,
            fg_color=self.COLORS["accent"],
            hover_color=self.COLORS["accent_hover"],
        ).pack(side="right")
        self.best_sort_dropdown = ctk.CTkComboBox(
            header,
            values=["Highest value first", "Lowest value first"],
            state="readonly",
            width=180,
            height=34,
            fg_color=self.COLORS["panel_alt"],
            border_color=self.COLORS["border_light"],
            button_color=self.COLORS["border_light"],
            button_hover_color=self.COLORS["accent"],
            command=lambda _value: self.rerender_best_opportunities(),
        )
        self.best_sort_dropdown.set("Highest value first")
        self.best_sort_dropdown.pack(side="right", padx=(0, 8))
        self.best_status = ctk.CTkLabel(
            self.best_tab,
            text=(
                "Value score compares the best available odd with a margin-free "
                "consensus from all complete bookmaker markets. +10 means the price "
                "is 10% above consensus value. It is not a prediction."
            ),
            anchor="w",
            text_color=self.COLORS["muted"],
            font=ctk.CTkFont(size=10),
        )
        self.best_status.grid(row=1, column=0, sticky="ew", padx=8, pady=(0, 6))
        self.best_results = ctk.CTkScrollableFrame(
            self.best_tab,
            fg_color=self.COLORS["panel_soft"],
            corner_radius=12,
            border_width=1,
            border_color=self.COLORS["border"],
        )
        self.best_results.grid(row=2, column=0, sticky="nsew", padx=4, pady=(0, 4))
        self.best_results.grid_columnconfigure(0, weight=1)
        self.show_best_opportunities_message("Scan a competition to rank opportunities.")

    def show_results_message(self, message):
        self.results_generation += 1
        self.latest_results_df = None
        if hasattr(self, "result_search_entry"):
            self.result_search_entry.delete(0, tk.END)
        for widget in self.game_results.winfo_children():
            widget.destroy()
        ctk.CTkLabel(
            self.game_results, text=message, text_color=("gray40", "gray65"),
            wraplength=500,
        ).grid(row=0, column=0, sticky="ew", padx=20, pady=30)
        if hasattr(self, "best_results"):
            self.show_best_opportunities_message("Scan a competition to rank opportunities.")

    def show_best_opportunities_message(self, message):
        for widget in self.best_results.winfo_children():
            widget.destroy()
        ctk.CTkLabel(
            self.best_results,
            text=message,
            text_color=("gray40", "gray65"),
            wraplength=620,
        ).grid(row=0, column=0, sticky="ew", padx=20, pady=30)

    def rerender_best_opportunities(self):
        if self.latest_results_df is not None:
            self.render_best_opportunities(self.latest_results_df)

    def display_game_results(self, df):
        self.capture_odds_movements(df)
        self.latest_results_df = df.copy()
        if self.result_search_after_id is not None:
            self.after_cancel(self.result_search_after_id)
            self.result_search_after_id = None
        self.result_search_entry.delete(0, tk.END)
        self.render_filtered_game_results()
        self.render_best_opportunities(df)

    def render_best_opportunities(self, df):
        if not hasattr(self, "best_results"):
            return
        for widget in self.best_results.winfo_children():
            widget.destroy()
        opportunities = MarketAnalyzer.find_discrepancies(df, minimum_spread_pct=0)
        if opportunities.empty:
            self.best_title.configure(text="Best value opportunities - 0")
            self.show_best_opportunities_message(
                "No opportunity data is available for this scan."
            )
            return
        sort_lowest_first = (
            hasattr(self, "best_sort_dropdown")
            and self.best_sort_dropdown.get() == "Lowest value first"
        )
        opportunities = opportunities.sort_values(
            ["value_score", "opportunity_score", "spread_pct"],
            ascending=[
                sort_lowest_first,
                sort_lowest_first,
                sort_lowest_first,
            ],
            na_position="last",
        )
        direction = "lowest first" if sort_lowest_first else "highest first"
        self.best_title.configure(
            text=f"Best value opportunities - {len(opportunities)} shown ({direction})"
        )
        for rank, (_, row) in enumerate(opportunities.iterrows(), start=1):
            self.create_opportunity_card(rank, row)

    def add_opportunity_to_slip(self, row):
        match = str(row.get("match", "Unknown match"))
        event_id = row.get("event_id")
        event_key = str(event_id) if pd.notna(event_id) else match.replace(" vs ", "|")
        bookmaker = str(row.get("best_bookmaker", "Unknown bookmaker"))
        odds_column = str(row.get("odds_column", "best_odds"))
        identity = (event_key, bookmaker, odds_column)

        try:
            odds = float(row.get("best_odds"))
        except (TypeError, ValueError):
            self.write_to_terminal("[!] Could not add leaderboard pick: missing odds.")
            return

        self.selected_bets[event_key] = {
            "identity": identity,
            "match": match,
            "selection": str(row.get("selection", row.get("outcome", "Selection"))),
            "bookmaker": bookmaker,
            "odds": odds,
        }
        self.set_custom_odd_status(event_key, False)
        self.update_odds_button_styles(event_key)
        self.render_bet_slip()
        if hasattr(self, "saved_slip_status"):
            self.saved_slip_status.configure(
                text=f"Added from Best: {match} - {row.get('selection')} @ {odds:.2f}"
            )
        self.show_page("Bet Slip")

    def make_opportunity_card_clickable(self, widget, row):
        try:
            widget.configure(cursor="hand2")
        except (tk.TclError, AttributeError):
            pass
        widget.bind("<Button-1>", lambda _event, pick=row: self.add_opportunity_to_slip(pick))

    def create_opportunity_card(self, rank, row):
        value_score = row.get("value_score")
        score = float(value_score) if pd.notna(value_score) else 0.0
        confidence = str(row.get("consensus_confidence") or "Low")
        confidence_color = {
            "High": self.COLORS["success"],
            "Medium": self.COLORS["warning"],
            "Low": self.COLORS["danger"],
        }.get(confidence, self.COLORS["muted"])
        color = (
            self.COLORS["success"] if score >= 5
            else self.COLORS["warning"] if score >= 0
            else self.COLORS["danger"]
        )
        card = ctk.CTkFrame(
            self.best_results,
            corner_radius=12,
            fg_color=self.COLORS["panel"],
            border_width=1,
            border_color=self.COLORS["border"],
        )
        card.grid(row=rank - 1, column=0, sticky="ew", padx=8, pady=6)
        card.grid_columnconfigure(1, weight=1)
        self.make_opportunity_card_clickable(card, row)
        rank_label = ctk.CTkLabel(
            card,
            text=f"#{rank}",
            text_color=color,
            font=ctk.CTkFont(size=18, weight="bold"),
            width=52,
        )
        rank_label.grid(row=0, column=0, rowspan=3, padx=(12, 4), pady=12)
        self.make_opportunity_card_clickable(rank_label, row)
        title_label = ctk.CTkLabel(
            card,
            text=f"{row['match']}  •  Bet option: {row['selection']}",
            text_color=self.COLORS["text"],
            font=ctk.CTkFont(size=14, weight="bold"),
            anchor="w",
        )
        title_label.grid(row=0, column=1, sticky="ew", padx=8, pady=(12, 2))
        self.make_opportunity_card_clickable(title_label, row)
        detail = (
            f"{row['outcome']} @ {row['best_odds']:.2f} at {row['best_bookmaker']}   |   "
            f"Fair odds {self.format_metric(row.get('consensus_fair_odds'))}   |   "
            f"Consensus chance "
            f"{self.format_metric(row.get('consensus_probability_pct'), '%')}   |   "
            f"{int(row.get('consensus_bookmakers') or 0)} bookmakers"
        )
        detail_label = ctk.CTkLabel(
            card,
            text=detail,
            text_color=self.COLORS["muted"],
            font=ctk.CTkFont(size=11),
            anchor="w",
        )
        detail_label.grid(row=1, column=1, sticky="ew", padx=8, pady=(0, 12))
        self.make_opportunity_card_clickable(detail_label, row)
        explanation_label = ctk.CTkLabel(
            card,
            text=self.opportunity_explanation(row),
            text_color=self.COLORS["text"],
            font=ctk.CTkFont(size=11),
            anchor="w",
            justify="left",
            wraplength=900,
        )
        explanation_label.grid(
            row=2, column=1, sticky="ew", padx=8, pady=(0, 12)
        )
        self.make_opportunity_card_clickable(explanation_label, row)
        score_label = ctk.CTkLabel(
            card,
            text=f"Value\n{score:+.2f}%",
            text_color=color,
            font=ctk.CTkFont(size=12, weight="bold"),
            justify="center",
            width=86,
        )
        score_label.grid(row=0, column=2, rowspan=2, padx=12, pady=(12, 2))
        self.make_opportunity_card_clickable(score_label, row)
        confidence_label = ctk.CTkLabel(
            card,
            text=f"{confidence}\nconfidence",
            text_color=confidence_color,
            font=ctk.CTkFont(size=11, weight="bold"),
            justify="center",
            width=86,
        )
        confidence_label.grid(row=2, column=2, padx=12, pady=(2, 12))
        self.make_opportunity_card_clickable(confidence_label, row)

    def opportunity_explanation(self, row):
        value = row.get("value_score")
        fair_odds = row.get("consensus_fair_odds")
        bookmaker_count = int(row.get("consensus_bookmakers") or 0)
        probability_range = row.get("consensus_probability_range_pct")
        confidence = str(row.get("consensus_confidence") or "Low")

        if pd.isna(value) or pd.isna(fair_odds):
            return (
                "Why: there is not enough complete bookmaker data to calculate "
                "a reliable consensus value."
            )

        position = "above" if float(value) >= 0 else "below"
        return (
            f"Why: the offered {float(row['best_odds']):.2f} price is "
            f"{abs(float(value)):.2f}% {position} the fair {float(fair_odds):.2f} "
            f"price. {confidence} confidence uses {bookmaker_count} complete "
            f"bookmakers whose estimates span "
            f"{self.format_metric(probability_range, ' percentage points')}."
        )

    def capture_odds_movements(self, df):
        """Compare this scan with prior prices from the same session."""
        current = {}
        metadata = {}
        for _, row in df.iterrows():
            event_id = row.get('event_id')
            event_key = str(event_id) if pd.notna(event_id) else (
                f"{row.get('home_team')}|{row.get('away_team')}"
            )
            bookmaker = str(row.get('bookmaker'))
            for odds_column in ('home_odds', 'draw_odds', 'away_odds'):
                odds = row.get(odds_column)
                if pd.notna(odds):
                    identity = (event_key, bookmaker, odds_column)
                    current[identity] = float(odds)
                    selection = (
                        "Draw" if odds_column == 'draw_odds'
                        else str(row.get('home_team')) if odds_column == 'home_odds'
                        else str(row.get('away_team'))
                    )
                    metadata[identity] = {
                        "match": f"{row.get('home_team')} vs {row.get('away_team')}",
                        "selection": selection,
                        "bookmaker": bookmaker,
                    }

        movements = {}
        for identity, current_odds in current.items():
            previous_odds = self.previous_odds_snapshot.get(identity)
            if previous_odds is not None:
                difference = current_odds - previous_odds
                movements[identity] = difference if abs(difference) >= 0.001 else 0.0

        self.odds_movements = movements
        self.previous_odds_snapshot.update(current)
        self.record_odds_history(current, metadata)

    def filter_result_teams(self, _event=None):
        if self.result_search_after_id is not None:
            self.after_cancel(self.result_search_after_id)
        self.result_search_after_id = self.after(160, self.apply_result_team_filter)

    def apply_result_team_filter(self):
        self.result_search_after_id = None
        self.render_filtered_game_results()

    def render_filtered_game_results(self):
        if self.latest_results_df is None:
            return
        query = self.result_search_entry.get().strip()
        data = self.latest_results_df
        if query:
            home = data['home_team'].astype(str).str.contains(query, case=False, regex=False, na=False)
            away = data['away_team'].astype(str).str.contains(query, case=False, regex=False, na=False)
            data = data[home | away]
        self.results_generation += 1
        generation = self.results_generation
        for widget in self.game_results.winfo_children():
            widget.destroy()
        self.odds_buttons = {}
        self.custom_odd_controls = {}
        self.view_tabs.set("Results")
        games = list(data.groupby(
            ['event_id', 'home_team', 'away_team'], dropna=False, sort=False
        ))
        if not games:
            self.results_title.configure(text="Team search  •  0 games")
            ctk.CTkLabel(
                self.game_results, text=f'No teams found for "{query}".',
                text_color=("gray40", "gray65"),
            ).grid(row=0, column=0, sticky="ew", padx=20, pady=30)
            return
        self.results_title.configure(text=f"Loading games...  0/{len(games)}")
        self.render_game_batch(games, 0, generation)

    def render_game_batch(self, games, start, generation):
        if self.is_closing or generation != self.results_generation:
            return
        end = min(start + 6, len(games))
        for row in range(start, end):
            (event_id, home, away), game_df = games[row]
            event_key = str(event_id) if pd.notna(event_id) else f"{home}|{away}"
            self.create_game_card(row, event_key, home, away, game_df)
        if end < len(games):
            self.results_title.configure(text=f"Loading games...  {end}/{len(games)}")
            self.after(1, self.render_game_batch, games, end, generation)
        else:
            self.results_title.configure(text=f"Game odds overview  •  {len(games)} games")

    def create_game_card(self, row, event_key, home, away, game_df):
        card = ctk.CTkFrame(
            self.game_results,
            corner_radius=12,
            fg_color=self.COLORS["panel"],
            border_width=1,
            border_color=self.COLORS["border"],
        )
        card.grid(row=row, column=0, sticky="ew", padx=8, pady=7)
        card.grid_columnconfigure(0, weight=1)
        details = ctk.CTkFrame(
            card,
            fg_color=self.COLORS["panel_soft"],
            corner_radius=10,
            border_width=1,
            border_color=self.COLORS["border"],
        )
        state = {"expanded": False, "loaded": False}

        def toggle_details():
            state["expanded"] = not state["expanded"]
            if state["expanded"]:
                if not state["loaded"]:
                    self.populate_bookmaker_details(details, event_key, home, away, game_df)
                    state["loaded"] = True
                details.grid(row=4, column=0, sticky="ew", padx=10, pady=(0, 10))
                arrow.configure(text=f"▼  {home} vs {away}")
            else:
                details.grid_remove()
                arrow.configure(text=f"▶  {home} vs {away}")

        arrow = ctk.CTkButton(
            card, text=f"▶  {home} vs {away}", command=toggle_details,
            anchor="w", fg_color="transparent", hover_color=self.COLORS["panel_alt"],
            text_color=self.COLORS["text"], font=ctk.CTkFont(size=15, weight="bold"),
        )
        arrow.grid(row=0, column=0, sticky="ew", padx=8, pady=(7, 3))
        first = game_df.iloc[0]
        ctk.CTkLabel(
            card,
            text=(f"Home team: {home}   •   Away team: {away}\n"
                  f"Jerusalem time: {self.format_jerusalem_time(first.get('commence_time'))}\n"
                  f"Country: {self.metadata_value(first.get('country'))}   •   "
                  f"Stadium: {self.metadata_value(first.get('stadium'))}"),
            anchor="w", justify="left", text_color=self.COLORS["muted"],
            font=ctk.CTkFont(size=11),
        ).grid(row=1, column=0, sticky="ew", padx=16, pady=(0, 5))

        summary = ctk.CTkFrame(card, fg_color="transparent")
        summary.grid(row=2, column=0, sticky="ew", padx=16, pady=(0, 9))
        summary.grid_columnconfigure(1, weight=1)
        summary.grid_columnconfigure(2, weight=1)
        has_draw = 'draw_odds' in game_df and game_df['draw_odds'].notna().any()
        selections = [(f"Home — {home}", 'home_odds', home)]
        if has_draw:
            selections.append(("Draw", 'draw_odds', "Draw"))
        selections.append((f"Away — {away}", 'away_odds', away))
        for result_row, (label, column, pick) in enumerate(selections):
            display_row = result_row * 2
            valid = game_df.dropna(subset=[column])
            if valid.empty:
                continue
            highest = valid.loc[valid[column].idxmax()]
            lowest = valid.loc[valid[column].idxmin()]
            ctk.CTkLabel(
                summary,
                text=label,
                anchor="w",
                text_color=self.COLORS["text"],
                font=ctk.CTkFont(size=12, weight="bold"),
            ).grid(row=display_row, column=0, sticky="w", padx=(0, 12), pady=2)
            for col, prefix, odds_row in (
                (1, "Highest", highest), (2, "Lowest", lowest)
            ):
                button = self.create_selectable_odd(
                    summary,
                    text=f"{prefix}: {odds_row[column]:.2f}  ({odds_row['bookmaker']})",
                    event_key=event_key, match=f"{home} vs {away}", selection=pick,
                    bookmaker=str(odds_row['bookmaker']), odds=float(odds_row[column]),
                    odds_column=column,
                )
                button.grid(row=display_row, column=col, sticky="ew", padx=6, pady=2)
            stats_text = self.outcome_probability_summary(
                highest=highest,
                lowest=lowest,
                odds_column=column,
                highest_odds=float(highest[column]),
                lowest_odds=float(lowest[column]),
            )
            ctk.CTkLabel(
                summary,
                text=stats_text,
                anchor="w",
                justify="left",
                text_color=self.COLORS["muted"],
                font=ctk.CTkFont(size=10),
            ).grid(
                row=display_row + 1,
                column=1,
                columnspan=2,
                sticky="ew",
                padx=6,
                pady=(0, 5),
            )
        self.build_custom_odd_controls(card, event_key, home, away, has_draw)

    @staticmethod
    def format_metric(value, suffix="", fallback="n/a"):
        if pd.isna(value):
            return fallback
        try:
            return f"{float(value):.2f}{suffix}"
        except (TypeError, ValueError):
            return fallback

    def outcome_probability_summary(self, highest, lowest, odds_column,
                                    highest_odds, lowest_odds):
        prefix = odds_column.replace("_odds", "")
        implied = highest.get(f"{prefix}_implied_pct")
        if pd.isna(implied):
            implied = highest.get(odds_column.replace("_odds", "_implied_pct"))
        spread = highest.get(f"{prefix}_spread_pct")
        if pd.isna(spread):
            spread = ((highest_odds - lowest_odds) / lowest_odds) * 100 if lowest_odds else None
        score = highest.get(f"{prefix}_opportunity_score")
        value_score = highest.get(f"{prefix}_value_score")
        fair_odds = highest.get(f"{prefix}_consensus_fair_odds")
        confidence = highest.get(f"{prefix}_consensus_confidence")
        return (
            f"Implied chance: {self.format_metric(implied, '%')}   |   "
            f"Bookmaker spread: {self.format_metric(spread, '%')}   |   "
            f"Fair odds: {self.format_metric(fair_odds)}   |   "
            f"Consensus value: {self.format_metric(value_score, '%')}   |   "
            f"Confidence: {confidence or 'Low'}   |   "
            f"Price disagreement: {self.format_metric(score)}"
        )

    @staticmethod
    def metadata_value(value):
        if value is None:
            return "Not provided by odds API"
        text = str(value).strip()
        return text if text and text.casefold() not in {"none", "nan", "nat", "<na>"} \
            else "Not provided by odds API"

    @staticmethod
    def format_jerusalem_time(value):
        if pd.isna(value) or not str(value).strip():
            return "Time not provided"
        try:
            parsed = datetime.fromisoformat(str(value).replace('Z', '+00:00'))
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            return parsed.astimezone(ZoneInfo("Asia/Jerusalem")).strftime("%a, %d %b %Y at %H:%M")
        except (ValueError, TypeError, ZoneInfoNotFoundError):
            return "Invalid kickoff time"

    def populate_bookmaker_details(self, details, event_key, home, away, game_df):
        has_draw = 'draw_odds' in game_df and game_df['draw_odds'].notna().any()
        columns = [("Bookmaker", None), (f"Home — {home}", 'home_odds')]
        if has_draw:
            columns.append(("Draw", 'draw_odds'))
        columns.append((f"Away — {away}", 'away_odds'))
        for index, (heading, _) in enumerate(columns):
            details.grid_columnconfigure(index, weight=1)
            ctk.CTkLabel(
                details, text=heading, font=ctk.CTkFont(size=11, weight="bold")
            ).grid(row=0, column=index, sticky="ew", padx=7, pady=(7, 4))
        rows = game_df.drop_duplicates(subset=['bookmaker']).sort_values('bookmaker')
        for table_row, (_, odds_row) in enumerate(rows.iterrows(), start=1):
            for column_index, (_, odds_column) in enumerate(columns):
                if odds_column is None:
                    ctk.CTkLabel(details, text=str(odds_row['bookmaker'])).grid(
                        row=table_row, column=column_index, sticky="ew", padx=7, pady=3
                    )
                    continue
                odds = odds_row[odds_column]
                if pd.isna(odds):
                    ctk.CTkLabel(details, text="—").grid(
                        row=table_row, column=column_index, sticky="ew", padx=7, pady=3
                    )
                    continue
                selection = "Draw" if odds_column == 'draw_odds' else (
                    home if odds_column == 'home_odds' else away
                )
                button = self.create_selectable_odd(
                    details, text=f"{odds:.2f}", event_key=event_key,
                    match=f"{home} vs {away}", selection=selection,
                    bookmaker=str(odds_row['bookmaker']), odds=float(odds),
                    odds_column=odds_column,
                )
                button.grid(row=table_row, column=column_index, sticky="ew", padx=7, pady=3)
