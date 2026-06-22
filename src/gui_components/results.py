import tkinter as tk
from datetime import datetime, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import customtkinter as ctk
import pandas as pd


class ResultsMixin:
    """Searchable, incrementally rendered game cards and bookmaker details."""

    def build_results_tab(self):
        self.results_tab.grid_rowconfigure(2, weight=1)
        self.results_tab.grid_columnconfigure(0, weight=1)
        header = ctk.CTkFrame(self.results_tab, fg_color="transparent")
        header.grid(row=0, column=0, sticky="ew", padx=8, pady=(6, 8))
        self.results_title = ctk.CTkLabel(
            header, text="Game odds overview", font=ctk.CTkFont(size=14, weight="bold")
        )
        self.results_title.pack(side="left")
        self.result_search_entry = ctk.CTkEntry(
            header, placeholder_text="Search home or away team...", width=230
        )
        self.result_search_entry.pack(side="right")
        self.result_search_entry.bind("<KeyRelease>", self.filter_result_teams)
        ctk.CTkButton(
            header, text="Export scan CSV", command=self.export_results_csv,
            width=105, height=28,
        ).pack(side="right", padx=(0, 8))
        ctk.CTkLabel(
            header,
            text="↑ odds rose   ↓ odds fell",
            text_color=("gray45", "gray65"),
            font=ctk.CTkFont(size=10),
        ).pack(side="right", padx=12)
        ctk.CTkLabel(
            self.results_tab,
            text=(
                "Export scan CSV saves every bookmaker/outcome from the current scan, "
                "including its movement since the previous scan."
            ),
            anchor="w",
            text_color=("gray45", "gray65"),
            font=ctk.CTkFont(size=10),
        ).grid(row=1, column=0, sticky="ew", padx=8, pady=(0, 6))
        self.game_results = ctk.CTkScrollableFrame(
            self.results_tab, fg_color=("gray90", "gray14")
        )
        self.game_results.grid(row=2, column=0, sticky="nsew", padx=4, pady=(0, 4))
        self.game_results.grid_columnconfigure(0, weight=1)
        self.show_results_message("Scan a competition to see its games here.")

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

    def display_game_results(self, df):
        self.capture_odds_movements(df)
        self.latest_results_df = df.copy()
        if self.result_search_after_id is not None:
            self.after_cancel(self.result_search_after_id)
            self.result_search_after_id = None
        self.result_search_entry.delete(0, tk.END)
        self.render_filtered_game_results()

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
        card = ctk.CTkFrame(self.game_results, corner_radius=9)
        card.grid(row=row, column=0, sticky="ew", padx=4, pady=5)
        card.grid_columnconfigure(0, weight=1)
        details = ctk.CTkFrame(card, fg_color=("gray87", "gray18"))
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
            anchor="w", fg_color="transparent", hover_color=("gray78", "gray25"),
            text_color=("gray10", "gray95"), font=ctk.CTkFont(size=14, weight="bold"),
        )
        arrow.grid(row=0, column=0, sticky="ew", padx=8, pady=(7, 3))
        first = game_df.iloc[0]
        ctk.CTkLabel(
            card,
            text=(f"Home team: {home}   •   Away team: {away}\n"
                  f"Jerusalem time: {self.format_jerusalem_time(first.get('commence_time'))}\n"
                  f"Country: {self.metadata_value(first.get('country'))}   •   "
                  f"Stadium: {self.metadata_value(first.get('stadium'))}"),
            anchor="w", justify="left", text_color=("gray35", "gray70"),
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
            valid = game_df.dropna(subset=[column])
            if valid.empty:
                continue
            highest = valid.loc[valid[column].idxmax()]
            lowest = valid.loc[valid[column].idxmin()]
            ctk.CTkLabel(
                summary, text=label, anchor="w", font=ctk.CTkFont(size=12, weight="bold")
            ).grid(row=result_row, column=0, sticky="w", padx=(0, 12), pady=2)
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
                button.grid(row=result_row, column=col, sticky="ew", padx=6, pady=2)
        self.build_custom_odd_controls(card, event_key, home, away, has_draw)

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
